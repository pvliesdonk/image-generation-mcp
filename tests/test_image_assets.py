"""Tests for image asset model -- registry, sidecar files, startup rebuild."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from image_gen_mcp.providers.placeholder import PlaceholderImageProvider
from image_gen_mcp.providers.types import ImageProviderError, ImageResult
from image_gen_mcp.service import ImageRecord, ImageService


@pytest.fixture
async def image_result() -> ImageResult:
    """Generate a test image via PlaceholderImageProvider."""
    provider = PlaceholderImageProvider()
    return await provider.generate("test image", aspect_ratio="1:1")


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    """Create an ImageService with a temp scratch directory."""
    return ImageService(scratch_dir=tmp_path)


# --- register_image ---


def test_register_image_creates_file(
    service: ImageService, image_result: ImageResult
) -> None:
    """Registering an image saves the original to scratch."""
    record = service.register_image(
        image_result, "placeholder", prompt="test image"
    )
    assert record.original_path.exists()
    assert record.original_path.read_bytes() == image_result.image_data


def test_register_image_returns_record(
    service: ImageService, image_result: ImageResult
) -> None:
    """register_image returns an ImageRecord with correct fields."""
    record = service.register_image(
        image_result,
        "placeholder",
        prompt="test image",
        negative_prompt="blurry",
        aspect_ratio="1:1",
        quality="standard",
    )
    assert isinstance(record, ImageRecord)
    assert len(record.id) == 12
    assert record.provider == "placeholder"
    assert record.prompt == "test image"
    assert record.negative_prompt == "blurry"
    assert record.aspect_ratio == "1:1"
    assert record.quality == "standard"
    assert record.content_type == "image/png"
    assert record.original_dimensions == (256, 256)
    assert record.created_at > 0


def test_register_image_content_addressed(
    service: ImageService, image_result: ImageResult
) -> None:
    """Same image data produces the same ID."""
    r1 = service.register_image(
        image_result, "placeholder", prompt="first"
    )
    r2 = service.register_image(
        image_result, "placeholder", prompt="second"
    )
    assert r1.id == r2.id


# --- sidecar files ---


def test_sidecar_written_on_register(
    service: ImageService, image_result: ImageResult
) -> None:
    """Registering an image creates both original and sidecar JSON."""
    record = service.register_image(
        image_result, "placeholder", prompt="test image"
    )
    sidecar_path = service.scratch_dir / f"{record.id}.json"
    assert sidecar_path.exists()
    assert record.original_path.exists()


def test_sidecar_contains_prompt(
    service: ImageService, image_result: ImageResult
) -> None:
    """Sidecar JSON includes generation context."""
    record = service.register_image(
        image_result,
        "placeholder",
        prompt="a sunset over mountains",
        negative_prompt="blurry",
        aspect_ratio="16:9",
    )
    sidecar = json.loads(
        (service.scratch_dir / f"{record.id}.json").read_text()
    )
    assert sidecar["prompt"] == "a sunset over mountains"
    assert sidecar["negative_prompt"] == "blurry"
    assert sidecar["provider"] == "placeholder"
    assert sidecar["aspect_ratio"] == "16:9"


def test_sidecar_contains_provider_metadata(
    service: ImageService, image_result: ImageResult
) -> None:
    """Sidecar JSON includes provider-specific metadata."""
    record = service.register_image(
        image_result, "placeholder", prompt="test"
    )
    sidecar = json.loads(
        (service.scratch_dir / f"{record.id}.json").read_text()
    )
    assert "provider_metadata" in sidecar
    # Placeholder provider includes quality, size, color
    assert sidecar["provider_metadata"]["quality"] == "placeholder"


def test_sidecar_contains_dimensions(
    service: ImageService, image_result: ImageResult
) -> None:
    """Sidecar JSON includes original image dimensions."""
    record = service.register_image(
        image_result, "placeholder", prompt="test"
    )
    sidecar = json.loads(
        (service.scratch_dir / f"{record.id}.json").read_text()
    )
    assert sidecar["original_dimensions"] == [256, 256]


# --- get_image / list_images ---


def test_get_image_found(
    service: ImageService, image_result: ImageResult
) -> None:
    """get_image returns the registered record."""
    record = service.register_image(
        image_result, "placeholder", prompt="test"
    )
    found = service.get_image(record.id)
    assert found.id == record.id
    assert found.prompt == "test"


def test_get_image_not_found(service: ImageService) -> None:
    """get_image raises ImageProviderError for unknown ID."""
    with pytest.raises(ImageProviderError, match="not found"):
        service.get_image("nonexistent")


def test_list_images(
    service: ImageService, image_result: ImageResult
) -> None:
    """list_images returns all registered images."""
    service.register_image(image_result, "placeholder", prompt="test")
    images = service.list_images()
    assert len(images) == 1
    assert images[0].provider == "placeholder"


def test_list_images_empty(service: ImageService) -> None:
    """list_images returns empty list when no images registered."""
    assert service.list_images() == []


# --- startup rebuild ---


def test_registry_rebuild_on_startup(
    service: ImageService, image_result: ImageResult
) -> None:
    """A new ImageService loads existing sidecar files from scratch."""
    record = service.register_image(
        image_result, "placeholder", prompt="rebuild test"
    )

    # Create a fresh service pointing at the same scratch dir
    new_service = ImageService(scratch_dir=service.scratch_dir)
    rebuilt = new_service.get_image(record.id)
    assert rebuilt.id == record.id
    assert rebuilt.prompt == "rebuild test"
    assert rebuilt.provider == "placeholder"


def test_registry_rebuild_ignores_corrupt_json(
    service: ImageService, image_result: ImageResult
) -> None:
    """Corrupt sidecar files are logged and skipped."""
    service.register_image(
        image_result, "placeholder", prompt="good"
    )

    # Write a corrupt sidecar
    corrupt_path = service.scratch_dir / "corrupt.json"
    corrupt_path.write_text("{invalid json")

    # New service should load the valid image, skip corrupt
    new_service = ImageService(scratch_dir=service.scratch_dir)
    images = new_service.list_images()
    assert len(images) == 1
    assert images[0].prompt == "good"
