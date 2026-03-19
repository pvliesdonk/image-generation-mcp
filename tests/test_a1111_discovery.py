"""Tests for A1111 checkpoint discovery and _detect_architecture()."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from image_generation_mcp.providers.a1111 import (
    _SD15_PRESET,
    _SDXL_LIGHTNING_PRESET,
    _SDXL_PRESET,
    A1111ImageProvider,
    _detect_architecture,
    _resolve_preset,
)
from image_generation_mcp.providers.capabilities import ProviderCapabilities

# -- Sample API payloads -------------------------------------------------------

_CHECKPOINT_SD15 = {
    "title": "v1-5-pruned-emaonly.safetensors [6ce0161689]",
    "model_name": "v1-5-pruned-emaonly",
    "hash": "6ce0161689",
}

_CHECKPOINT_SDXL = {
    "title": "sdxl_base_1.0.safetensors [abc123]",
    "model_name": "sdxl_base_1.0",
    "hash": "abc123",
}

_CHECKPOINT_LIGHTNING = {
    "title": "sdxl_lightning_4step.safetensors [def456]",
    "model_name": "sdxl_lightning_4step",
    "hash": "def456",
}

_CHECKPOINTS_ALL_THREE = [_CHECKPOINT_SD15, _CHECKPOINT_SDXL, _CHECKPOINT_LIGHTNING]

_OPTIONS_RESPONSE = {
    "sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors [6ce0161689]"
}


def _make_provider() -> A1111ImageProvider:
    return A1111ImageProvider(host="http://localhost:7860")


def _mock_get(
    checkpoints: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> AsyncMock:
    """Build a mock for provider._client.get that dispatches by URL."""
    if options is None:
        options = _OPTIONS_RESPONSE

    async def _dispatch(url: str, **kwargs: Any) -> MagicMock:  # noqa: ARG001
        response = MagicMock()
        response.status_code = 200
        if "sd-models" in url:
            response.json.return_value = checkpoints
        elif "options" in url:
            response.json.return_value = options
        else:
            response.status_code = 404
            response.json.return_value = {}
        return response

    return AsyncMock(side_effect=_dispatch)


# -- _detect_architecture() unit tests ----------------------------------------


class TestDetectArchitecture:
    """Unit tests for the extracted _detect_architecture() function."""

    def test_sd15_default(self) -> None:
        assert _detect_architecture("dreamshaper_8") == "sd15"

    def test_sd15_no_xl_tags(self) -> None:
        assert _detect_architecture("v1-5-pruned-emaonly") == "sd15"

    def test_sdxl_explicit_tag(self) -> None:
        assert _detect_architecture("sdxl_base_1.0") == "sdxl"

    def test_sdxl_xl_suffix(self) -> None:
        assert _detect_architecture("juggernaut_xl") == "sdxl"

    def test_sdxl_xl_prefix(self) -> None:
        assert _detect_architecture("xl_model_v2") == "sdxl"

    def test_sdxl_xl_hyphen(self) -> None:
        assert _detect_architecture("model-xl") == "sdxl"

    def test_sdxl_lightning(self) -> None:
        assert _detect_architecture("sdxl_lightning_4step") == "sdxl_lightning"

    def test_sdxl_turbo(self) -> None:
        assert _detect_architecture("sdxl_turbo") == "sdxl_lightning"

    def test_case_insensitive_sdxl(self) -> None:
        assert _detect_architecture("SDXL_Base") == "sdxl"

    def test_case_insensitive_lightning(self) -> None:
        assert _detect_architecture("SDXL_LIGHTNING_4step") == "sdxl_lightning"

    def test_lightning_without_xl_is_sd15(self) -> None:
        # "lightning" alone (no xl tag) → sd15
        assert _detect_architecture("dreamshaper_lightning") == "sd15"

    def test_returns_string(self) -> None:
        result = _detect_architecture("some_model")
        assert isinstance(result, str)


# -- _resolve_preset() regression tests ----------------------------------------


class TestResolvePresetStillWorks:
    """Regression tests ensuring refactored _resolve_preset produces identical presets."""

    def test_no_model_defaults_sd15(self) -> None:
        assert _resolve_preset(None) is _SD15_PRESET

    def test_unknown_model_defaults_sd15(self) -> None:
        assert _resolve_preset("dreamshaper_8") is _SD15_PRESET

    def test_sdxl_model(self) -> None:
        assert _resolve_preset("sdxl_base_1.0") is _SDXL_PRESET

    def test_xl_suffix(self) -> None:
        assert _resolve_preset("juggernaut_xl") is _SDXL_PRESET

    def test_xl_prefix(self) -> None:
        assert _resolve_preset("xl_model") is _SDXL_PRESET

    def test_lightning_sdxl(self) -> None:
        assert _resolve_preset("sdxl_lightning_4step") is _SDXL_LIGHTNING_PRESET

    def test_turbo_sdxl(self) -> None:
        assert _resolve_preset("sdxl_turbo") is _SDXL_LIGHTNING_PRESET

    def test_case_insensitive(self) -> None:
        assert _resolve_preset("SDXL_Base") is _SDXL_PRESET

    def test_sd15_steps(self) -> None:
        assert _SD15_PRESET.steps == 30

    def test_sdxl_steps(self) -> None:
        assert _SDXL_PRESET.steps == 35

    def test_lightning_steps(self) -> None:
        assert _SDXL_LIGHTNING_PRESET.steps == 6

    def test_sd15_cfg(self) -> None:
        assert _SD15_PRESET.cfg_scale == 7.0

    def test_sdxl_cfg(self) -> None:
        assert _SDXL_PRESET.cfg_scale == 7.5

    def test_lightning_cfg(self) -> None:
        assert _SDXL_LIGHTNING_PRESET.cfg_scale == 2.0


# -- discover_capabilities() success path ------------------------------------


class TestA1111DiscoverCapabilitiesSuccess:
    """Tests for successful capability discovery with 3 checkpoints."""

    async def test_returns_provider_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "a1111"
        assert caps.degraded is False

    async def test_three_models_discovered(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()
        assert len(caps.models) == 3

    async def test_sd15_model_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        sd15 = next(m for m in caps.models if "v1-5" in m.model_id)
        assert sd15.model_id == _CHECKPOINT_SD15["title"]
        assert sd15.display_name == _CHECKPOINT_SD15["model_name"]
        assert sd15.max_resolution == 768
        assert sd15.default_steps == 30
        assert sd15.default_cfg == 7.0
        assert "1:1" in sd15.supported_aspect_ratios
        assert "16:9" in sd15.supported_aspect_ratios

    async def test_sdxl_model_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        sdxl = next(m for m in caps.models if "sdxl_base" in m.model_id)
        assert sdxl.model_id == _CHECKPOINT_SDXL["title"]
        assert sdxl.display_name == _CHECKPOINT_SDXL["model_name"]
        assert sdxl.max_resolution == 1024
        assert sdxl.default_steps == 35
        assert sdxl.default_cfg == 7.5

    async def test_lightning_model_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        lightning = next(m for m in caps.models if "lightning" in m.model_id)
        assert lightning.model_id == _CHECKPOINT_LIGHTNING["title"]
        assert lightning.display_name == _CHECKPOINT_LIGHTNING["model_name"]
        assert lightning.max_resolution == 1024
        assert lightning.default_steps == 6
        assert lightning.default_cfg == 2.0

    async def test_all_models_can_generate(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.can_generate is True
            assert model.can_edit is False
            assert model.supports_mask is False

    async def test_all_models_negative_prompt(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_negative_prompt is True

    async def test_all_models_no_background(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_background is False

    async def test_all_models_standard_quality(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supported_qualities == ("standard",)

    async def test_all_models_png_format(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supported_formats == ("png",)

    async def test_discovered_at_is_set(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()
        assert caps.discovered_at > 0


# -- Active model logging test ------------------------------------------------


class TestA1111DiscoverActiveModel:
    """Verify active model is logged from /sdapi/v1/options."""

    async def test_active_model_logged_at_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(
            [_CHECKPOINT_SD15],
            options={
                "sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors [6ce0161689]"
            },
        )

        with caplog.at_level(
            logging.INFO, logger="image_generation_mcp.providers.a1111"
        ):
            await provider.discover_capabilities()

        assert any(
            "v1-5-pruned-emaonly.safetensors [6ce0161689]" in record.message
            for record in caplog.records
        )

    async def test_no_options_key_does_not_crash(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get([_CHECKPOINT_SD15], options={})
        caps = await provider.discover_capabilities()
        assert caps.degraded is False


# -- Unreachable provider test ------------------------------------------------


class TestA1111DiscoverUnreachable:
    """Verify degraded result when A1111 is unreachable."""

    async def test_connect_error_returns_degraded(self) -> None:
        import httpx

        provider = _make_provider()

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.models == ()
        assert caps.provider_name == "a1111"

    async def test_timeout_returns_degraded(self) -> None:
        import httpx

        provider = _make_provider()

        provider._client.get = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        caps = await provider.discover_capabilities()

        assert caps.degraded is True

    async def test_degraded_discovered_at_is_set(self) -> None:
        import httpx

        provider = _make_provider()

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        caps = await provider.discover_capabilities()

        assert caps.discovered_at > 0

    async def test_connect_error_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import httpx

        provider = _make_provider()

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with caplog.at_level(
            logging.WARNING, logger="image_generation_mcp.providers.a1111"
        ):
            await provider.discover_capabilities()

        assert any(
            "unreachable" in record.message.lower() or "a1111" in record.message.lower()
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )


# -- Provider-level capability flags -----------------------------------------


class TestA1111DiscoverProviderLevelFlags:
    """Verify provider-level supports_negative_prompt and supports_background."""

    async def test_supports_negative_prompt_true(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get([_CHECKPOINT_SD15])
        caps = await provider.discover_capabilities()
        assert caps.supports_negative_prompt is True

    async def test_supports_background_false(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get([_CHECKPOINT_SD15])
        caps = await provider.discover_capabilities()
        assert caps.supports_background is False

    async def test_empty_checkpoint_list(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get([])
        caps = await provider.discover_capabilities()
        assert caps.degraded is False
        assert caps.models == ()
        assert caps.supports_negative_prompt is True
