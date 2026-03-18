"""Tests for the OpenAI image provider."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from image_gen_mcp.providers.openai import (
    _DALLE3_SIZES,
    _GPT_IMAGE_SIZES,
    OpenAIImageProvider,
)
from image_gen_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProvider,
    ImageProviderConnectionError,
    ImageProviderError,
)


@pytest.fixture
def _mock_openai():
    """Patch openai imports so tests don't need the real package."""
    with patch("image_gen_mcp.providers.openai.OpenAIImageProvider._create_client"):
        yield


@pytest.mark.usefixtures("_mock_openai")
class TestOpenAIProvider:
    """Tests for OpenAIImageProvider."""

    def test_implements_protocol(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")
        assert isinstance(provider, ImageProvider)

    def test_default_model_is_gpt_image(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")
        assert provider._model == "gpt-image-1"
        assert provider._is_gpt_image is True

    def test_dalle3_model(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test", model="dall-e-3")
        assert provider._is_gpt_image is False
        assert provider._sizes is _DALLE3_SIZES

    def test_gpt_image_sizes(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")
        assert provider._sizes is _GPT_IMAGE_SIZES
        assert provider._sizes["1:1"] == "1024x1024"
        assert provider._sizes["16:9"] == "1536x1024"

    def test_dalle3_sizes(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test", model="dall-e-3")
        assert provider._sizes["16:9"] == "1792x1024"

    def test_unsupported_format_raises(self) -> None:
        with pytest.raises(ImageProviderError, match="Unsupported output_format"):
            OpenAIImageProvider(api_key="sk-test", output_format="gif")

    def test_dalle3_rejects_webp_format(self) -> None:
        with pytest.raises(ImageProviderError, match="dall-e-3 does not support"):
            OpenAIImageProvider(
                api_key="sk-test", model="dall-e-3", output_format="webp"
            )

    async def test_unsupported_aspect_ratio_raises(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")
        with pytest.raises(ImageProviderError, match="Unsupported aspect_ratio"):
            await provider.generate("test", aspect_ratio="7:3")

    async def test_generate_success(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        b64_image = base64.b64encode(b"fake-png-data").decode()
        mock_item = MagicMock()
        mock_item.b64_json = b64_image
        mock_item.revised_prompt = "enhanced prompt"

        mock_response = MagicMock()
        mock_response.data = [mock_item]

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(return_value=mock_response)

        result = await provider.generate("a cat", aspect_ratio="1:1")

        assert result.image_data == b"fake-png-data"
        assert result.content_type == "image/png"
        assert result.provider_metadata["model"] == "gpt-image-1"
        assert result.provider_metadata["quality"] == "standard"
        assert result.provider_metadata["api_quality"] == "high"
        assert result.provider_metadata["revised_prompt"] == "enhanced prompt"

    async def test_negative_prompt_appended(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        b64_image = base64.b64encode(b"data").decode()
        mock_item = MagicMock()
        mock_item.b64_json = b64_image
        mock_item.revised_prompt = None

        mock_response = MagicMock()
        mock_response.data = [mock_item]

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(return_value=mock_response)

        await provider.generate("a cat", negative_prompt="dogs")

        call_kwargs = provider._client.images.generate.call_args.kwargs
        assert "Avoid: dogs" in call_kwargs["prompt"]

    async def test_empty_response_raises(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        mock_response = MagicMock()
        mock_response.data = []

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(return_value=mock_response)

        with pytest.raises(ImageProviderError, match="Empty response"):
            await provider.generate("test")

    async def test_quality_mapping_for_gpt_image(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        b64_image = base64.b64encode(b"data").decode()
        mock_item = MagicMock()
        mock_item.b64_json = b64_image
        mock_item.revised_prompt = None
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(return_value=mock_response)

        await provider.generate("test", quality="standard")

        call_kwargs = provider._client.images.generate.call_args.kwargs
        assert call_kwargs["quality"] == "high"


class TestErrorHandling:
    """Tests for OpenAI error conversion."""

    @pytest.mark.usefixtures("_mock_openai")
    async def test_connection_error(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        from openai import APIConnectionError

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ImageProviderConnectionError):
            await provider.generate("test")

    @pytest.mark.usefixtures("_mock_openai")
    async def test_content_policy_error(self) -> None:
        provider = OpenAIImageProvider(api_key="sk-test")

        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"message": "content_policy"}}

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(
            side_effect=APIStatusError(
                message="content_policy violation",
                response=mock_response,
                body=None,
            )
        )

        with pytest.raises(ImageContentPolicyError):
            await provider.generate("test")

    @pytest.mark.usefixtures("_mock_openai")
    async def test_content_policy_error_structured_body(self) -> None:
        """Structured body[error][code] path triggers content policy error."""
        provider = OpenAIImageProvider(api_key="sk-test")

        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 400

        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.generate = AsyncMock(
            side_effect=APIStatusError(
                message="Your request was rejected",
                response=mock_response,
                body={
                    "error": {"code": "content_policy_violation", "message": "rejected"}
                },
            )
        )

        with pytest.raises(ImageContentPolicyError):
            await provider.generate("test")
