"""Tests for SD WebUI checkpoint discovery and _detect_architecture()."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from image_generation_mcp.providers.capabilities import ProviderCapabilities
from image_generation_mcp.providers.sd_webui import (
    _FLUX_DEV_PRESET,
    _FLUX_SCHNELL_PRESET,
    _SD15_PRESET,
    _SDXL_LIGHTNING_PRESET,
    _SDXL_PRESET,
    SdWebuiImageProvider,
    _detect_architecture,
    _resolve_preset,
)

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

_CHECKPOINT_FLUX_DEV = {
    "title": "flux1-dev-fp8.safetensors [aaa111]",
    "model_name": "flux1-dev-fp8",
    "hash": "aaa111",
}

_CHECKPOINT_FLUX_SCHNELL = {
    "title": "flux1-schnell-Q4.gguf [bbb222]",
    "model_name": "flux1-schnell-Q4",
    "hash": "bbb222",
}

_CHECKPOINTS_ALL_THREE = [_CHECKPOINT_SD15, _CHECKPOINT_SDXL, _CHECKPOINT_LIGHTNING]

_CHECKPOINTS_ALL_FIVE = [
    _CHECKPOINT_SD15,
    _CHECKPOINT_SDXL,
    _CHECKPOINT_LIGHTNING,
    _CHECKPOINT_FLUX_DEV,
    _CHECKPOINT_FLUX_SCHNELL,
]

_OPTIONS_RESPONSE = {
    "sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors [6ce0161689]"
}


def _make_provider() -> SdWebuiImageProvider:
    return SdWebuiImageProvider(host="http://localhost:7860")


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

    def test_flux_dev(self) -> None:
        assert _detect_architecture("flux1-dev-fp8.safetensors") == "flux_dev"

    def test_flux_schnell(self) -> None:
        assert _detect_architecture("flux1-schnell-Q4.gguf") == "flux_schnell"

    def test_flux_dev_uppercase(self) -> None:
        assert _detect_architecture("FLUX1-DEV-FP8") == "flux_dev"

    def test_flux_schnell_mixed_case(self) -> None:
        assert _detect_architecture("Flux1-Schnell-Q4") == "flux_schnell"

    def test_flux_without_schnell_is_dev(self) -> None:
        # "flux" without "schnell" → flux_dev
        assert _detect_architecture("flux_model_v2") == "flux_dev"

    def test_flux_takes_priority_over_xl(self) -> None:
        # Flux detection runs before XL detection
        assert _detect_architecture("flux_xl_hybrid") == "flux_dev"

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

    def test_sd15_sampler(self) -> None:
        assert _SD15_PRESET.sampler == "DPM++ 2M"

    def test_sd15_scheduler(self) -> None:
        assert _SD15_PRESET.scheduler == "Karras"

    def test_sdxl_sampler(self) -> None:
        assert _SDXL_PRESET.sampler == "DPM++ 2M"

    def test_sdxl_scheduler(self) -> None:
        assert _SDXL_PRESET.scheduler == "Karras"

    def test_lightning_sampler(self) -> None:
        assert _SDXL_LIGHTNING_PRESET.sampler == "DPM++ SDE"

    def test_lightning_scheduler(self) -> None:
        assert _SDXL_LIGHTNING_PRESET.scheduler == "Karras"

    def test_flux_dev_model(self) -> None:
        assert _resolve_preset("flux1-dev-fp8.safetensors") is _FLUX_DEV_PRESET

    def test_flux_schnell_model(self) -> None:
        assert _resolve_preset("flux1-schnell-Q4.gguf") is _FLUX_SCHNELL_PRESET

    def test_flux_dev_steps(self) -> None:
        assert _FLUX_DEV_PRESET.steps == 20

    def test_flux_schnell_steps(self) -> None:
        assert _FLUX_SCHNELL_PRESET.steps == 4

    def test_flux_dev_cfg(self) -> None:
        assert _FLUX_DEV_PRESET.cfg_scale == 1.0

    def test_flux_dev_sampler(self) -> None:
        assert _FLUX_DEV_PRESET.sampler == "Euler"

    def test_flux_dev_scheduler(self) -> None:
        assert _FLUX_DEV_PRESET.scheduler == "Simple"

    def test_flux_no_negative_prompt(self) -> None:
        assert _FLUX_DEV_PRESET.supports_negative_prompt is False
        assert _FLUX_SCHNELL_PRESET.supports_negative_prompt is False

    def test_flux_distilled_cfg(self) -> None:
        assert _FLUX_DEV_PRESET.distilled_cfg_scale == 3.5
        assert _FLUX_SCHNELL_PRESET.distilled_cfg_scale == 3.5


# -- txt2img payload includes scheduler field --------------------------------


def _make_txt2img_mock_response() -> MagicMock:
    """Build a minimal successful txt2img mock response."""
    import base64

    b64_image = base64.b64encode(b"fake-png").decode()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "images": [b64_image],
        "info": '{"seed": 42, "sd_model_name": "test-model"}',
    }
    return mock_response


class TestSdWebuiPayloadScheduler:
    """Verify the txt2img payload sends separate sampler and scheduler fields."""

    async def test_payload_has_scheduler_field(self) -> None:
        """The POST payload must include both sampler_name and scheduler."""
        provider = _make_provider()
        provider._client.post = AsyncMock(return_value=_make_txt2img_mock_response())

        await provider.generate("test prompt")

        payload = provider._client.post.call_args.kwargs["json"]
        assert "sampler_name" in payload
        assert "scheduler" in payload
        assert payload["sampler_name"] == "DPM++ 2M"
        assert payload["scheduler"] == "Karras"

    async def test_lightning_payload_scheduler(self) -> None:
        """Lightning preset sends DPM++ SDE sampler with Karras scheduler."""
        provider = SdWebuiImageProvider(
            host="http://localhost:7860", model="sdxl_lightning_4step"
        )
        provider._client.post = AsyncMock(return_value=_make_txt2img_mock_response())

        await provider.generate("test prompt")

        payload = provider._client.post.call_args.kwargs["json"]
        assert payload["sampler_name"] == "DPM++ SDE"
        assert payload["scheduler"] == "Karras"

    async def test_flux_payload_scheduler(self) -> None:
        """Flux preset sends Euler sampler with Simple scheduler."""
        provider = SdWebuiImageProvider(
            host="http://localhost:7860", model="flux1-dev-fp8.safetensors"
        )
        provider._client.post = AsyncMock(return_value=_make_txt2img_mock_response())

        await provider.generate("test prompt")

        payload = provider._client.post.call_args.kwargs["json"]
        assert payload["sampler_name"] == "Euler"
        assert payload["scheduler"] == "Simple"
        assert payload["cfg_scale"] == 1.0
        assert payload["distilled_cfg_scale"] == 3.5
        assert "negative_prompt" not in payload


# -- discover_capabilities() success path ------------------------------------


class TestSdWebuiDiscoverCapabilitiesSuccess:
    """Tests for successful capability discovery with 3 checkpoints."""

    async def test_returns_provider_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_THREE)
        caps = await provider.discover_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "sd_webui"
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
        assert sd15.prompt_style == "clip"
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
        assert sdxl.prompt_style == "clip"

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

    async def test_all_sd_models_negative_prompt(self) -> None:
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


class TestSdWebuiDiscoverActiveModel:
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
            logging.INFO, logger="image_generation_mcp.providers.sd_webui"
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


class TestSdWebuiDiscoverUnreachable:
    """Verify degraded result when SD WebUI is unreachable."""

    async def test_connect_error_returns_degraded(self) -> None:
        import httpx

        provider = _make_provider()

        provider._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.models == ()
        assert caps.provider_name == "sd_webui"

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
            logging.WARNING, logger="image_generation_mcp.providers.sd_webui"
        ):
            await provider.discover_capabilities()

        assert any(
            "unreachable" in record.message.lower()
            or "sd_webui" in record.message.lower()
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )


# -- Asymmetric failure tests -------------------------------------------------


class TestSdWebuiDiscoverAsymmetricFailure:
    """Verify degraded result when only one of the parallel requests fails."""

    async def test_sd_models_succeeds_options_connect_error_returns_degraded(
        self,
    ) -> None:
        """When /sd-models succeeds but /options raises ConnectError, return degraded."""
        import httpx

        provider = _make_provider()

        async def _dispatch(url: str, **kwargs: Any) -> MagicMock:  # noqa: ARG001
            if "sd-models" in url:
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = [_CHECKPOINT_SD15]
                return response
            raise httpx.ConnectError("Connection refused on options")

        provider._client.get = AsyncMock(side_effect=_dispatch)
        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.models == ()
        assert caps.provider_name == "sd_webui"


# -- Provider-level capability flags -----------------------------------------


class TestSdWebuiDiscoverProviderLevelFlags:
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
        assert caps.supports_negative_prompt is False


# -- Response validation tests -----------------------------------------------


class TestSdWebuiDiscoverResponseValidation:
    """Tests for defensive checks on unexpected API responses."""

    async def test_non_list_response_returns_degraded(self) -> None:
        """When /sdapi/v1/sd-models returns a dict instead of a list, mark degraded."""
        provider = _make_provider()

        async def _dispatch(url: str, **kwargs: Any) -> MagicMock:  # noqa: ARG001
            response = MagicMock()
            response.status_code = 200
            if "sd-models" in url:
                response.json.return_value = {"error": "unexpected"}
            elif "options" in url:
                response.json.return_value = _OPTIONS_RESPONSE
            return response

        provider._client.get = AsyncMock(side_effect=_dispatch)
        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.models == ()

    async def test_non_list_response_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-list response logs a warning with the type name."""
        provider = _make_provider()

        async def _dispatch(url: str, **kwargs: Any) -> MagicMock:  # noqa: ARG001
            response = MagicMock()
            response.status_code = 200
            if "sd-models" in url:
                response.json.return_value = {"error": "unexpected"}
            elif "options" in url:
                response.json.return_value = _OPTIONS_RESPONSE
            return response

        provider._client.get = AsyncMock(side_effect=_dispatch)

        with caplog.at_level(
            logging.WARNING, logger="image_generation_mcp.providers.sd_webui"
        ):
            await provider.discover_capabilities()

        assert any("unexpected type" in r.message.lower() for r in caplog.records)

    async def test_empty_title_checkpoint_skipped(self) -> None:
        """Checkpoints with empty titles are skipped."""
        provider = _make_provider()
        checkpoints = [
            {"title": "", "model_name": "no-title"},
            _CHECKPOINT_SD15,
        ]
        provider._client.get = _mock_get(checkpoints)
        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1
        assert caps.models[0].display_name == _CHECKPOINT_SD15["model_name"]

    async def test_missing_title_checkpoint_skipped(self) -> None:
        """Checkpoints with missing title key are skipped."""
        provider = _make_provider()
        checkpoints = [
            {"model_name": "no-title-key"},
            _CHECKPOINT_SD15,
        ]
        provider._client.get = _mock_get(checkpoints)
        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1


