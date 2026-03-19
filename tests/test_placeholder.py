"""Tests for the placeholder image provider."""

from __future__ import annotations

import pytest

from mcp_imagegen.providers.placeholder import PlaceholderImageProvider
from mcp_imagegen.providers.types import ImageProvider


class TestPlaceholderProvider:
    """Tests for PlaceholderImageProvider."""

    @pytest.fixture
    def provider(self) -> PlaceholderImageProvider:
        return PlaceholderImageProvider()

    async def test_implements_protocol(
        self, provider: PlaceholderImageProvider
    ) -> None:
        assert isinstance(provider, ImageProvider)

    async def test_generate_returns_image_result(
        self, provider: PlaceholderImageProvider
    ) -> None:
        result = await provider.generate("a cat")
        assert result.image_data
        assert result.content_type == "image/png"
        assert result.provider_metadata["quality"] == "placeholder"

    async def test_png_signature(self, provider: PlaceholderImageProvider) -> None:
        result = await provider.generate("test")
        assert result.image_data[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_deterministic_color(
        self, provider: PlaceholderImageProvider
    ) -> None:
        r1 = await provider.generate("same prompt")
        r2 = await provider.generate("same prompt")
        assert r1.provider_metadata["color"] == r2.provider_metadata["color"]

    async def test_different_prompts_can_differ(
        self, provider: PlaceholderImageProvider
    ) -> None:
        # Not guaranteed to differ for all pairs, but these two do
        r1 = await provider.generate("alpha")
        r2 = await provider.generate("beta")
        # At minimum, both produce valid results
        assert r1.image_data
        assert r2.image_data

    @pytest.mark.parametrize(
        "ratio,expected_size",
        [
            ("1:1", "256x256"),
            ("16:9", "640x360"),
            ("9:16", "360x640"),
            ("3:2", "480x320"),
            ("2:3", "320x480"),
        ],
    )
    async def test_aspect_ratios(
        self,
        provider: PlaceholderImageProvider,
        ratio: str,
        expected_size: str,
    ) -> None:
        result = await provider.generate("test", aspect_ratio=ratio)
        assert result.provider_metadata["size"] == expected_size

    async def test_unknown_aspect_ratio_falls_back(
        self, provider: PlaceholderImageProvider
    ) -> None:
        result = await provider.generate("test", aspect_ratio="7:3")
        assert result.provider_metadata["size"] == "256x256"
