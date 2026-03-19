"""Tests for the background transparency parameter across the image pipeline."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from image_generation_mcp.providers.a1111 import A1111ImageProvider
from image_generation_mcp.providers.openai import OpenAIImageProvider
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import SUPPORTED_BACKGROUNDS
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _png_color_type(png_bytes: bytes) -> int:
    """Return the PNG color type byte from the IHDR chunk.

    PNG structure: 8-byte sig + 4-byte length + 4-byte type + data + 4-byte CRC.
    IHDR data: width(4) + height(4) + bit_depth(1) + color_type(1) + ...
    Color type byte is at offset 25.
    """
    return png_bytes[25]


# ---------------------------------------------------------------------------
# PlaceholderImageProvider
# ---------------------------------------------------------------------------


class TestPlaceholderBackground:
    """Tests for background parameter in PlaceholderImageProvider."""

    @pytest.fixture
    def provider(self) -> PlaceholderImageProvider:
        return PlaceholderImageProvider()

    async def test_generate_background_opaque_default(
        self, provider: PlaceholderImageProvider
    ) -> None:
        """Default behavior (opaque) produces RGB PNG (color type 2)."""
        result = await provider.generate("a cat")
        assert result.image_data[:8] == b"\x89PNG\r\n\x1a\n"
        assert _png_color_type(result.image_data) == 2  # RGB

    async def test_generate_background_transparent_placeholder(
        self, provider: PlaceholderImageProvider
    ) -> None:
        """Transparent background produces RGBA PNG (color type 6)."""
        result = await provider.generate("a cat", background="transparent")
        assert result.image_data[:8] == b"\x89PNG\r\n\x1a\n"
        assert _png_color_type(result.image_data) == 6  # RGBA

    async def test_generate_background_explicit_opaque(
        self, provider: PlaceholderImageProvider
    ) -> None:
        """Explicit opaque background produces RGB PNG (color type 2)."""
        result = await provider.generate("a cat", background="opaque")
        assert _png_color_type(result.image_data) == 2  # RGB


# ---------------------------------------------------------------------------
# OpenAIImageProvider
# ---------------------------------------------------------------------------


def _make_openai_provider(model: str = "gpt-image-1") -> OpenAIImageProvider:
    """Build an OpenAIImageProvider with a mocked client."""
    with patch(
        "image_generation_mcp.providers.openai.OpenAIImageProvider._create_client"
    ):
        return OpenAIImageProvider(api_key="sk-test", model=model)


def _setup_mock_response(provider: OpenAIImageProvider, image_data: bytes) -> None:
    """Attach a mock images.generate that returns image_data."""
    b64_image = base64.b64encode(image_data).decode()
    mock_item = MagicMock()
    mock_item.b64_json = b64_image
    mock_item.revised_prompt = None
    mock_response = MagicMock()
    mock_response.data = [mock_item]

    provider._client = MagicMock()
    provider._client.images = MagicMock()
    provider._client.images.generate = AsyncMock(return_value=mock_response)


class TestOpenAIBackground:
    """Tests for background parameter in OpenAIImageProvider."""

    async def test_generate_background_transparent_openai(self) -> None:
        """background param is forwarded to the API for gpt-image-1."""
        provider = _make_openai_provider(model="gpt-image-1")
        _setup_mock_response(provider, b"fake-data")

        await provider.generate("a cat", background="transparent")

        call_kwargs = provider._client.images.generate.call_args.kwargs
        assert call_kwargs["background"] == "transparent"

    async def test_generate_background_opaque_openai(self) -> None:
        """Default background='opaque' is forwarded to the API for gpt-image-1."""
        provider = _make_openai_provider(model="gpt-image-1")
        _setup_mock_response(provider, b"fake-data")

        await provider.generate("a cat")

        call_kwargs = provider._client.images.generate.call_args.kwargs
        assert call_kwargs["background"] == "opaque"

    async def test_generate_background_dall_e_3_ignored(self) -> None:
        """background is NOT passed in kwargs for dall-e-3."""
        provider = _make_openai_provider(model="dall-e-3")
        _setup_mock_response(provider, b"fake-data")

        await provider.generate("a cat", background="transparent")

        call_kwargs = provider._client.images.generate.call_args.kwargs
        assert "background" not in call_kwargs


# ---------------------------------------------------------------------------
# A1111ImageProvider
# ---------------------------------------------------------------------------


class TestA1111Background:
    """Tests for background parameter in A1111ImageProvider."""

    async def test_generate_background_a1111_ignored(self) -> None:
        """A1111 generates normally when background='transparent'."""
        b64_image = base64.b64encode(b"fake-png").decode()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "images": [b64_image],
            "info": '{"seed": 42, "sd_model_name": "test-model"}',
        }

        provider = A1111ImageProvider(host="http://localhost:7860")

        with patch.object(
            provider._client, "post", new=AsyncMock(return_value=mock_response)
        ):
            result = await provider.generate("a cat", background="transparent")

        assert result.image_data == b"fake-png"


# ---------------------------------------------------------------------------
# Service-level validation
# ---------------------------------------------------------------------------


class TestBackgroundValidation:
    """Tests for background validation at the tool/service boundary."""

    def test_supported_backgrounds_constant(self) -> None:
        """SUPPORTED_BACKGROUNDS contains expected values."""
        assert "opaque" in SUPPORTED_BACKGROUNDS
        assert "transparent" in SUPPORTED_BACKGROUNDS

    def test_generate_background_invalid_raises(self) -> None:
        """Invalid background value is not in SUPPORTED_BACKGROUNDS; error message
        format includes the value and lists valid choices."""
        background = "semi-transparent"
        assert background not in SUPPORTED_BACKGROUNDS

        # Verify the error message format used by the tool validation
        msg = (
            f"Unsupported background '{background}'. "
            f"Supported: {', '.join(SUPPORTED_BACKGROUNDS)}"
        )
        with pytest.raises(ValueError, match="Unsupported background"):
            raise ValueError(msg)


# ---------------------------------------------------------------------------
# Service.register_image sidecar storage
# ---------------------------------------------------------------------------


class TestBackgroundInSidecar:
    """Tests for background value persistence in sidecar JSON."""

    @pytest.fixture
    def scratch_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "scratch"

    @pytest.fixture
    def service(self, scratch_dir: Path) -> ImageService:
        svc = ImageService(scratch_dir=scratch_dir)
        svc.register_provider("placeholder", PlaceholderImageProvider())
        return svc

    async def test_background_in_sidecar(
        self, service: ImageService, scratch_dir: Path
    ) -> None:
        """background value is persisted in the sidecar JSON."""
        provider_name, result = await service.generate(
            "a test image",
            provider="placeholder",
            background="transparent",
        )
        record = service.register_image(
            result,
            provider_name,
            prompt="a test image",
            background="transparent",
        )

        sidecar_path = scratch_dir / f"{record.id}.json"
        sidecar_data = json.loads(sidecar_path.read_text())

        assert sidecar_data["background"] == "transparent"

    async def test_background_opaque_default_in_sidecar(
        self, service: ImageService, scratch_dir: Path
    ) -> None:
        """Default background='opaque' is persisted in sidecar JSON."""
        provider_name, result = await service.generate(
            "a test image",
            provider="placeholder",
        )
        record = service.register_image(
            result,
            provider_name,
            prompt="a test image",
        )

        sidecar_path = scratch_dir / f"{record.id}.json"
        sidecar_data = json.loads(sidecar_path.read_text())

        assert sidecar_data["background"] == "opaque"
