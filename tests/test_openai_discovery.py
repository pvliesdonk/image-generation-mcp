"""Tests for OpenAIImageProvider.discover_capabilities()."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
)
from image_generation_mcp.providers.openai import OpenAIImageProvider


@pytest.fixture
def provider() -> OpenAIImageProvider:
    """OpenAIImageProvider with _create_client patched out."""
    with patch(
        "image_generation_mcp.providers.openai.OpenAIImageProvider._create_client"
    ):
        p = OpenAIImageProvider(api_key="sk-test")
    # Replace _client with a plain MagicMock so we can configure models.list
    p._client = MagicMock()
    return p


def _make_model(*model_ids: str) -> MagicMock:
    """Build a mock models.list() response with the given model IDs."""
    models = []
    for mid in model_ids:
        m = MagicMock()
        m.id = mid
        models.append(m)
    response = MagicMock()
    response.data = models
    return response


class TestDiscoverCapabilitiesSuccess:
    """Happy-path tests for discover_capabilities()."""

    async def test_openai_discover_capabilities_success(
        self, provider: OpenAIImageProvider
    ) -> None:
        """Returns 2 ModelCapabilities when gpt-image-1 and dall-e-3 are present."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-image-1", "dall-e-3")
        )

        caps = await provider.discover_capabilities()

        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "openai"
        assert caps.degraded is False
        assert len(caps.models) == 2
        model_ids = {m.model_id for m in caps.models}
        assert model_ids == {"gpt-image-1", "dall-e-3"}

    async def test_openai_discover_capabilities_filters_non_image(
        self, provider: OpenAIImageProvider
    ) -> None:
        """Non-image models (gpt-4o, text-embedding-3-small) are excluded."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-4o", "text-embedding-3-small", "gpt-image-1")
        )

        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1
        assert caps.models[0].model_id == "gpt-image-1"

    async def test_openai_discover_capabilities_no_image_models(
        self, provider: OpenAIImageProvider
    ) -> None:
        """Empty model list when no image models are in the response — not degraded."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-4o", "text-embedding-3-small")
        )

        caps = await provider.discover_capabilities()

        assert caps.degraded is False
        assert caps.models == ()
        assert caps.supports_background is False
        assert caps.supports_negative_prompt is False

    async def test_openai_discover_capabilities_api_failure(
        self, provider: OpenAIImageProvider, caplog: pytest.LogCaptureFixture
    ) -> None:
        """API error returns degraded=True, empty models, and logs a warning."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            side_effect=RuntimeError("network timeout")
        )

        with caplog.at_level(logging.WARNING):
            caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.models == ()
        assert caps.provider_name == "openai"
        assert any(
            "degraded" in record.message.lower() or "failed" in record.message.lower()
            for record in caplog.records
        )


class TestDiscoverGptImage1Fields:
    """Verify specific fields for the gpt-image-1 model entry."""

    async def test_openai_discover_gpt_image_1_fields(
        self, provider: OpenAIImageProvider
    ) -> None:
        """gpt-image-1 has the expected capability fields."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-image-1")
        )

        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1
        m = caps.models[0]
        assert isinstance(m, ModelCapabilities)
        assert m.model_id == "gpt-image-1"
        assert m.display_name == "GPT Image 1"
        assert m.can_generate is True
        assert m.can_edit is True
        assert m.supports_mask is True
        assert m.supports_background is True
        assert m.supports_negative_prompt is False
        assert "1:1" in m.supported_aspect_ratios
        assert "16:9" in m.supported_aspect_ratios
        assert "png" in m.supported_formats
        assert "jpeg" in m.supported_formats
        assert "webp" in m.supported_formats
        assert "standard" in m.supported_qualities
        assert "hd" in m.supported_qualities
        assert m.max_resolution == 1536


class TestDiscoverDalle3Fields:
    """Verify specific fields for the dall-e-3 model entry."""

    async def test_openai_discover_dalle3_fields(
        self, provider: OpenAIImageProvider
    ) -> None:
        """dall-e-3 has the expected capability fields."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(return_value=_make_model("dall-e-3"))

        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1
        m = caps.models[0]
        assert isinstance(m, ModelCapabilities)
        assert m.model_id == "dall-e-3"
        assert m.display_name == "DALL-E 3"
        assert m.can_generate is True
        assert m.can_edit is False
        assert m.supports_mask is False
        assert m.supports_background is False
        assert m.supports_negative_prompt is False
        assert "1:1" in m.supported_aspect_ratios
        assert "16:9" in m.supported_aspect_ratios
        assert m.supported_formats == ("png",)
        assert "standard" in m.supported_qualities
        assert "hd" in m.supported_qualities
        assert m.max_resolution == 1792


class TestDiscoverProviderLevelFlags:
    """Verify provider-level aggregate flags."""

    async def test_openai_discover_provider_level_flags(
        self, provider: OpenAIImageProvider
    ) -> None:
        """supports_background is True (gpt-image-1); supports_negative_prompt is False."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-image-1", "dall-e-3")
        )

        caps = await provider.discover_capabilities()

        assert caps.supports_background is True
        assert caps.supports_negative_prompt is False

    async def test_supports_background_false_when_only_dalle3(
        self, provider: OpenAIImageProvider
    ) -> None:
        """supports_background is False when only dall-e-3 is present."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(return_value=_make_model("dall-e-3"))

        caps = await provider.discover_capabilities()

        assert caps.supports_background is False
        assert caps.supports_negative_prompt is False

    async def test_discovered_at_is_set(self, provider: OpenAIImageProvider) -> None:
        """discovered_at is a positive unix timestamp."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(
            return_value=_make_model("gpt-image-1")
        )

        caps = await provider.discover_capabilities()

        assert caps.discovered_at > 0

    async def test_discovered_at_set_on_degraded(
        self, provider: OpenAIImageProvider
    ) -> None:
        """discovered_at is still set when discovery fails (degraded path)."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(side_effect=RuntimeError("auth error"))

        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.discovered_at > 0


class TestDiscoverDalle2Fields:
    """Verify specific fields for the dall-e-2 model entry."""

    async def test_dalle2_fields(self, provider: OpenAIImageProvider) -> None:
        """dall-e-2 has the expected capability fields."""
        provider._client.models = MagicMock()
        provider._client.models.list = AsyncMock(return_value=_make_model("dall-e-2"))

        caps = await provider.discover_capabilities()

        assert len(caps.models) == 1
        m = caps.models[0]
        assert m.model_id == "dall-e-2"
        assert m.display_name == "DALL-E 2"
        assert m.can_generate is True
        assert m.can_edit is True
        assert m.supports_mask is True
        assert m.supports_background is False
        assert m.supported_aspect_ratios == ("1:1",)
        assert m.supported_formats == ("png",)
        assert m.supported_qualities == ("standard",)
        assert m.max_resolution == 1024
