"""Tests for image processing utilities."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from image_gen_mcp.processing import (
    convert_format,
    crop_to_dimensions,
    generate_thumbnail,
    optimize_png,
    resize_image,
)
from image_gen_mcp.providers.placeholder import PlaceholderImageProvider


@pytest.fixture
async def png_256() -> bytes:
    """256x256 placeholder PNG."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("test image", aspect_ratio="1:1")
    return result.image_data


@pytest.fixture
async def png_640x360() -> bytes:
    """640x360 placeholder PNG (16:9)."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("wide image", aspect_ratio="16:9")
    return result.image_data


# --- generate_thumbnail ---


def test_generate_thumbnail_dimensions(png_256: bytes) -> None:
    """Thumbnail fits within the max_size box."""
    data, content_type = generate_thumbnail(png_256, max_size=64)
    img = Image.open(io.BytesIO(data))
    assert img.width <= 64
    assert img.height <= 64
    assert content_type == "image/webp"


def test_generate_thumbnail_non_square(png_640x360: bytes) -> None:
    """Thumbnail preserves aspect ratio for non-square input."""
    data, _ = generate_thumbnail(png_640x360, max_size=128)
    img = Image.open(io.BytesIO(data))
    assert img.width <= 128
    assert img.height <= 128
    # 16:9 → width should be larger than height
    assert img.width > img.height


def test_generate_thumbnail_formats(png_256: bytes) -> None:
    """Thumbnail can be generated in all supported formats."""
    for fmt, expected_mime in [
        ("webp", "image/webp"),
        ("png", "image/png"),
        ("jpeg", "image/jpeg"),
    ]:
        data, content_type = generate_thumbnail(png_256, max_size=64, fmt=fmt)
        assert content_type == expected_mime
        assert len(data) > 0


# --- convert_format ---


def test_convert_format_png_to_webp(png_256: bytes) -> None:
    """PNG → WebP conversion produces valid WebP output."""
    data, content_type = convert_format(png_256, "webp")
    assert content_type == "image/webp"
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"


def test_convert_format_rgba_to_jpeg(png_256: bytes) -> None:
    """RGBA → JPEG handles alpha channel removal."""
    # Create an RGBA image from the PNG
    img = Image.open(io.BytesIO(png_256)).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    rgba_png = buf.getvalue()

    data, content_type = convert_format(rgba_png, "jpeg")
    assert content_type == "image/jpeg"
    result_img = Image.open(io.BytesIO(data))
    assert result_img.mode == "RGB"


# --- optimize_png ---


def test_optimize_png_valid(png_256: bytes) -> None:
    """Optimized PNG is valid and not larger than input."""
    data = optimize_png(png_256)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert len(data) <= len(png_256)


# --- resize_image ---


def test_resize_exact_dimensions(png_256: bytes) -> None:
    """Resize produces exact target dimensions."""
    data = resize_image(png_256, 100, 50)
    img = Image.open(io.BytesIO(data))
    assert img.size == (100, 50)


def test_resize_preserves_format(png_256: bytes) -> None:
    """Resize preserves the source format."""
    data = resize_image(png_256, 100, 100)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"


# --- crop_to_dimensions ---


def test_crop_center_dimensions(png_640x360: bytes) -> None:
    """Center crop produces exact target dimensions."""
    data = crop_to_dimensions(png_640x360, 200, 200)
    img = Image.open(io.BytesIO(data))
    assert img.size == (200, 200)


def test_crop_larger_than_source(png_256: bytes) -> None:
    """Crop upscales when target exceeds source dimensions."""
    data = crop_to_dimensions(png_256, 300, 300)
    img = Image.open(io.BytesIO(data))
    assert img.size == (300, 300)


# --- validation ---


def test_invalid_format_raises() -> None:
    """Invalid format raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported format"):
        generate_thumbnail(b"", fmt="bmp")


def test_invalid_format_convert_raises(png_256: bytes) -> None:
    """Invalid format in convert_format raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported format"):
        convert_format(png_256, "tiff")
