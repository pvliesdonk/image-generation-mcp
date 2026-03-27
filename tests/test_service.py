"""Tests for the ImageService orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

import json

from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import ImageProviderError
from image_generation_mcp.service import ImageService


@pytest.fixture
def scratch_dir(tmp_path: Path) -> Path:
    return tmp_path / "scratch"


@pytest.fixture
def service(scratch_dir: Path) -> ImageService:
    svc = ImageService(scratch_dir=scratch_dir)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


class TestProviderRegistry:
    """Tests for provider registration and listing."""

    def test_register_and_list(self, service: ImageService) -> None:
        providers = service.list_providers()
        assert "placeholder" in providers
        assert providers["placeholder"]["available"] is True

    def test_empty_registry(self, scratch_dir: Path) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        assert svc.list_providers() == {}


class TestGenerate:
    """Tests for the generate method."""

    async def test_generate_with_explicit_provider(self, service: ImageService) -> None:
        name, result = await service.generate("a cat", provider="placeholder")
        assert name == "placeholder"
        assert result.image_data
        assert result.content_type == "image/png"

    async def test_generate_auto_with_only_placeholder(
        self, service: ImageService
    ) -> None:
        name, result = await service.generate("a cat")
        assert name == "placeholder"
        assert result.image_data

    async def test_generate_unknown_provider_raises(
        self, service: ImageService
    ) -> None:
        with pytest.raises(ImageProviderError, match="not available"):
            await service.generate("test", provider="nonexistent")

    async def test_generate_no_providers_raises(self, scratch_dir: Path) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        with pytest.raises(ImageProviderError, match="No providers are registered"):
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

    async def test_generate_passes_model_to_provider(
        self, service: ImageService
    ) -> None:
        """Service passes model= through to the provider (placeholder ignores it)."""
        name, result = await service.generate(
            "test",
            provider="placeholder",
            model="some-checkpoint",
        )
        assert name == "placeholder"
        # Placeholder ignores model, result is still valid
        assert result.image_data


# ---------------------------------------------------------------------------
# ImageRecord.source_image_id
# ---------------------------------------------------------------------------


async def test_source_image_id_defaults_none(tmp_path: Path) -> None:
    """ImageRecord.source_image_id defaults to None for normal images."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("test", aspect_ratio="1:1")
    svc = ImageService(scratch_dir=tmp_path)
    record = svc.register_image(result, "placeholder", prompt="test")
    assert record.source_image_id is None


async def test_source_image_id_persisted_in_sidecar(tmp_path: Path) -> None:
    """source_image_id is written to and read back from the sidecar JSON."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("test", aspect_ratio="1:1")
    svc = ImageService(scratch_dir=tmp_path)
    record = svc.register_image(
        result, "placeholder", prompt="test", source_image_id="abc123"
    )
    assert record.source_image_id == "abc123"

    # Check sidecar
    sidecar = json.loads((tmp_path / f"{record.id}.json").read_text())
    assert sidecar["source_image_id"] == "abc123"

    # Reload from disk
    svc2 = ImageService(scratch_dir=tmp_path)
    reloaded = svc2.get_image(record.id)
    assert reloaded.source_image_id == "abc123"
