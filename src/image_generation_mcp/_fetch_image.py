"""Fetch a caller-supplied image URL into the gallery (issue #308).

Wraps pvl-core's SSRF-hardened ``fetch_url``: pull the bytes at an http(s) URL
(private/loopback/metadata targets rejected, redirects refused, size-capped) and
register them as an ``imported`` gallery entry. Stored provenance is redacted
(userinfo, query, and fragment dropped) so a secret-bearing URL never persists to
the sidecar.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from fastmcp_pvl_core import fetch_url

if TYPE_CHECKING:
    import httpx

    from image_generation_mcp.domain import ImageRecord, ImageService

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


async def fetch_image_into_gallery(
    service: ImageService,
    url: str,
    *,
    max_bytes: int,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ImageRecord:
    """Fetch *url* (SSRF-hardened) and register the bytes as an imported image.

    Args:
        service: The live ImageService.
        url: Caller-supplied http(s) URL.
        max_bytes: Size cap; the fetch aborts past it and the bytes are
            re-checked at registration.
        timeout_s: Overall fetch timeout in seconds.
        transport: Optional httpx transport (test injection); ``None`` = real
            networking.

    Returns:
        The created ImageRecord (``origin="imported"``,
        ``origin_source="fetch:<redacted-url>"``).

    Raises:
        ValueError: SSRF-blocked / bad scheme / missing host / refused redirect
            / body over *max_bytes* (from ``fetch_url``).
        httpx.HTTPStatusError: On a 4xx/5xx response status.
        httpx.TransportError: On timeout / connection failure.
        InvalidInputImage: When the fetched bytes are not a decodable image.
        InputImageTooLarge: When the fetched bytes exceed *max_bytes*.
    """
    result = await fetch_url(
        url, max_bytes=max_bytes, timeout_s=timeout_s, transport=transport
    )
    redacted = _redact_fetch_url(url)
    record = await asyncio.to_thread(
        service.register_imported_image,
        result.body,
        origin_source=f"fetch:{redacted}",
        max_bytes=max_bytes,
    )
    logger.info(
        "fetch_image_ingested image_id=%s url=%s bytes=%d",
        record.id,
        redacted,
        result.size,
    )
    return record
