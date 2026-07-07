"""Resolution of caller-supplied image references into raw bytes.

The single module that knows about input sources (gallery ids/URIs and
local file paths). Producing :class:`InputImage` values for providers.
Adding base64/URL sources later is localized here.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from image_generation_mcp.providers.types import InputImage

logger = logging.getLogger(__name__)

GalleryLoader = Callable[[str], tuple[bytes, str]]
"""Loads ``(data, content_type)`` for a gallery image id; raises KeyError if unknown."""

_IMAGE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_IMAGE_URI_RE = re.compile(r"^image://([0-9a-f]{12})(?:/.*)?$")

_PIL_FORMAT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


class ImageReferenceNotFound(Exception):
    """Raised when a gallery id is unknown or a file path does not exist."""

    def __init__(self, ref: str) -> None:
        super().__init__(
            f"Image reference {ref!r} not found. "
            "Use a gallery image_id (read image://list) or an existing file path."
        )


class LocalFileInputDisabled(Exception):
    """Raised when a file-path reference is given but file input is disabled."""

    def __init__(self, ref: str) -> None:
        super().__init__(
            f"Local file input is disabled; cannot read {ref!r}. "
            "Set IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT=true to enable "
            "(only when callers are trusted with server filesystem access)."
        )


class InputImageTooLarge(Exception):
    """Raised when a reference image exceeds the configured byte cap."""

    def __init__(self, ref: str, size: int, max_bytes: int) -> None:
        super().__init__(
            f"Image reference {ref!r} is {size} bytes; "
            f"exceeds the {max_bytes}-byte limit."
        )


class InvalidInputImage(Exception):
    """Raised when reference bytes cannot be decoded as an image."""

    def __init__(self, ref: str) -> None:
        super().__init__(f"Image reference {ref!r} is not a decodable image.")


def _parse_gallery_id(ref: str) -> str | None:
    """Return the gallery id for *ref*, or ``None`` if it is not a gallery ref."""
    uri_match = _IMAGE_URI_RE.match(ref)
    if uri_match:
        return uri_match.group(1)
    if _IMAGE_ID_RE.match(ref):
        return ref
    return None


def validate_image_bytes(
    data: bytes, *, max_bytes: int, ref: str = "<imported>"
) -> str:
    """Validate size and decodability of image bytes; return the resolved MIME.

    Shared by reference resolution (:func:`resolve_reference`) and gallery
    import (:meth:`ImageService.register_imported_image`).

    Args:
        data: Raw image bytes to validate.
        max_bytes: Maximum allowed byte size.
        ref: Label for error messages (a reference string or ``"<imported>"``).

    Returns:
        The MIME type derived from the PIL-detected image format.

    Raises:
        InputImageTooLarge: When ``len(data) > max_bytes``.
        InvalidInputImage: When the bytes are not a decodable image or the
            format is not in the supported MIME map (PNG, JPEG, WEBP).
    """
    if len(data) > max_bytes:
        raise InputImageTooLarge(ref, len(data), max_bytes)
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            fmt = img.format
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidInputImage(ref) from exc
    mime = _PIL_FORMAT_TO_MIME.get(fmt or "")
    if mime is None:
        raise InvalidInputImage(ref)
    return mime


def resolve_reference(
    ref: str,
    *,
    loader: GalleryLoader,
    allow_local_files: bool,
    max_bytes: int,
) -> InputImage:
    """Resolve a single image reference into an :class:`InputImage`.

    Args:
        ref: An ``image://`` URI, a 12-hex gallery id, or a local file path.
        loader: Loads ``(data, content_type)`` for a gallery id.
        allow_local_files: Whether file-path references may be read.
        max_bytes: Maximum allowed byte size for the resolved image.

    Returns:
        The resolved :class:`InputImage`.

    Raises:
        ImageReferenceNotFound: Unknown gallery id or missing file.
        LocalFileInputDisabled: File-path ref while file input is disabled.
        InputImageTooLarge: Resolved image exceeds ``max_bytes``.
        InvalidInputImage: Bytes are not a decodable image.
    """
    gallery_id = _parse_gallery_id(ref)
    if gallery_id is not None:
        try:
            data, _content_type = loader(gallery_id)
        except KeyError as exc:
            raise ImageReferenceNotFound(ref) from exc
        resolved_type = validate_image_bytes(data, max_bytes=max_bytes, ref=ref)
        return InputImage(data=data, content_type=resolved_type, source_id=gallery_id)

    if not allow_local_files:
        raise LocalFileInputDisabled(ref)
    path = Path(ref)
    if not path.is_file():
        raise ImageReferenceNotFound(ref)
    data = path.read_bytes()
    resolved_type = validate_image_bytes(data, max_bytes=max_bytes, ref=ref)
    logger.debug("resolved_file_reference path=%s bytes=%d", ref, len(data))
    return InputImage(data=data, content_type=resolved_type, source_id=None)


def resolve_references(
    refs: Sequence[str],
    *,
    loader: GalleryLoader,
    allow_local_files: bool,
    max_bytes: int,
) -> list[InputImage]:
    """Resolve a list of references, preserving order.

    Args:
        refs: References to resolve.
        loader: Loads ``(data, content_type)`` for a gallery id.
        allow_local_files: Whether file-path references may be read.
        max_bytes: Per-image maximum byte size.

    Returns:
        Resolved :class:`InputImage` values in input order.
    """
    return [
        resolve_reference(
            ref,
            loader=loader,
            allow_local_files=allow_local_files,
            max_bytes=max_bytes,
        )
        for ref in refs
    ]
