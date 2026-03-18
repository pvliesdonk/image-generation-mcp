"""Image generation service — orchestrates providers and scratch storage.

The ``ImageService`` is the DI service object injected into MCP tools.
It holds registered providers, dispatches generation requests, and
saves generated images to the scratch directory.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from image_gen_mcp.providers.types import ImageProvider, ImageProviderError, ImageResult

logger = logging.getLogger(__name__)


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

    @property
    def scratch_dir(self) -> Path:
        """The scratch directory for saved images."""
        return self._scratch_dir

    def register_provider(self, name: str, provider: ImageProvider) -> None:
        """Register an image provider.

        Args:
            name: Provider name (e.g., ``"openai"``, ``"placeholder"``).
            provider: Provider instance implementing ``ImageProvider``.
        """
        self._providers[name] = provider
        logger.info("Registered image provider: %s", name)

    def list_providers(self) -> dict[str, dict[str, Any]]:
        """List registered providers with availability info.

        Returns:
            Dict of provider name → ``{available: True, description: str}``.
        """
        result: dict[str, dict[str, Any]] = {}
        for name, prov in self._providers.items():
            result[name] = {
                "available": True,
                "description": f"{type(prov).__name__} ({name})",
            }
        return result

    def _resolve_provider(self, provider: str) -> tuple[str, ImageProvider]:
        """Resolve a provider name to an instance.

        Args:
            provider: Provider name or ``"auto"``.

        Returns:
            Tuple of (resolved_name, provider_instance).

        Raises:
            ImageProviderError: If no matching provider is available.
        """
        if provider == "auto":
            # Simple fallback: first non-placeholder, then placeholder
            for name, prov in self._providers.items():
                if name != "placeholder":
                    return name, prov
            if "placeholder" in self._providers:
                return "placeholder", self._providers["placeholder"]
            raise ImageProviderError("auto", "No providers available")

        if provider not in self._providers:
            available = ", ".join(self._providers) or "none"
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
            provider or self._default_provider
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

    def save_to_scratch(self, result: ImageResult, provider_name: str) -> Path:
        """Save an image result to the scratch directory.

        Args:
            result: The image result to save.
            provider_name: Provider name for the filename.

        Returns:
            Path to the saved file.
        """
        self._scratch_dir.mkdir(parents=True, exist_ok=True)

        # Build filename: {timestamp}-{provider}-{hash}.png
        ts = int(time.time())
        content_hash = hashlib.sha256(result.image_data).hexdigest()[:8]
        ext = _mime_to_ext(result.content_type)
        filename = f"{ts}-{provider_name}-{content_hash}{ext}"

        path = self._scratch_dir / filename
        path.write_bytes(result.image_data)

        logger.info("Saved image to %s (%d bytes)", path, result.size_bytes)
        return path

    @staticmethod
    def get_image_base64(result: ImageResult) -> str:
        """Encode image data as base64 string.

        Args:
            result: The image result to encode.

        Returns:
            Base64-encoded string.
        """
        return base64.b64encode(result.image_data).decode("ascii")


_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _mime_to_ext(content_type: str) -> str:
    """Map MIME type to file extension."""
    return _MIME_TO_EXT.get(content_type, ".png")
