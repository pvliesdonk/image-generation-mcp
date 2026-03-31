"""Tests for GeminiImageProvider.discover_capabilities()."""

from __future__ import annotations

import time

import pytest

from image_generation_mcp.providers.capabilities import ProviderCapabilities
from image_generation_mcp.providers.gemini import (
    _KNOWN_IMAGE_MODELS,
    GeminiImageProvider,
)


class TestDiscoverCapabilities:
    """Tests for discover_capabilities()."""

    async def test_returns_known_models(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "gemini"
        assert caps.degraded is False
        assert len(caps.models) == len(_KNOWN_IMAGE_MODELS)

    async def test_model_ids_match_known_list(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        model_ids = {m.model_id for m in caps.models}
        expected = {mid for mid, _ in _KNOWN_IMAGE_MODELS}
        assert model_ids == expected

    async def test_models_support_all_aspect_ratios(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        expected_ratios = (
            "1:1",
            "16:9",
            "9:16",
            "3:2",
            "2:3",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "4:1",
            "1:4",
            "8:1",
            "1:8",
            "21:9",
        )
        for model in caps.models:
            for ratio in expected_ratios:
                assert ratio in model.supported_aspect_ratios

    async def test_models_have_no_background_support(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_background is False

    async def test_models_have_no_negative_prompt_support(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_negative_prompt is False

    async def test_models_use_natural_language_style(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        for model in caps.models:
            assert model.prompt_style == "natural_language"

    async def test_default_model_is_first(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        caps = await gemini_provider.discover_capabilities()

        assert caps.models[0].model_id == "gemini-2.5-flash-image"

    async def test_discovered_at_is_recent(
        self, gemini_provider: GeminiImageProvider
    ) -> None:
        before = time.time()
        caps = await gemini_provider.discover_capabilities()
        after = time.time()

        assert before <= caps.discovered_at <= after

    async def test_degraded_on_unexpected_exception(
        self, gemini_provider: GeminiImageProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If _KNOWN_IMAGE_MODELS is broken, returns degraded caps."""
        import image_generation_mcp.providers.gemini as gemini_mod

        monkeypatch.setattr(
            gemini_mod,
            "_KNOWN_IMAGE_MODELS",
            None,  # type: ignore[arg-type]
        )

        caps = await gemini_provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.provider_name == "gemini"
