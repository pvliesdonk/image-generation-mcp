"""Automatic1111 (Stable Diffusion WebUI) image provider.

Generates images via the A1111 REST API (``/sdapi/v1/txt2img``).
Model-aware presets auto-detect SD 1.5, SDXL, and SDXL Lightning
from the checkpoint name.

Ported from questfoundry — prompt distillation removed entirely.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
    make_degraded,
)
from image_generation_mcp.providers.types import (
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 180.0  # SDXL at high res can be slow on consumer GPUs


# -- Model-aware generation presets -------------------------------------------


@dataclass(frozen=True)
class _A1111Preset:
    """Generation parameters tuned for a specific SD architecture.

    A1111 >=1.6 split the sampler and scheduler into separate API fields.
    Older versions used combined names like ``"DPM++ 2M Karras"``.
    """

    sizes: dict[str, tuple[int, int]] = field(repr=False)
    steps: int = 30
    sampler: str = "DPM++ 2M"
    scheduler: str = "Karras"
    cfg_scale: float = 7.0
    quality_tier: str = "medium"


_SD15_PRESET = _A1111Preset(
    sizes={
        "1:1": (768, 768),
        "16:9": (912, 512),
        "9:16": (512, 912),
        "3:2": (768, 512),
        "2:3": (512, 768),
    },
)

_SDXL_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "3:2": (1216, 832),
    "2:3": (832, 1216),
}

_SDXL_PRESET = _A1111Preset(
    sizes=_SDXL_SIZES,
    steps=35,
    sampler="DPM++ 2M",
    scheduler="Karras",
    cfg_scale=7.5,
    quality_tier="high",
)

_SDXL_LIGHTNING_PRESET = _A1111Preset(
    sizes=_SDXL_SIZES,
    steps=6,
    sampler="DPM++ SDE",
    scheduler="Karras",
    cfg_scale=2.0,
    quality_tier="high",
)

_XL_TAGS = ("sdxl", "xl_", "_xl", "-xl")
_LIGHTNING_TAGS = ("lightning", "turbo")


def _detect_architecture(model_name: str) -> str:
    """Detect SD architecture from a checkpoint name.

    Detection order:
    1. Lightning/Turbo SDXL — returns ``"sdxl_lightning"``
    2. Standard SDXL — returns ``"sdxl"``
    3. SD 1.5 fallback — returns ``"sd15"``

    Args:
        model_name: Checkpoint name or title string (case-insensitive).

    Returns:
        One of ``"sd15"``, ``"sdxl"``, or ``"sdxl_lightning"``.
    """
    lower = model_name.lower()
    is_xl = any(tag in lower for tag in _XL_TAGS)
    is_lightning = any(tag in lower for tag in _LIGHTNING_TAGS)
    if is_xl and is_lightning:
        return "sdxl_lightning"
    if is_xl:
        return "sdxl"
    return "sd15"


def _resolve_preset(model: str | None) -> _A1111Preset:
    """Choose generation preset based on checkpoint name.

    Detection order:
    1. Lightning/Turbo SDXL — low steps, low CFG
    2. Standard SDXL — matches xl tags
    3. SD 1.5 — fallback default
    """
    if not model:
        return _SD15_PRESET
    arch = _detect_architecture(model)
    if arch == "sdxl_lightning":
        return _SDXL_LIGHTNING_PRESET
    if arch == "sdxl":
        return _SDXL_PRESET
    return _SD15_PRESET


class A1111ImageProvider:
    """Image provider using Automatic1111 Stable Diffusion WebUI.

    Args:
        host: WebUI base URL (e.g., ``http://localhost:7860``).
        model: Optional SD checkpoint name for preset detection and
            checkpoint override.
    """

    def __init__(
        self,
        host: str,
        model: str | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._preset = _resolve_preset(model)
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",  # noqa: ARG002
        background: str = "opaque",
    ) -> ImageResult:
        """Generate an image via A1111 txt2img API.

        Args:
            prompt: Positive text prompt (SD tag format recommended).
            negative_prompt: Negative prompt (natively supported by SD).
            aspect_ratio: Desired aspect ratio.
            quality: Ignored — SD quality is controlled by steps/cfg.
            background: Ignored — A1111 does not support background
                transparency control.

        Returns:
            ImageResult with PNG data and provider metadata.

        Raises:
            ImageProviderConnectionError: If A1111 is unreachable.
            ImageProviderError: On API errors.
        """
        if background != "opaque":
            logger.debug(
                "A1111 does not support background transparency control, ignoring"
            )
        default_size = self._preset.sizes["1:1"]
        width, height = self._preset.sizes.get(aspect_ratio, default_size)

        payload: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "",
            "width": width,
            "height": height,
            "steps": self._preset.steps,
            "cfg_scale": self._preset.cfg_scale,
            "sampler_name": self._preset.sampler,
            "scheduler": self._preset.scheduler,
        }

        if self._model:
            payload["override_settings"] = {"sd_model_checkpoint": self._model}

        url = f"{self._host}/sdapi/v1/txt2img"

        logger.debug(
            "A1111 generate: host=%s model=%s size=%dx%d",
            self._host,
            self._model,
            width,
            height,
        )

        try:
            response = await self._client.post(url, json=payload)
        except httpx.ConnectError as e:
            raise ImageProviderConnectionError(
                "a1111", f"Cannot connect to A1111 at {self._host}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise ImageProviderConnectionError(
                "a1111",
                f"Request to A1111 timed out after {_DEFAULT_TIMEOUT}s: {e}",
            ) from e

        if response.status_code != 200:
            body_preview = response.text[:200]
            raise ImageProviderError(
                "a1111",
                f"A1111 returned HTTP {response.status_code}: {body_preview}",
            )

        data = response.json()
        images = data.get("images")
        if not images:
            raise ImageProviderError(
                "a1111",
                "A1111 response missing 'images' field or returned empty list",
            )

        # Extract seed and model name from response info
        seed = None
        active_model = self._model
        info_str = data.get("info")
        if info_str:
            try:
                info = json.loads(info_str) if isinstance(info_str, str) else info_str
                seed = info.get("seed")
                if not self._model:
                    active_model = info.get("sd_model_name")
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.warning(
                    "A1111 info parse failed: %s (preview: %s)",
                    e,
                    str(info_str)[:100],
                )

        metadata: dict[str, Any] = {
            "quality": self._preset.quality_tier,
            "model": active_model,
            "size": f"{width}x{height}",
            "steps": self._preset.steps,
        }
        if seed is not None:
            metadata["seed"] = seed

        logger.info(
            "A1111 image generated: model=%s size=%dx%d seed=%s",
            active_model,
            width,
            height,
            seed,
        )

        return ImageResult.from_base64(
            images[0],
            content_type="image/png",
            **metadata,
        )

    async def discover_capabilities(self) -> ProviderCapabilities:
        """Discover A1111 checkpoint capabilities via sd-models API.

        Calls ``GET /sdapi/v1/sd-models`` to enumerate installed checkpoints
        and ``GET /sdapi/v1/options`` to identify the currently active model.
        Architecture (SD1.5, SDXL, Lightning) is auto-detected from each
        checkpoint name to populate correct resolution and step defaults.

        Returns:
            ProviderCapabilities with one ModelCapabilities entry per
            checkpoint.  Returns a degraded ProviderCapabilities (empty
            model list, ``degraded=True``) if A1111 is unreachable.
        """
        discovered_at = time.time()

        try:
            models_response = await self._client.get(f"{self._host}/sdapi/v1/sd-models")
            options_response = await self._client.get(f"{self._host}/sdapi/v1/options")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(
                "A1111 unreachable during capability discovery at %s: %s",
                self._host,
                e,
            )
            return make_degraded("a1111", discovered_at)

        # Log the active checkpoint from /options
        if options_response.status_code == 200:
            options_data = options_response.json()
            active_checkpoint = options_data.get("sd_model_checkpoint")
            if active_checkpoint:
                logger.info("A1111 active checkpoint: %s", active_checkpoint)

        if models_response.status_code != 200:
            logger.warning(
                "A1111 /sdapi/v1/sd-models returned HTTP %d — marking degraded",
                models_response.status_code,
            )
            return make_degraded("a1111", discovered_at)

        raw = models_response.json()
        if not isinstance(raw, list):
            logger.warning(
                "A1111 /sdapi/v1/sd-models returned unexpected type %s — marking degraded",
                type(raw).__name__,
            )
            return make_degraded("a1111", discovered_at)
        checkpoints: list[dict[str, Any]] = raw
        model_caps: list[ModelCapabilities] = []

        for checkpoint in checkpoints:
            title: str = checkpoint.get("title", "")
            if not title:
                logger.debug("Skipping checkpoint with empty title: %r", checkpoint)
                continue
            model_name: str = checkpoint.get("model_name", title)

            arch = _detect_architecture(title)
            preset = _resolve_preset(title)

            max_resolution = 1024 if arch in ("sdxl", "sdxl_lightning") else 768

            model_caps.append(
                ModelCapabilities(
                    model_id=title,
                    display_name=model_name,
                    can_generate=True,
                    can_edit=False,
                    supports_mask=False,
                    supported_aspect_ratios=tuple(preset.sizes.keys()),
                    supported_qualities=("standard",),
                    supported_formats=("png",),
                    supports_negative_prompt=True,
                    supports_background=False,
                    max_resolution=max_resolution,
                    default_steps=preset.steps,
                    default_cfg=preset.cfg_scale,
                )
            )

        logger.info(
            "A1111 capability discovery complete: %d checkpoints found at %s",
            len(model_caps),
            self._host,
        )

        return ProviderCapabilities(
            provider_name="a1111",
            models=tuple(model_caps),
            supports_negative_prompt=True,
            supports_background=False,
            discovered_at=discovered_at,
        )
