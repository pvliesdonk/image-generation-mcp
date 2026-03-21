"""One-time artifact download endpoint for inter-MCP image transfer.

Implements an in-memory token store and a Starlette route handler that
serves image bytes once and then invalidates the token.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.responses import Response

from image_generation_mcp.processing import (
    convert_format,
    crop_to_dimensions,
    resize_image,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request

    from image_generation_mcp.service import ImageService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------


@dataclass
class TokenRecord:
    """A one-time download token record.

    Attributes:
        uri: The ``image://`` resource URI this token grants access to.
        created_at: Unix timestamp of when the token was created.
        ttl_seconds: Time-to-live in seconds.
    """

    uri: str
    created_at: float
    ttl_seconds: int


class ArtifactStore:
    """In-memory one-time token store for artifact downloads.

    Tokens are UUIDs (hex) that grant a single download of an image
    resource URI.  Expired tokens are cleaned up lazily on each
    operation.

    Note:
        The store is in-memory only — tokens do not survive a server
        restart.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, TokenRecord] = {}

    def create_token(self, uri: str, ttl_seconds: int = 300) -> str:
        """Create a one-time download token.

        Args:
            uri: The ``image://`` resource URI to grant access to.
            ttl_seconds: Token lifetime in seconds (default 300).

        Returns:
            A hex UUID token string.
        """
        self._cleanup_expired()
        token = uuid.uuid4().hex
        self._tokens[token] = TokenRecord(
            uri=uri,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )
        logger.debug("Created artifact token for uri=%r ttl=%ds", uri, ttl_seconds)
        return token

    def consume_token(self, token: str) -> TokenRecord | None:
        """Consume a token, returning the record or None if invalid/expired.

        The token is always removed from the store (one-time use), even
        if it has expired.

        Args:
            token: The hex UUID token string.

        Returns:
            The :class:`TokenRecord`, or ``None`` if unknown or expired.
        """
        self._cleanup_expired()
        record = self._tokens.pop(token, None)
        if record is None:
            return None
        if time.time() - record.created_at > record.ttl_seconds:
            logger.debug("Artifact token expired: %s", token)
            return None
        return record

    def _cleanup_expired(self) -> None:
        """Remove expired tokens (lazy cleanup on each operation)."""
        now = time.time()
        expired = [
            k for k, v in self._tokens.items() if now - v.created_at > v.ttl_seconds
        ]
        for k in expired:
            del self._tokens[k]
        if expired:
            logger.debug("Cleaned up %d expired artifact token(s)", len(expired))


# ---------------------------------------------------------------------------
# Module-level store singleton (set by lifespan)
# ---------------------------------------------------------------------------

_artifact_store: ArtifactStore | None = None


def set_artifact_store(store: ArtifactStore | None) -> None:
    """Set the module-level artifact store (called from lifespan).

    Args:
        store: The :class:`ArtifactStore` instance to use, or ``None`` to clear.
    """
    global _artifact_store
    _artifact_store = store


def get_artifact_store() -> ArtifactStore:
    """Return the module-level artifact store.

    Returns:
        The active :class:`ArtifactStore`.

    Raises:
        RuntimeError: If the store has not been initialised via lifespan.
    """
    if _artifact_store is None:
        msg = "ArtifactStore not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return _artifact_store


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


def make_artifact_handler() -> Callable[[Request], Awaitable[Response]]:
    """Build the Starlette route handler for ``GET /artifacts/{token}``.

    The returned handler accesses the :class:`ImageService` via the
    module-level store in :mod:`image_generation_mcp._server_deps`, which
    is populated during server lifespan.

    Returns:
        An async Starlette request handler.
    """
    from urllib.parse import parse_qs, urlparse

    async def artifact_handler(request: Request) -> Response:
        """Serve a one-time image download and invalidate the token.

        Args:
            request: Starlette request with ``token`` path param.

        Returns:
            Image bytes response with correct ``Content-Type``, or HTTP 404.
        """
        token = request.path_params.get("token", "")
        store = get_artifact_store()
        record = store.consume_token(token)

        if record is None:
            logger.debug("Artifact token not found or expired: %s", token)
            return Response(content="Not Found", status_code=404)

        # Parse the resource URI to extract image_id and transform params
        parsed = urlparse(record.uri)
        image_id = parsed.netloc or ""
        qs = parse_qs(parsed.query)

        fmt = qs.get("format", [""])[0]
        try:
            width = int(qs.get("width", ["0"])[0])
        except (ValueError, TypeError):
            width = 0
        try:
            height = int(qs.get("height", ["0"])[0])
        except (ValueError, TypeError):
            height = 0
        try:
            quality = int(qs.get("quality", ["90"])[0])
        except (ValueError, TypeError):
            quality = 90

        # Get service via module-level getter
        from image_generation_mcp._server_deps import _get_service_from_store
        from image_generation_mcp.providers.types import ImageProviderError

        service: ImageService = _get_service_from_store()

        try:
            img_record = await asyncio.to_thread(service.get_image, image_id)
        except ImageProviderError:
            logger.warning("Artifact: image not found for id=%r", image_id)
            return Response(content="Not Found", status_code=404)

        try:
            data = await asyncio.to_thread(img_record.original_path.read_bytes)
        except OSError:
            logger.warning(
                "Artifact: image file missing for id=%r path=%s",
                image_id,
                img_record.original_path,
            )
            return Response(content="Not Found", status_code=404)
        content_type = img_record.content_type

        # Apply resize/crop first (same logic as show_image and image_view)
        if width > 0 and height > 0:
            data = await asyncio.to_thread(crop_to_dimensions, data, width, height)
        elif width > 0:
            orig_w, orig_h = img_record.original_dimensions
            ratio = width / orig_w
            new_height = round(orig_h * ratio)
            data = await asyncio.to_thread(resize_image, data, width, new_height)
        elif height > 0:
            orig_w, orig_h = img_record.original_dimensions
            ratio = height / orig_h
            new_width = round(orig_w * ratio)
            data = await asyncio.to_thread(resize_image, data, new_width, height)

        # Apply format conversion last
        if fmt:
            data, content_type = await asyncio.to_thread(
                convert_format, data, fmt, quality
            )

        logger.info(
            "Artifact served: token=%s image_id=%r content_type=%s",
            token,
            image_id,
            content_type,
        )
        return Response(content=data, media_type=content_type)

    return artifact_handler
