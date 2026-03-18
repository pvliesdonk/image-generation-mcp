"""Image processing utilities --Pillow-based transforms for MCP resources.

Provides thumbnail generation, format conversion, resize/crop, and PNG
optimization.  All functions operate on raw ``bytes`` via ``io.BytesIO``
(no temp files) and return processed image data.
"""

from __future__ import annotations

import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)

_FORMAT_TO_MIME: dict[str, str] = {
    "png": "image/png",
    "webp": "image/webp",
    "jpeg": "image/jpeg",
}

_VALID_FORMATS = frozenset(_FORMAT_TO_MIME)


def _validate_format(fmt: str) -> str:
    """Normalise and validate an output format string.

    Returns:
        Normalised lowercase format string.

    Raises:
        ValueError: If *fmt* is not a supported format.
    """
    fmt_lower = fmt.lower()
    if fmt_lower not in _VALID_FORMATS:
        msg = f"Unsupported format {fmt!r}. Choose from: {sorted(_VALID_FORMATS)}"
        raise ValueError(msg)
    return fmt_lower


def _ensure_rgb(img: Image.Image, target_format: str) -> Image.Image:
    """Convert to RGB when saving to JPEG (handles RGBA, P, LA, and similar modes)."""
    if target_format == "jpeg" and img.mode not in ("RGB", "L"):
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            return background
        return img.convert("RGB")
    return img


def _save_kwargs(fmt_lower: str, quality: int) -> dict[str, object]:
    """Build keyword arguments for ``Image.save()`` based on format."""
    if fmt_lower == "png":
        return {"optimize": True}
    return {"quality": quality}


def generate_thumbnail(
    image_data: bytes,
    max_size: int = 256,
    fmt: str = "webp",
    quality: int = 80,
) -> tuple[bytes, str]:
    """Create a thumbnail that fits within a *max_size* x*max_size* box.

    Args:
        image_data: Source image bytes.
        max_size: Maximum dimension (width or height).
        fmt: Output format (``"png"``, ``"webp"``, ``"jpeg"``).
        quality: Compression quality (1-100, used by WebP/JPEG).

    Returns:
        Tuple of ``(thumbnail_bytes, content_type)``.

    Raises:
        ValueError: If *fmt* is not supported.
    """
    fmt_lower = _validate_format(fmt)
    img: Image.Image = Image.open(io.BytesIO(image_data))
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    img = _ensure_rgb(img, fmt_lower)

    buf = io.BytesIO()
    img.save(buf, format=fmt_lower, **_save_kwargs(fmt_lower, quality))
    return buf.getvalue(), _FORMAT_TO_MIME[fmt_lower]


def convert_format(
    image_data: bytes,
    fmt: str,
    quality: int = 90,
) -> tuple[bytes, str]:
    """Convert image data to a different format.

    Args:
        image_data: Source image bytes.
        fmt: Target format (``"png"``, ``"webp"``, ``"jpeg"``).
        quality: Compression quality (1-100, used by WebP/JPEG).

    Returns:
        Tuple of ``(converted_bytes, content_type)``.

    Raises:
        ValueError: If *fmt* is not supported.
    """
    fmt_lower = _validate_format(fmt)
    img: Image.Image = Image.open(io.BytesIO(image_data))
    img = _ensure_rgb(img, fmt_lower)

    buf = io.BytesIO()
    img.save(buf, format=fmt_lower, **_save_kwargs(fmt_lower, quality))
    return buf.getvalue(), _FORMAT_TO_MIME[fmt_lower]


def resize_image(image_data: bytes, width: int, height: int) -> bytes:
    """Resize an image to exact *width* x*height* dimensions.

    Uses LANCZOS resampling.  Does **not** preserve aspect ratio --the
    caller is responsible for choosing sensible dimensions.

    Args:
        image_data: Source image bytes.
        width: Target width in pixels.
        height: Target height in pixels.

    Returns:
        Resized image bytes in the same format as the source.
    """
    img: Image.Image = Image.open(io.BytesIO(image_data))
    src_format = img.format
    if not src_format:
        msg = "Could not determine source image format."
        raise ValueError(msg)
    img = img.resize((width, height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format=src_format)
    return buf.getvalue()


def crop_to_dimensions(image_data: bytes, width: int, height: int) -> bytes:
    """Center-crop an image to *width* x*height*.

    If the requested dimensions exceed the source, the image is scaled
    up to fill the target area before cropping.

    Args:
        image_data: Source image bytes.
        width: Target width in pixels.
        height: Target height in pixels.

    Returns:
        Cropped image bytes in the same format as the source.
    """
    img: Image.Image = Image.open(io.BytesIO(image_data))
    src_format = img.format
    if not src_format:
        msg = "Could not determine source image format."
        raise ValueError(msg)
    src_w, src_h = img.size

    # Scale up if source is smaller than target in either dimension
    scale = max(width / src_w, height / src_h)
    if scale > 1:
        img = img.resize(
            (round(src_w * scale), round(src_h * scale)),
            Image.Resampling.LANCZOS,
        )
        src_w, src_h = img.size

    # Center crop
    left = (src_w - width) // 2
    top = (src_h - height) // 2
    img = img.crop((left, top, left + width, top + height))

    buf = io.BytesIO()
    img.save(buf, format=src_format)
    return buf.getvalue()


def optimize_png(image_data: bytes) -> bytes:
    """Re-save a PNG with Pillow's ``optimize=True`` flag.

    Args:
        image_data: Source PNG bytes.

    Returns:
        Optimized PNG bytes.
    """
    img = Image.open(io.BytesIO(image_data))
    if img.format != "PNG":
        msg = f"optimize_png requires PNG input, got {img.format!r}"
        raise ValueError(msg)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
