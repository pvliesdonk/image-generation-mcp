"""Tests for the input-reference resolver."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from image_generation_mcp._input_images import (
    ImageReferenceNotFound,
    InputImageTooLarge,
    InvalidInputImage,
    LocalFileInputDisabled,
    resolve_reference,
    resolve_references,
)


def _png_bytes(color: str = "red", size: tuple[int, int] = (4, 4)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _loader_with(mapping: dict[str, tuple[bytes, str]]):
    def loader(image_id: str):
        if image_id not in mapping:
            raise KeyError(image_id)
        return mapping[image_id]

    return loader


def test_resolve_bare_image_id() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    img = resolve_reference(
        "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10_000
    )
    assert img.data == data
    assert img.source_id == "0123456789ab"


def test_resolve_image_uri() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    img = resolve_reference(
        "image://0123456789ab/view",
        loader=loader,
        allow_local_files=False,
        max_bytes=10_000,
    )
    assert img.source_id == "0123456789ab"


def test_unknown_gallery_id_raises() -> None:
    loader = _loader_with({})
    with pytest.raises(ImageReferenceNotFound):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10_000
        )


def test_file_path_rejected_when_disabled() -> None:
    loader = _loader_with({})
    with pytest.raises(LocalFileInputDisabled):
        resolve_reference(
            "/tmp/foo.png", loader=loader, allow_local_files=False, max_bytes=10_000
        )


def test_file_path_read_when_enabled(tmp_path) -> None:
    p = tmp_path / "ref.png"
    p.write_bytes(_png_bytes("blue"))
    loader = _loader_with({})
    img = resolve_reference(
        str(p), loader=loader, allow_local_files=True, max_bytes=10_000
    )
    assert img.source_id is None
    assert img.content_type == "image/png"


def test_missing_file_raises(tmp_path) -> None:
    loader = _loader_with({})
    with pytest.raises(ImageReferenceNotFound):
        resolve_reference(
            str(tmp_path / "nope.png"),
            loader=loader,
            allow_local_files=True,
            max_bytes=10_000,
        )


def test_oversized_image_rejected() -> None:
    data = _png_bytes(size=(64, 64))
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    with pytest.raises(InputImageTooLarge):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10
        )


def test_non_image_bytes_rejected(tmp_path) -> None:
    p = tmp_path / "bad.png"
    p.write_bytes(b"not an image")
    loader = _loader_with({})
    with pytest.raises(InvalidInputImage):
        resolve_reference(
            str(p), loader=loader, allow_local_files=True, max_bytes=10_000
        )


def test_resolve_references_multiple() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    imgs = resolve_references(
        ["0123456789ab", "image://0123456789ab/view"],
        loader=loader,
        allow_local_files=False,
        max_bytes=10_000,
    )
    assert len(imgs) == 2


def test_unknown_gallery_id_with_local_files_enabled() -> None:
    loader = _loader_with({})
    with pytest.raises(ImageReferenceNotFound):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=True, max_bytes=10_000
        )


def test_oversized_file_rejected(tmp_path) -> None:
    p = tmp_path / "big.png"
    p.write_bytes(_png_bytes(size=(64, 64)))
    loader = _loader_with({})
    with pytest.raises(InputImageTooLarge):
        resolve_reference(str(p), loader=loader, allow_local_files=True, max_bytes=10)


def test_gallery_non_image_bytes_rejected() -> None:
    loader = _loader_with({"0123456789ab": (b"not an image", "image/png")})
    with pytest.raises(InvalidInputImage):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10_000
        )
