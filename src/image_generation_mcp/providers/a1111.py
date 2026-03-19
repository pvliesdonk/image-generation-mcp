"""Automatic1111 (Stable Diffusion WebUI) image provider.

Generates images via the A1111 REST API (``/sdapi/v1/txt2img``).
Model-aware presets auto-detect SD 1.5, SDXL, and SDXL Lightning
from the checkpoint name.

Ported from questfoundry — prompt distillation removed entirely.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

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
    """Generation parameters tuned for a specific SD architecture."""

    sizes: dict[str, tuple[int, int]] = field(repr=False)
    steps: int = 30
    sampler: str = "DPM++ 2M Karras"
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
    sampler="DPM++ 2M Karras",
    cfg_scale=7.5,
    quality_tier="high",
)

_SDXL_LIGHTNING_PRESET = _A1111Preset(
    sizes=_SDXL_SIZES,
    steps=6,
    sampler="DPM++ SDE Karras",
    cfg_scale=2.0,
    quality_tier="high",
)

_XL_TAGS = ("sdxl", "xl_", "_xl", "-xl")
_LIGHTNING_TAGS = ("lightning", "turbo")


def _resolve_preset(model: str | None) -> _A1111Preset:
    """Choose generation preset based on checkpoint name.

    Detection order:
    1. Lightning/Turbo SDXL — low steps, low CFG
    2. Standard SDXL — matches xl tags
    3. SD 1.5 — fallback default
    """
    if not model:
        return _SD15_PRESET
    lower = model.lower()
    is_xl = any(tag in lower for tag in _XL_TAGS)
    is_lightning = any(tag in lower for tag in _LIGHTNING_TAGS)
    if is_xl and is_lightning:
        return _SDXL_LIGHTNING_PRESET
    if is_xl:
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
    ) -> ImageResult:
        """Generate an image via A1111 txt2img API.

        Args:
            prompt: Positive text prompt (SD tag format recommended).
            negative_prompt: Negative prompt (natively supported by SD).
            aspect_ratio: Desired aspect ratio.
            quality: Ignored — SD quality is controlled by steps/cfg.

        Returns:
            ImageResult with PNG data and provider metadata.

        Raises:
            ImageProviderConnectionError: If A1111 is unreachable.
            ImageProviderError: On API errors.
        """
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
