"""Inline base64 image ingest into the gallery (issue #309).

Wraps pvl-core's ``decode_base64_capped`` (a strict, size-capped base64 decoder) and
registers the decoded bytes as an ``imported`` gallery entry. The primitive rejects
wrapped input (``validate=True``), so this module normalizes first — stripping a
``data:<type>;base64,`` URI prefix and any whitespace — which is the "unwrap first" the
primitive's contract expects of its caller.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_DATA_URI_PREFIX = re.compile(r"^data:[^,]*;base64,", re.IGNORECASE)


def _normalize_base64(data: str) -> str:
    """Return *data* as raw base64: strip a ``data:<type>;base64,`` prefix and whitespace.

    ``decode_base64_capped`` uses ``validate=True`` and rejects wrapped input, so a
    data-URI wrapper or line-wrapped (MIME) base64 must be unwrapped before decoding.
    """
    without_prefix = _DATA_URI_PREFIX.sub("", data, count=1)
    return "".join(without_prefix.split())
