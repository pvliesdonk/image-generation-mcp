"""Tests for image resource templates -- view, metadata, list."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from image_gen_mcp.processing import convert_format
from image_gen_mcp.providers.placeholder import PlaceholderImageProvider
from image_gen_mcp.providers.types import ImageProviderError, ImageResult
from image_gen_mcp.service import ImageService


@pytest.fixture
async def image_result() -> ImageResult:
    """Generate a test image via PlaceholderImageProvider."""
    provider = PlaceholderImageProvider()
    return await provider.generate("resource test", aspect_ratio="16:9")


@pytest.fixture
def service(tmp_path: object) -> ImageService:
    """Create an ImageService with a temp scratch directory."""
    from pathlib import Path

    return ImageService(scratch_dir=Path(str(tmp_path)))


@pytest.fixture
def registered(
    service: ImageService, image_result: ImageResult
) -> tuple[ImageService, str]:
    """Register a test image and return (service, image_id)."""
    record = service.register_image(
        image_result, "placeholder", prompt="resource test"
    )
    return service, record.id


# --- image://{id}/view ---


def test_image_view_no_params_returns_original(
    registered: tuple[ImageService, str],
    image_result: ImageResult,
) -> None:
    """Reading view with no params returns original bytes."""
    service, image_id = registered
    record = service.get_image(image_id)
    data = record.original_path.read_bytes()
    assert data == image_result.image_data


def test_image_view_format_conversion(
    registered: tuple[ImageService, str],
) -> None:
    """Format conversion produces valid output."""
    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Convert to WebP
    data, content_type = convert_format(original, "webp")
    assert content_type == "image/webp"
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"


def test_image_view_resize(
    registered: tuple[ImageService, str],
) -> None:
    """Resize produces correct dimensions."""
    from image_gen_mcp.processing import crop_to_dimensions

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Crop to 200x200
    data = crop_to_dimensions(original, 200, 200)
    img = Image.open(io.BytesIO(data))
    assert img.size == (200, 200)


def test_image_view_proportional_resize_width(
    registered: tuple[ImageService, str],
) -> None:
    """Width-only resize preserves aspect ratio."""
    from image_gen_mcp.processing import resize_image

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Original is 640x360 (16:9), resize to width=320
    img = Image.open(io.BytesIO(original))
    ratio = 320 / img.width
    new_height = round(img.height * ratio)
    data = resize_image(original, 320, new_height)
    result_img = Image.open(io.BytesIO(data))
    assert result_img.width == 320
    assert result_img.height == new_height


def test_image_view_combined_params(
    registered: tuple[ImageService, str],
) -> None:
    """Format conversion + crop together."""
    from image_gen_mcp.processing import crop_to_dimensions

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Crop then convert
    cropped = crop_to_dimensions(original, 128, 128)
    data, content_type = convert_format(cropped, "jpeg")
    assert content_type == "image/jpeg"
    img = Image.open(io.BytesIO(data))
    assert img.size == (128, 128)


def test_image_view_unknown_id(service: ImageService) -> None:
    """get_image raises for nonexistent ID."""
    with pytest.raises(ImageProviderError, match="not found"):
        service.get_image("nonexistent_id")


# --- image://{id}/metadata ---


def test_metadata_resource_returns_json(
    registered: tuple[ImageService, str],
) -> None:
    """Metadata resource returns sidecar JSON content."""
    service, image_id = registered
    sidecar_path = service.scratch_dir / f"{image_id}.json"
    data = json.loads(sidecar_path.read_text())
    assert data["id"] == image_id
    assert data["prompt"] == "resource test"
    assert data["provider"] == "placeholder"
    assert "original_dimensions" in data
    assert "provider_metadata" in data
    assert "created_at" in data


def test_metadata_resource_not_found(service: ImageService) -> None:
    """Metadata for nonexistent ID raises error."""
    with pytest.raises(ImageProviderError, match="not found"):
        service.get_image("nonexistent_id")


# --- image://list ---


def test_image_list_resource(
    registered: tuple[ImageService, str],
) -> None:
    """list_images returns registered images."""
    service, image_id = registered
    images = service.list_images()
    assert len(images) == 1
    assert images[0].id == image_id
    assert images[0].provider == "placeholder"
    assert images[0].prompt == "resource test"