# -- Flux model discovery tests -----------------------------------------------


class TestSdWebuiDiscoverFluxModels:
    """Tests for Flux model discovery and capability reporting."""

    async def test_five_models_discovered(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_FIVE)
        caps = await provider.discover_capabilities()
        assert len(caps.models) == 5

    async def test_flux_dev_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_FIVE)
        caps = await provider.discover_capabilities()

        flux_dev = next(m for m in caps.models if "flux1-dev" in m.model_id)
        assert flux_dev.model_id == _CHECKPOINT_FLUX_DEV["title"]
        assert flux_dev.display_name == _CHECKPOINT_FLUX_DEV["model_name"]
        assert flux_dev.max_resolution == 1024
        assert flux_dev.default_steps == 20
        assert flux_dev.default_cfg == 1.0
        assert flux_dev.supports_negative_prompt is False
        assert flux_dev.prompt_style == "natural_language"

    async def test_flux_schnell_capabilities(self) -> None:
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_FIVE)
        caps = await provider.discover_capabilities()

        flux_schnell = next(m for m in caps.models if "schnell" in m.model_id)
        assert flux_schnell.model_id == _CHECKPOINT_FLUX_SCHNELL["title"]
        assert flux_schnell.display_name == _CHECKPOINT_FLUX_SCHNELL["model_name"]
        assert flux_schnell.max_resolution == 1024
        assert flux_schnell.default_steps == 4
        assert flux_schnell.default_cfg == 1.0
        assert flux_schnell.supports_negative_prompt is False
        assert flux_schnell.prompt_style == "natural_language"

    async def test_provider_supports_negative_prompt_mixed(self) -> None:
        """Provider-level flag is True when at least one model supports it."""
        provider = _make_provider()
        provider._client.get = _mock_get(_CHECKPOINTS_ALL_FIVE)
        caps = await provider.discover_capabilities()
        # SD15, SDXL, Lightning support it; Flux doesn't → provider says True
        assert caps.supports_negative_prompt is True

    async def test_flux_only_no_negative_prompt(self) -> None:
        """Provider-level flag is False when only Flux models are present."""
        provider = _make_provider()
        provider._client.get = _mock_get(
            [_CHECKPOINT_FLUX_DEV, _CHECKPOINT_FLUX_SCHNELL]
        )
        caps = await provider.discover_capabilities()
        assert caps.supports_negative_prompt is False
