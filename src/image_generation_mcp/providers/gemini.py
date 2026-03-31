"""Gemini image generation provider.

Uses the Gemini native generateContent API with responseModalities=["IMAGE"].
Requires the google-genai package (optional dependency).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, NoReturn

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
    make_degraded,
)
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
    ProgressCallback,
)

if TYPE_CHECKING:
    from google import genai as genai_type

logger = logging.getLogger(__name__)

# All 5 project aspect ratios are natively supported by Gemini — direct pass-through.
_ASPECT_RATIOS: dict[str, str] = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "3:2": "3:2",
    "2:3": "2:3",
}

# quality -> Gemini image_size
_QUALITY_SIZES: dict[str, str] = {
    "standard": "1K",
    "hd": "2K",
}

# Known Gemini image-capable models in preference order.
# Discovery returns this static list — models.list() does not reliably filter
# image-generation models, so we maintain the known set here.
_KNOWN_IMAGE_MODELS: list[tuple[str, str]] = [
    ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image"),
    ("gemini-3.1-flash-image-preview", "Gemini 3.1 Flash Image Preview"),
    ("gemini-3-pro-image-preview", "Gemini 3 Pro Image Preview"),
]

_SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "16:9", "9:16", "3:2", "2:3")
_SUPPORTED_QUALITIES: tuple[str, ...] = ("standard", "hd")


class GeminiImageProvider:
    """Image generation provider backed by the Gemini generateContent API.

    Uses the google-genai SDK with native image generation via
    ``responseModalities=["IMAGE"]``. Registered when
    ``IMAGE_GENERATION_MCP_GOOGLE_API_KEY`` is set.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-image",
    ) -> None:
        """Initialise the Gemini provider.

        Args:
            api_key: Google API key with Gemini access.
            model: Default model ID for image generation.
        """
        self._model = model
        self._client = self._create_client(api_key)

    def _create_client(self, api_key: str) -> genai_type.Client:
        """Create the google-genai client.

        Separated from ``__init__`` so tests can patch it without needing
        the real ``google-genai`` package installed.

        Args:
            api_key: Google API key.

        Returns:
            Initialised ``genai.Client``.
        """
        from google import genai

        return genai.Client(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageResult:
        """Generate an image using the Gemini generateContent API.

        Args:
            prompt: Positive text prompt.
            negative_prompt: Appended as ``"\\n\\nAvoid: {negative_prompt}"``
                (Gemini has no native negative prompt support).
            aspect_ratio: One of the 5 supported ratios.
            quality: ``"standard"`` maps to ``image_size="1K"``,
                ``"hd"`` maps to ``image_size="2K"``.
            background: Ignored — Gemini does not support transparent backgrounds.
            model: Override the default model for this call.
            progress_callback: Ignored — Gemini does not report progress.

        Returns:
            ImageResult with PNG image data.

        Raises:
            ImageProviderError: If generation fails or returns no image.
            ImageContentPolicyError: If the prompt violates content policy.
            ImageProviderConnectionError: If the Gemini API is unreachable.
        """
        from google.genai import types

        if aspect_ratio not in _ASPECT_RATIOS:
            raise ImageProviderError(
                "gemini",
                f"Unsupported aspect_ratio: {aspect_ratio!r}. "
                f"Supported: {sorted(_ASPECT_RATIOS)}",
            )

        effective_model = model or self._model
        image_size = _QUALITY_SIZES.get(quality, "1K")

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        if background == "transparent":
            logger.debug(
                "Gemini does not support transparent backgrounds; "
                "background parameter ignored"
            )

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_ASPECT_RATIOS[aspect_ratio],
                image_size=image_size,
            ),
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=effective_model,
                contents=full_prompt,
                config=config,
            )
        except Exception as exc:
            self._handle_error(exc)

        for part in response.parts:
            if part.inline_data is not None:
                return ImageResult(
                    image_data=part.inline_data.data,
                    content_type=part.inline_data.mime_type or "image/png",
                    provider_metadata={
                        "model": effective_model,
                        "quality": quality,
                        "image_size": image_size,
                        "aspect_ratio": aspect_ratio,
                    },
                )

        raise ImageProviderError("gemini", "No image in response")

    async def discover_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for known Gemini image-generation models.

        Uses a static known model list rather than calling models.list(),
        which does not reliably filter image-capable models.

        Returns:
            ProviderCapabilities with the known Gemini image models.
        """
        discovered_at = time.time()
        try:
            models = tuple(
                ModelCapabilities(
                    model_id=model_id,
                    display_name=display_name,
                    can_generate=True,
                    can_edit=False,
                    supported_aspect_ratios=_SUPPORTED_ASPECT_RATIOS,
                    supported_qualities=_SUPPORTED_QUALITIES,
                    supported_formats=("image/png",),
                    supports_negative_prompt=False,
                    supports_background=False,
                    prompt_style="natural_language",
                )
                for model_id, display_name in _KNOWN_IMAGE_MODELS
            )
            return ProviderCapabilities(
                provider_name="gemini",
                models=models,
                discovered_at=discovered_at,
                degraded=False,
            )
        except Exception:
            logger.exception("Gemini capability discovery failed")
            return make_degraded("gemini", discovered_at)

    def _handle_error(self, exc: Exception) -> NoReturn:
        """Convert exceptions to ImageProviderError subtypes.

        Args:
            exc: Exception raised by the Gemini API client.

        Raises:
            ImageContentPolicyError: For content policy / safety violations.
            ImageProviderConnectionError: For network / timeout errors.
            ImageProviderError: For all other failures.
        """
        import httpx

        exc_str = str(exc).lower()
        if any(kw in exc_str for kw in ("safety", "policy", "blocked", "harm")):
            raise ImageContentPolicyError("gemini", str(exc)) from exc
        if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
            raise ImageProviderConnectionError("gemini", str(exc)) from exc

        # Detect connection-like errors by type name (without hard google import)
        exc_type = type(exc).__name__.lower()
        if "connection" in exc_type or "timeout" in exc_type:
            raise ImageProviderConnectionError("gemini", str(exc)) from exc

        raise ImageProviderError("gemini", str(exc)) from exc
