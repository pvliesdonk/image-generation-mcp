"""Tests for the Gemini image generation provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from image_generation_mcp.providers.gemini import (
    _ASPECT_RATIOS,
    _THINKING_MODELS,
    GeminiImageProvider,
)
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProvider,
    ImageProviderConnectionError,
    ImageProviderError,
)


@pytest.mark.usefixtures("_mock_genai")
class TestGeminiProvider:
    """Tests for GeminiImageProvider."""

    def test_implements_protocol(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        assert isinstance(provider, ImageProvider)

    def test_default_model(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        assert provider._model == "gemini-2.5-flash-image"

    def test_custom_model(self) -> None:
        provider = GeminiImageProvider(
            api_key="AIza-test", model="gemini-3-pro-image-preview"
        )
        assert provider._model == "gemini-3-pro-image-preview"

    def test_aspect_ratio_table_complete(self) -> None:
        for ratio in (
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
        ):
            assert ratio in _ASPECT_RATIOS

    async def test_generate_success(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", aspect_ratio="1:1")

        assert result.image_data == fake_image_bytes
        assert result.content_type == "image/png"
        assert result.provider_metadata["model"] == "gemini-2.5-flash-image"
        assert result.provider_metadata["quality"] == "standard"

    async def test_generate_hd_quality(self) -> None:
        """hd quality on a thinking model enables thinking, 2K, and TEXT+IMAGE."""
        provider = GeminiImageProvider(
            api_key="AIza-test", model="gemini-3.1-flash-image-preview"
        )
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", quality="hd")

        assert result.provider_metadata["quality"] == "hd"

        # Verify the config passed to generate_content
        from google.genai import types

        # response_modalities should be TEXT+IMAGE for hd
        types.GenerateContentConfig.assert_called_once()
        config_kwargs = types.GenerateContentConfig.call_args.kwargs
        assert config_kwargs["response_modalities"] == ["TEXT", "IMAGE"]

        # thinking_config should be set
        assert "thinking_config" in config_kwargs
        types.ThinkingConfig.assert_called_once_with(thinking_level="High")

        # image_size should be 2K
        types.ImageConfig.assert_called_once()
        image_config_kwargs = types.ImageConfig.call_args.kwargs
        assert image_config_kwargs["image_size"] == "2K"

    async def test_generate_standard_quality_config(self) -> None:
        """standard quality uses IMAGE-only, 1K, no thinking."""
        provider = GeminiImageProvider(
            api_key="AIza-test", model="gemini-3.1-flash-image-preview"
        )
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        await provider.generate("a cat", quality="standard")

        from google.genai import types

        config_kwargs = types.GenerateContentConfig.call_args.kwargs
        assert config_kwargs["response_modalities"] == ["IMAGE"]

        # No thinking_config for standard
        assert "thinking_config" not in config_kwargs

        # image_size should be 1K
        image_config_kwargs = types.ImageConfig.call_args.kwargs
        assert image_config_kwargs["image_size"] == "1K"

    async def test_hd_no_thinking_for_flash_image(self) -> None:
        """gemini-2.5-flash-image does not support thinking — hd skips it."""
        provider = GeminiImageProvider(
            api_key="AIza-test", model="gemini-2.5-flash-image"
        )
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", quality="hd")
        assert result.provider_metadata["quality"] == "hd"

        from google.genai import types

        config_kwargs = types.GenerateContentConfig.call_args.kwargs
        # Still gets TEXT+IMAGE and 2K for hd
        assert config_kwargs["response_modalities"] == ["TEXT", "IMAGE"]
        # But no thinking_config since model doesn't support it
        assert "thinking_config" not in config_kwargs

        image_config_kwargs = types.ImageConfig.call_args.kwargs
        assert image_config_kwargs["image_size"] == "2K"

    async def test_thinking_models_set(self) -> None:
        """Verify the thinking models set is correct."""
        assert "gemini-3.1-flash-image-preview" in _THINKING_MODELS
        assert "gemini-3-pro-image-preview" in _THINKING_MODELS
        assert "gemini-2.5-flash-image" not in _THINKING_MODELS

    async def test_generate_uses_model_override(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", model="gemini-3-pro-image-preview")

        call_kwargs = provider._client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-pro-image-preview"
        assert result.provider_metadata["model"] == "gemini-3-pro-image-preview"

    async def test_negative_prompt_appended(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        await provider.generate("a cat", negative_prompt="dogs")

        call_kwargs = provider._client.aio.models.generate_content.call_args.kwargs
        assert "Avoid: dogs" in call_kwargs["contents"]

    async def test_unsupported_aspect_ratio_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        with pytest.raises(ImageProviderError, match="Unsupported aspect_ratio"):
            await provider.generate("test", aspect_ratio="7:3")

    async def test_no_image_in_response_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_part = MagicMock()
        mock_part.inline_data = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_empty_parts_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_response = MagicMock()
        mock_response.parts = []

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_none_parts_raises(self) -> None:
        """response.parts=None (possible from SDK) raises ImageProviderError."""
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_response = MagicMock()
        mock_response.parts = None

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_api_error_raises_provider_error(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("some API error")
        )

        with pytest.raises(ImageProviderError):
            await provider.generate("test")

    async def test_content_policy_error(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("SAFETY blocked by content policy")
        )

        with pytest.raises(ImageContentPolicyError):
            await provider.generate("test")

    async def test_background_transparent_ignored(self) -> None:
        """background='transparent' is silently ignored — Gemini doesn't support it."""
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", background="transparent")
        assert result.image_data == fake_image_bytes

    async def test_aspect_ratio_passed_to_api(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", aspect_ratio="16:9")

        assert result.provider_metadata["aspect_ratio"] == "16:9"

    async def test_connection_error_raises_provider_connection_error(self) -> None:
        import httpx

        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(ImageProviderConnectionError):
            await provider.generate("test")

    async def test_non_bytes_inline_data_skipped(self) -> None:
        """If inline_data.data is not bytes, the part is skipped → no image error."""
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_inline = MagicMock()
        mock_inline.data = None  # not bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_connection_error_by_type_name(self) -> None:
        """Errors with 'connection' or 'timeout' in the type name are connection errors."""

        class FakeTimeoutError(Exception):
            pass

        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=FakeTimeoutError("deadline exceeded")
        )

        with pytest.raises(ImageProviderConnectionError):
            await provider.generate("test")
