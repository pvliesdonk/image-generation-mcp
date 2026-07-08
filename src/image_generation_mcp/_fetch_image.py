"""Fetch a caller-supplied image URL into the gallery (issue #308).

Wraps pvl-core's SSRF-hardened ``fetch_url``: pull the bytes at an http(s) URL
(private/loopback/metadata targets rejected, redirects refused, size-capped) and
register them as an ``imported`` gallery entry. Stored provenance is redacted
(userinfo + query dropped) so a secret-bearing URL never persists to the sidecar.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def _redact_fetch_url(url: str) -> str:
    """Return *url* with userinfo, query, and fragment stripped.

    Provenance must not persist secrets (``user:pass@`` / ``?token=…``); keep
    only ``scheme://host[:port]/path``. An IPv6-literal host is re-bracketed
    (``urlparse`` hands it back unbracketed).
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))
