"""Tests for the base64 ingest helper (issue #309)."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from image_generation_mcp._base64_image import _normalize_base64, base64_into_gallery
from image_generation_mcp._input_images import InvalidInputImage
from image_generation_mcp.domain import ImageService


def test_normalize_strips_data_uri_prefix() -> None:
    assert _normalize_base64("data:image/png;base64,aGVsbG8=") == "aGVsbG8="


def test_normalize_strips_whitespace_and_newlines() -> None:
    assert _normalize_base64("aGVs\n bG8=\r\n") == "aGVsbG8="


def test_normalize_leaves_raw_base64_unchanged() -> None:
    assert _normalize_base64("aGVsbG8=") == "aGVsbG8="


def _png_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def service(tmp_path) -> ImageService:
    return ImageService(scratch_dir=tmp_path)


async def test_ingest_success_registers_imported(service: ImageService) -> None:
    record = base64_into_gallery(service, _png_b64(), max_bytes=1_000_000)
    assert record.origin == "imported"
    assert record.origin_source == "base64"


async def test_ingest_accepts_data_uri(service: ImageService) -> None:
    record = base64_into_gallery(
        service, "data:image/png;base64," + _png_b64(), max_bytes=1_000_000
    )
    assert record.origin == "imported"


async def test_ingest_accepts_whitespace_wrapped(service: ImageService) -> None:
    wrapped = "\n".join(_png_b64()[i : i + 16] for i in range(0, len(_png_b64()), 16))
    record = base64_into_gallery(service, wrapped, max_bytes=1_000_000)
    assert record.origin == "imported"


async def test_ingest_malformed_raises_valueerror(service: ImageService) -> None:
    with pytest.raises(ValueError):
        base64_into_gallery(service, "@@@@not-base64@@@@", max_bytes=1_000_000)


async def test_ingest_oversized_raises_valueerror(service: ImageService) -> None:
    big = base64.b64encode(b"x" * 200).decode()
    with pytest.raises(ValueError):
        base64_into_gallery(service, big, max_bytes=10)


async def test_ingest_non_image_raises_invalid(service: ImageService) -> None:
    not_image = base64.b64encode(b"this is not an image").decode()
    with pytest.raises(InvalidInputImage):
        base64_into_gallery(service, not_image, max_bytes=1_000_000)
