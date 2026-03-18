"""Tests for the ImageService orchestrator."""

from __future__ import annotations

import pytest

from image_gen_mcp.providers.placeholder import PlaceholderImageProvider
from image_gen_mcp.providers.types import ImageProviderError, ImageResult
from image_gen_mcp.service import ImageService


@pytest.fixture
def scratch_dir(tmp_path):
    return tmp_path / "scratch"


@pytest.fixture
def service(scratch_dir):
    svc = ImageService(scratch_dir=scratch_dir)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


class TestProviderRegistry:
    """Tests for provider registration and listing."""

    def test_register_and_list(self, service: ImageService) -> None:
        providers = service.list_providers()
        assert "placeholder" in providers
        assert providers["placeholder"]["available"] is True

    def test_empty_registry(self, scratch_dir) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        assert svc.list_providers() == {}


class TestGenerate:
    """Tests for the generate method."""

    async def test_generate_with_explicit_provider(
        self, service: ImageService
    ) -> None:
        name, result = await service.generate("a cat", provider="placeholder")
        assert name == "placeholder"
        assert result.image_data
        assert result.content_type == "image/png"

    async def test_generate_auto_with_only_placeholder(
        self, service: ImageService
    ) -> None:
        name, result = await service.generate("a cat", provider="auto")
        assert name == "placeholder"
        assert result.image_data

    async def test_generate_unknown_provider_raises(
        self, service: ImageService
    ) -> None:
        with pytest.raises(ImageProviderError, match="not available"):
            await service.generate("test", provider="nonexistent")

    async def test_generate_no_providers_raises(self, scratch_dir) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        with pytest.raises(ImageProviderError, match="No providers available"):
            await svc.generate("test", provider="auto")

    async def test_generate_passes_params(self, service: ImageService) -> None:
        name, result = await service.generate(
            "test",
            provider="placeholder",
            negative_prompt="bad stuff",
            aspect_ratio="16:9",
            quality="hd",
        )
        assert name == "placeholder"
        assert result.provider_metadata["size"] == "640x360"


class TestScratchSave:
    """Tests for saving images to scratch directory."""

    async def test_save_creates_file(self, service: ImageService) -> None:
        _, result = await service.generate("test", provider="placeholder")
        path = service.save_to_scratch(result, "placeholder")
        assert path.exists()
        assert path.read_bytes() == result.image_data

    async def test_save_creates_scratch_dir(
        self, scratch_dir, service: ImageService
    ) -> None:
        assert not scratch_dir.exists()
        _, result = await service.generate("test", provider="placeholder")
        service.save_to_scratch(result, "placeholder")
        assert scratch_dir.exists()

    async def test_save_filename_format(self, service: ImageService) -> None:
        _, result = await service.generate("test", provider="placeholder")
        path = service.save_to_scratch(result, "placeholder")
        # Format: {timestamp}-{provider}-{hash}.png
        parts = path.stem.split("-")
        assert len(parts) >= 3
        assert "placeholder" in path.stem
        assert path.suffix == ".png"

    def test_get_image_base64(self, service: ImageService) -> None:
        result = ImageResult(image_data=b"hello")
        b64 = service.get_image_base64(result)
        assert b64 == "aGVsbG8="
