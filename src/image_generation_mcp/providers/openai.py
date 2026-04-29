"""OpenAI image generation provider.

Supports the ``gpt-image-*`` family (``gpt-image-1.5`` current flagship,
``gpt-image-1``/``gpt-image-1-mini`` legacy variants) and ``dall-e-3``
(deprecated, API removal scheduled 2026-05-12) plus ``dall-e-2`` (legacy,
inpainting-only). Lifecycle metadata flows through
``providers.model_styles.MODEL_STYLES`` into ``list_providers``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, NoReturn

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
    make_degraded,
)
from image_generation_mcp.providers.model_styles import resolve_style
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
    ProgressCallback,
)

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_GPT_IMAGE_SIZES: dict[str, str] = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}

_DALLE3_SIZES: dict[str, str] = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "3:2": "1792x1024",
    "2:3": "1024x1792",
}

_FORMAT_TO_CONTENT_TYPE: dict[str, str] = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

_DALLE3_FORMATS: frozenset[str] = frozenset({"png"})

_KNOWN_IMAGE_MODELS: frozenset[str] = frozenset(
    {
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-1.5",
        "dall-e-3",
        "dall-e-2",
    }
)


def _is_gpt_image_model(model: str) -> bool:
    """Return True for gpt-image-* models (not dall-e)."""
    return model.startswith("gpt-image")


class OpenAIImageProvider:
    """Image generation via OpenAI's Images API.

    Args:
        model: Model name (``gpt-image-1`` or ``dall-e-3``).
        api_key: OpenAI API key.
        output_format: Image format (``png``, ``jpeg``, ``webp``).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-image-1",
        output_format: str = "png",
    ) -> None:
        self._model = model
        self._output_format = output_format

        if output_format not in _FORMAT_TO_CONTENT_TYPE:
            supported = ", ".join(sorted(_FORMAT_TO_CONTENT_TYPE))
            raise ImageProviderError(
                "openai",
                f"Unsupported output_format '{output_format}'. Supported: {supported}",
            )

        self._is_gpt_image = _is_gpt_image_model(model)

        if not self._is_gpt_image and output_format not in _DALLE3_FORMATS:
            supported_dalle3 = ", ".join(sorted(_DALLE3_FORMATS))
            raise ImageProviderError(
                "openai",
                f"dall-e-3 does not support output_format '{output_format}'. "
                f"Supported: {supported_dalle3}",
            )

        self._client: AsyncOpenAI = self._create_client(api_key)

    def _create_client(self, api_key: str) -> AsyncOpenAI:
        """Create the AsyncOpenAI client (deferred import)."""
        try:
            from openai import AsyncOpenAI as _AsyncOpenAI
        except ImportError as e:
            raise ImageProviderError(
                "openai", "openai package not installed. Run: uv add openai"
            ) from e
        return _AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        progress_callback: ProgressCallback | None = None,  # noqa: ARG002
    ) -> ImageResult:
        """Generate an image via OpenAI Images API.

        Args:
            prompt: Positive text prompt.
            negative_prompt: Appended as ``"Avoid: ..."`` clause.
            aspect_ratio: Maps to OpenAI size parameter.
            quality: ``"standard"`` maps to ``"auto"`` for gpt-image-1
                (lets OpenAI choose). ``"hd"`` maps to ``"high"``.
            background: Background transparency (``opaque``, ``transparent``).
                Only supported for gpt-image-1; ignored for dall-e-3.
            model: Specific model to use for this call (e.g., ``"dall-e-3"``).
                Overrides the constructor model. Size table selection adjusts
                automatically.

        Returns:
            ImageResult with generated image.

        Raises:
            ImageProviderError: On API errors.
            ImageContentPolicyError: On content policy rejection.
            ImageProviderConnectionError: On network errors.
        """
        effective_model = model or self._model
        # NOTE: any model not matching 'gpt-image*' (e.g. dall-e-2) falls back to
        # DALL-E 3 sizes/format. Unknown models will fail at the API level.
        is_gpt_image = _is_gpt_image_model(effective_model)
        sizes = _GPT_IMAGE_SIZES if is_gpt_image else _DALLE3_SIZES
        # dall-e-3 only produces PNG; gpt-image-* uses configured format
        effective_format = self._output_format if is_gpt_image else "png"
        content_type = _FORMAT_TO_CONTENT_TYPE[effective_format]

        effective_prompt = prompt
        if negative_prompt:
            effective_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        api_quality = quality
        if is_gpt_image:
            api_quality = {"standard": "auto", "hd": "high"}.get(quality, quality)

        size = sizes.get(aspect_ratio)
        if size is None:
            supported = ", ".join(sorted(sizes))
            raise ImageProviderError(
                "openai",
                f"Unsupported aspect_ratio '{aspect_ratio}'. Supported: {supported}",
            )

        logger.debug(
            "OpenAI image generation: model=%s size=%s quality=%s",
            effective_model,
            size,
            api_quality,
        )

        try:
            api_kwargs: dict[str, Any] = {
                "model": effective_model,
                "prompt": effective_prompt,
                "n": 1,
                "size": size,
                "quality": api_quality,
            }
            if is_gpt_image:
                api_kwargs["output_format"] = effective_format
                api_kwargs["background"] = background
            else:
                api_kwargs["response_format"] = "b64_json"
                logger.debug("dall-e-3 does not support background parameter, ignoring")
            response = await self._client.images.generate(**api_kwargs)
        except ImageProviderError:
            raise
        except Exception as e:
            self._handle_error(e)

        if not response.data:
            raise ImageProviderError("openai", "Empty response from image API")

        image_item = response.data[0]
        b64_data = image_item.b64_json
        if not b64_data:
            raise ImageProviderError("openai", "No image data in response")

        metadata: dict[str, Any] = {
            "model": effective_model,
            "size": size,
            "quality": quality,
            "api_quality": api_quality,
        }
        revised_prompt = getattr(image_item, "revised_prompt", None)
        if revised_prompt:
            metadata["revised_prompt"] = revised_prompt

        logger.info("OpenAI image generated: model=%s size=%s", effective_model, size)

        return ImageResult.from_base64(
            b64_data,
            content_type=content_type,
            **metadata,
        )

    def _handle_error(self, error: Exception) -> NoReturn:
        """Convert OpenAI exceptions to ImageProvider exceptions."""
        from openai import APIConnectionError, APIStatusError

        if isinstance(error, APIConnectionError):
            raise ImageProviderConnectionError(
                "openai", f"Connection error: {error}"
            ) from error

        if isinstance(error, APIStatusError):
            status = error.status_code
            body = getattr(error, "body", None) or {}
            code = (
                body.get("error", {}).get("code", "") if isinstance(body, dict) else ""
            )
            if status == 400 and (
                code == "content_policy_violation"
                or "content_policy" in str(error).lower()
            ):
                raise ImageContentPolicyError(
                    "openai", f"Content policy rejection: {error}"
                ) from error
            raise ImageProviderError(
                "openai", f"API error (HTTP {status}): {error}"
            ) from error

        raise ImageProviderError(
            "openai", f"Image generation failed: {error}"
        ) from error

    async def discover_capabilities(self) -> ProviderCapabilities:
        """Discover OpenAI image model capabilities via models.list().

        Calls the OpenAI models API to enumerate available models, then filters
        to known image models and maps them to :class:`ModelCapabilities` using
        hardcoded knowledge about each model's feature set.

        Returns:
            ProviderCapabilities with one entry per discovered image model.
            If the API call fails, returns a degraded ProviderCapabilities with
            an empty model list and ``degraded=True``.
        """
        discovered_at = time.time()

        try:
            response = await self._client.models.list()
            model_ids = {m.id for m in response.data if m.id in _KNOWN_IMAGE_MODELS}
        except Exception:
            logger.warning(
                "OpenAI models.list() failed; returning degraded capabilities",
                exc_info=True,
            )
            return make_degraded("openai", discovered_at)

        model_caps: list[ModelCapabilities] = []

        # OpenAI has no native negative_prompt API parameter; the provider
        # implements it by appending 'Avoid: ...' to the prompt text, so
        # supports_negative_prompt remains False at the capability level.
        if "gpt-image-1" in model_ids:
            model_caps.append(
                ModelCapabilities(
                    model_id="gpt-image-1",
                    display_name="GPT Image 1",
                    can_generate=True,
                    can_edit=True,
                    supports_mask=True,
                    supports_background=True,
                    supports_negative_prompt=False,
                    supported_aspect_ratios=tuple(_GPT_IMAGE_SIZES),
                    supported_formats=("png", "jpeg", "webp"),
                    supported_qualities=("standard", "hd"),
                    max_resolution=1536,
                    style_profile=resolve_style("openai", "gpt-image-1"),
                )
            )

        # NOTE: capabilities for these models are assumed to match
        # gpt-image-1 — update once officially documented by OpenAI.
        for mini_model_id, mini_display in (
            ("gpt-image-1-mini", "GPT Image 1 Mini"),
            ("gpt-image-1.5", "GPT Image 1.5"),
        ):
            if mini_model_id in model_ids:
                model_caps.append(
                    ModelCapabilities(
                        model_id=mini_model_id,
                        display_name=mini_display,
                        can_generate=True,
                        can_edit=True,
                        supports_mask=True,
                        supports_background=True,
                        supports_negative_prompt=False,
                        supported_aspect_ratios=tuple(_GPT_IMAGE_SIZES),
                        supported_formats=("png", "jpeg", "webp"),
                        supported_qualities=("standard", "hd"),
                        max_resolution=1536,
                        style_profile=resolve_style("openai", mini_model_id),
                    )
                )

        if "dall-e-3" in model_ids:
            model_caps.append(
                ModelCapabilities(
                    model_id="dall-e-3",
                    display_name="DALL-E 3",
                    can_generate=True,
                    can_edit=False,
                    supports_mask=False,
                    supports_background=False,
                    supports_negative_prompt=False,
                    supported_aspect_ratios=tuple(_DALLE3_SIZES),
                    supported_formats=("png",),
                    supported_qualities=("standard", "hd"),
                    max_resolution=1792,
                    style_profile=resolve_style("openai", "dall-e-3"),
                )
            )

        if "dall-e-2" in model_ids:
            model_caps.append(
                ModelCapabilities(
                    model_id="dall-e-2",
                    display_name="DALL-E 2",
                    can_generate=True,
                    can_edit=True,
                    supports_mask=True,
                    supports_background=False,
                    supports_negative_prompt=False,
                    supported_aspect_ratios=("1:1",),
                    supported_formats=("png",),
                    supported_qualities=("standard",),
                    max_resolution=1024,
                    style_profile=resolve_style("openai", "dall-e-2"),
                )
            )

        return ProviderCapabilities(
            provider_name="openai",
            models=tuple(model_caps),
            discovered_at=discovered_at,
        )
