"""Image generation service -- orchestrates providers and scratch storage.

The ``ImageService`` is the DI service object injected into MCP tools.
It holds registered providers, dispatches generation requests, manages
an in-memory image registry backed by sidecar JSON files, and saves
generated images to the scratch directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from PIL import Image

from image_gen_mcp.providers.types import ImageProvider, ImageProviderError, ImageResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageRecord:
    """Metadata for a registered image in the scratch directory."""

    id: str
    original_path: Path
    content_type: str
    provider: str
    prompt: str
    negative_prompt: str | None
    aspect_ratio: str
    quality: str
    original_dimensions: tuple[int, int]
    provider_metadata: dict[
        str, Any
    ]  # treat as read-only; frozen prevents reassignment
    created_at: float


class ImageService:
    """Central orchestrator for image generation.

    Args:
        scratch_dir: Directory for saving generated images.
        default_provider: Provider name to use when none specified.
    """

    def __init__(
        self,
        scratch_dir: Path,
        default_provider: str = "auto",
    ) -> None:
        self._providers: dict[str, ImageProvider] = {}
        self._scratch_dir = scratch_dir
        self._default_provider = default_provider
        self._images: dict[str, ImageRecord] = {}

        # Rebuild registry from existing sidecar files
        self._load_registry()

    @property
    def scratch_dir(self) -> Path:
        """The scratch directory for saved images."""
        return self._scratch_dir

    @property
    def providers(self) -> dict[str, ImageProvider]:
        """Registered providers (read-only view)."""
        return self._providers

    async def aclose(self) -> None:
        """Close all providers that support async cleanup."""
        for provider in self._providers.values():
            if hasattr(provider, "aclose"):
                await provider.aclose()

    def register_provider(self, name: str, provider: ImageProvider) -> None:
        """Register an image provider.

        Args:
            name: Provider name (e.g., ``"openai"``, ``"placeholder"``).
            provider: Provider instance implementing ``ImageProvider``.
        """
        self._providers[name] = provider
        logger.info("Registered image provider: %s", name)

    _PROVIDER_DESCRIPTIONS: ClassVar[dict[str, str]] = {
        "openai": (
            "OpenAI (gpt-image-1 / dall-e-3) — best for text, logos, "
            "and general-purpose generation"
        ),
        "a1111": (
            "Stable Diffusion via A1111 WebUI — best for photorealism, "
            "portraits, and artistic styles"
        ),
        "placeholder": (
            "Zero-cost solid-color PNG — instant, no API key, for testing and drafts"
        ),
    }

    def list_providers(self) -> dict[str, dict[str, Any]]:
        """List registered providers with availability info.

        Returns:
            Dict of provider name -> ``{available: True, description: str}``.
        """
        result: dict[str, dict[str, Any]] = {}
        for name in self._providers:
            result[name] = {
                "available": True,
                "description": self._PROVIDER_DESCRIPTIONS.get(name, name),
            }
        return result

    def _resolve_provider(
        self, provider: str, prompt: str
    ) -> tuple[str, ImageProvider]:
        """Resolve a provider name to an instance.

        Args:
            provider: Provider name or ``"auto"``.
            prompt: The generation prompt (used for auto-selection).

        Returns:
            Tuple of (resolved_name, provider_instance).

        Raises:
            ImageProviderError: If no matching provider is available.
        """
        if not self._providers:
            raise ImageProviderError(
                provider,
                "No providers are registered. Configure at least one: "
                "set IMAGE_GEN_MCP_OPENAI_API_KEY for OpenAI, "
                "IMAGE_GEN_MCP_A1111_HOST for Stable Diffusion, "
                "or the placeholder provider is always available.",
            )

        if provider == "auto":
            from image_gen_mcp.providers.selector import select_provider

            selected = select_provider(prompt, set(self._providers))
            return selected, self._providers[selected]

        if provider not in self._providers:
            available = ", ".join(self._providers)
            raise ImageProviderError(
                provider,
                f"Provider '{provider}' not available. Available: {available}",
            )
        return provider, self._providers[provider]

    async def generate(
        self,
        prompt: str,
        *,
        provider: str | None = None,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
    ) -> tuple[str, ImageResult]:
        """Generate an image using a provider.

        Args:
            prompt: Text prompt for image generation.
            provider: Provider name, or ``None`` to use the configured default.
            negative_prompt: Things to avoid in the image.
            aspect_ratio: Desired aspect ratio.
            quality: Quality level.

        Returns:
            Tuple of (provider_name, ImageResult).

        Raises:
            ImageProviderError: If generation fails.
        """
        resolved_name, resolved_provider = self._resolve_provider(
            provider or self._default_provider, prompt
        )

        logger.info(
            "Generating image with provider=%s, aspect_ratio=%s",
            resolved_name,
            aspect_ratio,
        )

        result = await resolved_provider.generate(
            prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
        )

        return resolved_name, result

    # ------------------------------------------------------------------
    # Image registry
    # ------------------------------------------------------------------

    def register_image(
        self,
        result: ImageResult,
        provider_name: str,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
    ) -> ImageRecord:
        """Register a generated image in the scratch directory.

        Saves the original image, writes a sidecar JSON metadata file,
        and stores the record in the in-memory registry.

        Args:
            result: The image result to register.
            provider_name: Name of the provider that generated the image.
            prompt: The generation prompt.
            negative_prompt: Things to avoid (if any).
            aspect_ratio: Requested aspect ratio.
            quality: Requested quality level.

        Returns:
            The created ImageRecord.
        """
        self._scratch_dir.mkdir(parents=True, exist_ok=True)

        # Content-addressed ID
        image_id = hashlib.sha256(result.image_data).hexdigest()[:12]

        # Extract original dimensions via Pillow
        img = Image.open(io.BytesIO(result.image_data))
        original_dimensions = img.size  # (width, height)

        # Save original
        ext = _mime_to_ext(result.content_type)
        original_filename = f"{image_id}-original{ext}"
        original_path = self._scratch_dir / original_filename
        original_path.write_bytes(result.image_data)

        # Build record
        record = ImageRecord(
            id=image_id,
            original_path=original_path,
            content_type=result.content_type,
            provider=provider_name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            original_dimensions=original_dimensions,
            provider_metadata=result.provider_metadata,
            created_at=time.time(),
        )

        # Write sidecar JSON
        sidecar_path = self._scratch_dir / f"{image_id}.json"
        sidecar_data = {
            "id": record.id,
            "prompt": record.prompt,
            "negative_prompt": record.negative_prompt,
            "provider": record.provider,
            "aspect_ratio": record.aspect_ratio,
            "quality": record.quality,
            "content_type": record.content_type,
            "original_filename": original_filename,
            "original_size_bytes": result.size_bytes,
            "original_dimensions": list(record.original_dimensions),
            "provider_metadata": record.provider_metadata,
            "created_at": datetime.fromtimestamp(record.created_at, tz=UTC).isoformat(),
        }
        sidecar_path.write_text(json.dumps(sidecar_data, indent=2))

        # Store in registry
        self._images[image_id] = record

        logger.info(
            "Registered image %s from %s (%d bytes)",
            image_id,
            provider_name,
            result.size_bytes,
        )
        return record

    def get_image(self, image_id: str) -> ImageRecord:
        """Look up a registered image by ID.

        Args:
            image_id: The content-addressed image ID.

        Returns:
            The ImageRecord for the image.

        Raises:
            ImageProviderError: If the image ID is not found.
        """
        if image_id not in self._images:
            raise ImageProviderError(
                "server",
                f"Image '{image_id}' not found. "
                "Read image://list to see available IDs.",
            )
        return self._images[image_id]

    def list_images(self) -> list[ImageRecord]:
        """Return all registered images.

        Returns:
            List of ImageRecord instances.
        """
        return list(self._images.values())

    def _load_registry(self) -> None:
        """Rebuild the in-memory registry from sidecar JSON files."""
        if not self._scratch_dir.exists():
            return

        count = 0
        for sidecar_path in sorted(self._scratch_dir.glob("*.json")):
            try:
                data = json.loads(sidecar_path.read_text())
                image_id = data["id"]
                original_path = self._scratch_dir / data["original_filename"]
                if not original_path.exists():
                    logger.warning(
                        "Skipping sidecar %s: original file missing (%s)",
                        sidecar_path,
                        original_path,
                    )
                    continue

                # Parse ISO timestamp back to epoch
                created_at = datetime.fromisoformat(data["created_at"]).timestamp()

                record = ImageRecord(
                    id=image_id,
                    original_path=original_path,
                    content_type=data["content_type"],
                    provider=data["provider"],
                    prompt=data["prompt"],
                    negative_prompt=data.get("negative_prompt"),
                    aspect_ratio=data.get("aspect_ratio", "1:1"),
                    quality=data.get("quality", "standard"),
                    original_dimensions=tuple(data["original_dimensions"]),
                    provider_metadata=data.get("provider_metadata", {}),
                    created_at=created_at,
                )
                self._images[image_id] = record
                count += 1
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.warning("Skipping corrupt sidecar file: %s", sidecar_path)

        if count:
            logger.info("Loaded %d images from scratch directory", count)


_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _mime_to_ext(content_type: str) -> str:
    """Map MIME type to file extension."""
    return _MIME_TO_EXT.get(content_type, ".png")
