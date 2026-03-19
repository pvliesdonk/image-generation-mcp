"""Tests for image provider types, protocol, and exceptions."""

from __future__ import annotations

import base64

import pytest

from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProvider,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
)


class TestImageResult:
    """Tests for the ImageResult dataclass."""

    def test_creation_with_defaults(self) -> None:
        data = b"\x89PNG\r\n"
        result = ImageResult(image_data=data)
        assert result.image_data == data
        assert result.content_type == "image/png"
        assert result.provider_metadata == {}

    def test_creation_with_all_fields(self) -> None:
        data = b"\xff\xd8\xff"
        meta = {"model": "test", "seed": 42}
        result = ImageResult(
            image_data=data,
            content_type="image/jpeg",
            provider_metadata=meta,
        )
        assert result.content_type == "image/jpeg"
        assert result.provider_metadata["model"] == "test"
        assert result.provider_metadata["seed"] == 42

    def test_size_bytes(self) -> None:
        data = b"x" * 1024
        result = ImageResult(image_data=data)
        assert result.size_bytes == 1024

    def test_size_bytes_empty(self) -> None:
        result = ImageResult(image_data=b"")
        assert result.size_bytes == 0

    def test_from_base64(self) -> None:
        original = b"hello image data"
        b64 = base64.b64encode(original).decode()
        result = ImageResult.from_base64(b64, content_type="image/webp")
        assert result.image_data == original
        assert result.content_type == "image/webp"

    def test_from_base64_default_content_type(self) -> None:
        b64 = base64.b64encode(b"data").decode()
        result = ImageResult.from_base64(b64)
        assert result.content_type == "image/png"

    def test_from_base64_with_metadata(self) -> None:
        b64 = base64.b64encode(b"data").decode()
        result = ImageResult.from_base64(b64, model="gpt-image-1", size="1024x1024")
        assert result.provider_metadata["model"] == "gpt-image-1"
        assert result.provider_metadata["size"] == "1024x1024"

    def test_frozen(self) -> None:
        result = ImageResult(image_data=b"data")
        with pytest.raises(AttributeError):
            result.image_data = b"other"  # type: ignore[misc]


class TestImageProvider:
    """Tests for the ImageProvider protocol."""

    def test_protocol_isinstance_check(self) -> None:
        class _Good:
            async def generate(
                self,
                prompt: str,  # noqa: ARG002
                *,
                negative_prompt: str | None = None,  # noqa: ARG002
                aspect_ratio: str = "1:1",  # noqa: ARG002
                quality: str = "standard",  # noqa: ARG002
            ) -> ImageResult:
                return ImageResult(image_data=b"")

        assert isinstance(_Good(), ImageProvider)

    def test_non_provider_fails_isinstance(self) -> None:
        class _Bad:
            pass

        assert not isinstance(_Bad(), ImageProvider)


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_base_error(self) -> None:
        err = ImageProviderError("openai", "rate limited")
        assert err.provider == "openai"
        assert "[openai] rate limited" in str(err)

    def test_content_policy_is_provider_error(self) -> None:
        err = ImageContentPolicyError("openai", "rejected")
        assert isinstance(err, ImageProviderError)
        assert err.provider == "openai"

    def test_connection_error_is_provider_error(self) -> None:
        err = ImageProviderConnectionError("a1111", "unreachable")
        assert isinstance(err, ImageProviderError)
        assert err.provider == "a1111"

    def test_all_are_exceptions(self) -> None:
        for cls in (
            ImageProviderError,
            ImageContentPolicyError,
            ImageProviderConnectionError,
        ):
            assert issubclass(cls, Exception)
