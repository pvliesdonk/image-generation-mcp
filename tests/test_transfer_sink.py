"""Tests for GalleryTransferSink (issue #307).

The sink + validator are the domain hooks pvl-core's ``register_transfer_routes``
consumes: download serves a gallery image's bytes; upload ingests bytes as an
imported gallery entry.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from image_generation_mcp._input_images import InvalidInputImage
from image_generation_mcp._transfer_sink import GalleryTransferSink
from image_generation_mcp.config import ProjectConfig
from image_generation_mcp.domain import ImageService
from image_generation_mcp.providers.types import ImageProviderError, ImageResult

if TYPE_CHECKING:
    from pathlib import Path


def _png_bytes(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    return ImageService(scratch_dir=tmp_path)


@pytest.fixture
def sink(service: ImageService, tmp_path: Path) -> GalleryTransferSink:
    config = ProjectConfig(scratch_dir=tmp_path)
    return GalleryTransferSink(config, service_provider=lambda: service)


@pytest.fixture
def generated_id(service: ImageService) -> str:
    record = service.register_image(
        ImageResult(image_data=_png_bytes(), content_type="image/png"),
        "placeholder",
        prompt="p",
    )
    return record.id


# --- validate -------------------------------------------------------------


async def test_validate_download_existing_returns_id(
    sink: GalleryTransferSink, generated_id: str
) -> None:
    assert (
        await sink.validate(f"image://{generated_id}/view", "download") == generated_id
    )


async def test_validate_download_bare_id(
    sink: GalleryTransferSink, generated_id: str
) -> None:
    assert await sink.validate(generated_id, "download") == generated_id


async def test_validate_download_unknown_raises(sink: GalleryTransferSink) -> None:
    with pytest.raises(ImageProviderError):
        await sink.validate("image://abcdef012345/view", "download")


async def test_validate_download_invalid_ref_raises(sink: GalleryTransferSink) -> None:
    with pytest.raises(ValueError, match="Invalid image reference"):
        await sink.validate("not-an-image-ref", "download")


async def test_validate_upload_image_extension(sink: GalleryTransferSink) -> None:
    assert await sink.validate("photo.png", "upload") == "upload"


async def test_validate_upload_no_extension(sink: GalleryTransferSink) -> None:
    assert await sink.validate("clipboard", "upload") == "upload"


async def test_validate_upload_non_image_extension_raises(
    sink: GalleryTransferSink,
) -> None:
    with pytest.raises(ValueError, match="Unsupported upload type"):
        await sink.validate("report.pdf", "upload")


# --- read (download) ------------------------------------------------------


async def test_read_serves_image_bytes(
    sink: GalleryTransferSink, service: ImageService, generated_id: str
) -> None:
    result = await sink.read(generated_id)
    assert result.body == service.get_image(generated_id).original_path.read_bytes()
    assert result.media_type == "image/png"
    assert result.filename == f"{generated_id}.png"


# --- write (upload) -------------------------------------------------------


async def test_write_registers_imported_image(
    sink: GalleryTransferSink, service: ImageService
) -> None:
    payload = await sink.write("upload", _png_bytes("blue"))
    image_id = payload["image_id"]
    assert payload["uri"] == f"image://{image_id}/view"
    assert payload["origin"] == "imported"

    record = service.get_image(image_id)
    assert record.origin == "imported"
    assert record.origin_source == "upload"
    assert record.provider == ""


async def test_write_non_image_bytes_raises(sink: GalleryTransferSink) -> None:
    with pytest.raises(InvalidInputImage):
        await sink.write("upload", b"not an image")
