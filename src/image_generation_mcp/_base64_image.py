"""Inline base64 image ingest into the gallery (issue #309).

Wraps pvl-core's ``decode_base64_capped`` (a strict, size-capped base64 decoder) and
registers the decoded bytes as an ``imported`` gallery entry via
``ImageService.register_imported_image``. The primitive rejects wrapped input
(``validate=True``), so this module normalizes first — stripping a
``data:<type>;base64,`` URI prefix and any whitespace — which is the "unwrap first" the
primitive's contract expects of its caller. ``base64_into_gallery`` composes
normalize -> decode -> register into the single entry point tools call.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from fastmcp_pvl_core import decode_base64_capped

if TYPE_CHECKING:
    from image_generation_mcp.domain import ImageRecord, ImageService

logger = logging.getLogger(__name__)

_DATA_URI_PREFIX = re.compile(r"^data:[^,]*;base64,", re.IGNORECASE)


def _normalize_base64(data: str) -> str:
    """Return *data* as raw base64: strip a ``data:<type>;base64,`` prefix and whitespace.

    ``decode_base64_capped`` uses ``validate=True`` and rejects wrapped input, so a
    data-URI wrapper or line-wrapped (MIME) base64 must be unwrapped before decoding.
    """
    without_prefix = _DATA_URI_PREFIX.sub("", data, count=1)
    return "".join(without_prefix.split())


def base64_into_gallery(
    service: ImageService, data: str, *, max_bytes: int
) -> ImageRecord:
    """Decode inline base64 *data* under a size cap and register it as an imported image.

    Args:
        service: The live ImageService.
        data: Inline base64 — raw, ``data:<type>;base64,`` URI, or whitespace-wrapped.
        max_bytes: Cap on the decoded byte size (also re-checked at registration).

    Returns:
        The created ImageRecord (``origin="imported"``, ``origin_source="base64"``).

    Raises:
        ValueError: Invalid base64, or a decoded size over *max_bytes* (from
            ``decode_base64_capped``).
        InvalidInputImage: The decoded bytes are not a decodable image.
        InputImageTooLarge: Defensive re-check at registration; unreachable while
            the decode cap and the registration cap are the same ``max_bytes``.
    """
    decoded = decode_base64_capped(_normalize_base64(data), max_bytes=max_bytes)
    record = service.register_imported_image(
        decoded, origin_source="base64", max_bytes=max_bytes
    )
    logger.info("base64_image_ingested image_id=%s bytes=%d", record.id, len(decoded))
    return record
