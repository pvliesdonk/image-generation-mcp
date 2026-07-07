"""Gallery-backed transfer hooks for pvl-core's capability-link routes.

pvl-core's ``register_transfer_routes`` owns the token store, the
``/transfer/{token}`` route, the ``create_download_link`` / ``create_upload_link``
tools, size caps, and TTL. This module supplies the two domain hooks it
consumes — a :class:`TransferSink` (where bytes come from / go to) and a
``TransferValidator`` (which refs are acceptable):

- **download** — ``read`` serves an existing gallery image's original bytes.
- **upload** — ``write`` ingests the uploaded bytes as an imported gallery
  entry via :meth:`ImageService.register_imported_image`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from image_generation_mcp._input_images import _parse_gallery_id
from image_generation_mcp._server_deps import _get_service_from_store
from image_generation_mcp.domain import _mime_to_ext

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from fastmcp_pvl_core import TransferKind, TransferReadResult

    from image_generation_mcp.config import ProjectConfig
    from image_generation_mcp.domain import ImageService

# Provenance recorded for uploaded images (an upload has no pre-known id).
_UPLOAD_ORIGIN_SOURCE = "upload"
# Accepted upload-name extensions (a fast pre-check; the real check is the
# byte-level validation in register_imported_image).
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


class GalleryTransferSink:
    """:class:`TransferSink` + validator backed by the image gallery.

    The live :class:`ImageService` is resolved per request (it is created by
    the server lifespan) so a single sink instance can be wired at server-build
    time.
    """

    def __init__(
        self,
        config: ProjectConfig,
        service_provider: Callable[[], ImageService] = _get_service_from_store,
    ) -> None:
        self._config = config
        self._service = service_provider

    async def validate(self, ref: str, kind: TransferKind) -> str:
        """Validate a link ref; return the opaque sink handle or raise to reject.

        Args:
            ref: For ``"download"``, an ``image://<id>`` URI or bare id; for
                ``"upload"``, the intended filename/label.
            kind: ``"download"`` or ``"upload"``.

        Returns:
            The sink handle: the image id (download) or the upload provenance.

        Raises:
            ValueError: Invalid download ref, or a non-image upload extension.
            ImageProviderError: Download ref names an unknown image.
        """
        if kind == "download":
            image_id = _parse_gallery_id(ref)
            if image_id is None:
                raise ValueError(
                    f"Invalid image reference {ref!r}; "
                    "expected image://<id> or a 12-hex id."
                )
            # Existence check — raises ImageProviderError if unknown.
            await asyncio.to_thread(self._service().get_image, image_id)
            return image_id

        suffix = PurePosixPath(ref).suffix.lower()
        if suffix and suffix not in _IMAGE_SUFFIXES:
            raise ValueError(
                f"Unsupported upload type {suffix!r}; expected a PNG/JPEG/WEBP image."
            )
        return _UPLOAD_ORIGIN_SOURCE

    async def read(self, handle: str) -> TransferReadResult:
        """Serve a gallery image's original bytes for a download handle."""
        from fastmcp_pvl_core import TransferReadResult

        service = self._service()
        record = await asyncio.to_thread(service.get_image, handle)
        data = await asyncio.to_thread(record.original_path.read_bytes)
        # Reuse domain.py's canonical MIME→extension map (single source of
        # truth). A stored record's content_type is always png/jpeg/webp, so
        # the helper's ".png" fallback is unreachable here.
        ext = _mime_to_ext(record.content_type)
        logger.info(
            "transfer_download_served image_id=%s bytes=%d", record.id, len(data)
        )
        return TransferReadResult(data, record.content_type, f"{record.id}{ext}")

    async def write(self, handle: str, body: bytes) -> Mapping[str, Any]:
        """Ingest an uploaded body as an imported gallery entry."""
        service = self._service()
        record = await asyncio.to_thread(
            service.register_imported_image,
            body,
            origin_source=handle,
            max_bytes=self._config.max_input_image_bytes,
        )
        logger.info(
            "transfer_upload_ingested image_id=%s origin_source=%s bytes=%d",
            record.id,
            handle,
            len(body),
        )
        return {
            "image_id": record.id,
            "uri": f"image://{record.id}/view",
            "origin": record.origin,
        }
