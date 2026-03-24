"""MCP tool registrations for image generation.

Exposes ``generate_image``, ``show_image``, ``browse_gallery``,
``gallery_page``, ``gallery_full_image``, and ``list_providers`` tools to
MCP clients.  ``generate_image`` is tagged ``write`` (hidden in read-only
mode).  ``gallery_page`` and ``gallery_full_image`` are app-only
(``visibility=["app"]``) and not shown to the model.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.apps import AppConfig
from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.tools import ToolResult
from mcp.types import (
    ClientCapabilities,
    ElicitationCapability,
    Icon,
    ImageContent,
    ResourceLink,
    TextContent,
)
from PIL import Image as PILImage
from pydantic import AnyUrl

from ._server_deps import get_config, get_service
from ._server_resources import _IMAGE_GALLERY_URI, _IMAGE_VIEWER_URI
from .config import ServerConfig
from .processing import (
    convert_format,
    crop_to_dimensions,
    generate_thumbnail,
    resize_image,
)
from .providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_BACKGROUNDS,
    SUPPORTED_QUALITY_LEVELS,
    ImageContentPolicyError,
    ImageProviderConnectionError,
)
from .service import ImageRecord, ImageService, PendingGeneration

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"
_THUMBNAIL_MAX_PX = 512
_GALLERY_THUMBNAIL_MAX_PX = 128
_GALLERY_PAGE_SIZE = 12
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def register_tools(mcp: FastMCP, *, transport: str = "stdio") -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
        transport: The MCP transport in use.  ``create_download_link`` is
            only registered for non-stdio transports (``"sse"`` or
            ``"http"``), because stdio has no HTTP server.
    """

    @mcp.tool(
        tags={"write"},
        task=True,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        icons=[Icon(src=_LUCIDE.format("image-plus"), mimeType="image/svg+xml")],
    )
    async def generate_image(
        prompt: str,
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        service: ImageService = Depends(get_service),
        config: ServerConfig = Depends(get_config),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Generate an image and return metadata with resource URIs.

        Returns immediately with ``{"status": "generating", "image_id":
        "..."}`` while the image is generated in the background. Call
        ``show_image`` with the returned ``image_id`` to check progress
        and display the result once ready.

        Call list_providers first to see available providers and model IDs.
        Read info://prompt-guide for provider-specific prompt writing tips.
        SD WebUI prompt style depends on the model: use CLIP tags for
        SD 1.5/SDXL, natural language for Flux (check ``prompt_style`` in
        list_providers or in the returned metadata).

        Args:
            prompt: Text description of the desired image.
            provider: Which provider to use. ``"auto"`` (default) selects
                based on prompt analysis. ``"openai"`` — best for text,
                logos, and general-purpose. ``"sd_webui"`` — best for
                photorealism, portraits, and artistic styles.
                ``"placeholder"`` — instant zero-cost solid-color PNG
                for testing.
            negative_prompt: Things to avoid in the image. SD WebUI
                supports this natively for SD 1.5/SDXL (CLIP-based) but
                NOT for Flux models. OpenAI appends as an "Avoid:" clause
                (weaker effect). Placeholder ignores it.
            aspect_ratio: Desired ratio (``1:1``, ``16:9``, ``9:16``,
                ``3:2``, ``2:3``).
            quality: Quality level. ``"hd"`` vs ``"standard"`` only
                affects OpenAI (gpt-image-1 maps both to its highest
                tier). SD WebUI and placeholder ignore this parameter.
            background: Background transparency. ``"opaque"`` (default)
                generates a solid background. ``"transparent"`` requests
                an image with a transparent background. Only supported
                by some providers (OpenAI gpt-image-1, placeholder).
                SD WebUI and dall-e-3 ignore this parameter.
            model: Specific model to use (e.g., a checkpoint name for
                SD WebUI, or ``"dall-e-3"`` for OpenAI). Use
                ``list_providers`` to see available model IDs. Defaults
                to the provider's configured model.

        Returns:
            JSON metadata with ``status``, ``image_id``, and resource
            URIs. Call ``show_image`` with the image URI to check
            progress and display the result.
        """
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            msg = (
                f"Unsupported aspect_ratio '{aspect_ratio}'. "
                f"Supported: {list(SUPPORTED_ASPECT_RATIOS)}"
            )
            raise ValueError(msg)
        if quality not in SUPPORTED_QUALITY_LEVELS:
            msg = (
                f"Unsupported quality '{quality}'. "
                f"Supported: {list(SUPPORTED_QUALITY_LEVELS)}"
            )
            raise ValueError(msg)
        if background not in SUPPORTED_BACKGROUNDS:
            msg = (
                f"Unsupported background '{background}'. "
                f"Supported: {', '.join(SUPPORTED_BACKGROUNDS)}"
            )
            raise ValueError(msg)

        # Resolve provider before generation so we can check if it's paid
        resolved_name = await asyncio.to_thread(
            service.resolve_provider_name,
            provider,
            prompt,
            background=background,
        )

        # If the resolved provider is paid and the client supports
        # elicitation, ask for confirmation before spending money.
        if resolved_name in config.paid_providers:
            try:
                supports_elicit = ctx.session.check_client_capability(
                    ClientCapabilities(elicitation=ElicitationCapability())
                )
            except Exception:
                logger.debug(
                    "check_client_capability failed; assuming no elicitation support",
                    exc_info=True,
                )
                supports_elicit = False

            if supports_elicit:
                elicit_result = await ctx.elicit(
                    f"This will use {resolved_name}"
                    f"{f' ({model})' if model else ''}"
                    ", which costs money. Proceed?",
                    response_type=None,
                )
                if not isinstance(elicit_result, AcceptedElicitation):
                    return ToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text=f"Image generation cancelled — {resolved_name} was not confirmed.",
                            )
                        ]
                    )

        # Pre-allocate image ID and register as pending
        image_id = service.allocate_image_id()
        service.register_pending(
            image_id=image_id,
            prompt=prompt,
            provider=resolved_name,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
            model=model,
        )

        # Spawn background generation task
        async def _background_generate() -> None:
            try:
                # Progress callback updates PendingGeneration so show_image
                # polling returns step-level detail for SD WebUI.
                pending = service.get_pending(image_id)
                if pending is None:
                    logger.warning(
                        "get_pending(%s) returned None; progress updates will be lost",
                        image_id,
                    )

                def _on_progress(fraction: float, message: str) -> None:
                    if pending is not None:
                        pending.progress = fraction
                        pending.progress_message = message

                provider_name, result = await service.generate(
                    prompt,
                    provider=resolved_name,
                    negative_prompt=negative_prompt,
                    aspect_ratio=aspect_ratio,
                    quality=quality,
                    background=background,
                    model=model,
                    progress_callback=_on_progress,
                )
                await asyncio.to_thread(
                    service.register_image,
                    result,
                    provider_name,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    aspect_ratio=aspect_ratio,
                    quality=quality,
                    background=background,
                    image_id=image_id,
                )
                service.complete_pending(image_id)
                logger.info("Background generation completed: %s", image_id)
            except ImageContentPolicyError as exc:
                service.fail_pending(
                    image_id,
                    "Content policy rejected the prompt. "
                    "Try rephrasing or use a different provider.",
                )
                logger.error(
                    "Background generation failed (content policy): %s: %s",
                    image_id,
                    exc,
                )
            except ImageProviderConnectionError as exc:
                service.fail_pending(
                    image_id,
                    "Provider is unreachable. "
                    "Check that it is running, or try a different provider.",
                )
                logger.error(
                    "Background generation failed (connection): %s: %s",
                    image_id,
                    exc,
                )
            except Exception as exc:
                service.fail_pending(image_id, str(exc))
                logger.error(
                    "Background generation failed: %s: %s",
                    image_id,
                    exc,
                    exc_info=True,
                )

        task = asyncio.create_task(_background_generate())
        # Hold a strong reference to prevent GC before completion
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

        # Resolve prompt_style from capabilities for the response
        prompt_style = None
        caps = service.capabilities.get(resolved_name)
        if caps:
            if model:
                for m in caps.models:
                    if m.model_id == model:
                        prompt_style = m.prompt_style
                        break
            elif len(caps.models) == 1:
                prompt_style = caps.models[0].prompt_style

        # Return immediately with pending status
        metadata = {
            "status": "generating",
            "image_id": image_id,
            "prompt": prompt,
            "provider": resolved_name,
            "prompt_style": prompt_style,
            "original_uri": f"image://{image_id}/view",
            "metadata_uri": f"image://{image_id}/metadata",
            "resource_template": (
                f"image://{image_id}/view{{?format,width,height,quality}}"
            ),
        }

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
                ResourceLink(
                    type="resource_link",
                    uri=AnyUrl(f"image://{image_id}/view"),
                    name="Generated image (generating)",
                ),
            ]
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("eye"), mimeType="image/svg+xml")],
        app=AppConfig(resourceUri=_IMAGE_VIEWER_URI),
    )
    async def show_image(
        uri: str,
        with_link: bool = True,
        service: ImageService = Depends(get_service),
        config: ServerConfig = Depends(get_config),
    ) -> ToolResult:
        """Display a registered image with optional on-demand transforms.

        Also serves as the polling endpoint for fire-and-forget generation.
        After calling ``generate_image``, call ``show_image`` with the
        returned ``image_id`` to check progress:

        - ``{"status": "generating", ...}`` — image is still being generated
        - ``{"status": "failed", "error": "..."}`` — generation failed
        - Image thumbnail + metadata — generation complete

        Accepts a full ``image://`` resource URI (e.g.
        ``image://abc123/view`` or
        ``image://abc123/view?format=webp&width=512``).  Transforms are
        encoded in the URI query string — no separate parameters needed.

        Read the ``image://list`` resource to browse available image IDs.

        Args:
            uri: A full ``image://`` resource URI, optionally with query
                params: ``format`` (``png``, ``webp``, ``jpeg``),
                ``width`` (pixels), ``height`` (pixels),
                ``quality`` (1-100, for lossy formats).
            with_link: When ``True`` (default), include a one-time
                ``download_url`` in the metadata if the server is
                running on HTTP transport with ``BASE_URL`` configured.
                Present this URL directly to the user as a clickable
                link — the MCP App widget cannot open it from its
                sandboxed iframe.

        Returns:
            For completed images: a WebP thumbnail preview (max 512px,
            under 1 MB) as ``ImageContent`` plus JSON metadata.
            For in-progress images: JSON with ``status`` and progress info.
            For full-resolution access, use the ``image://`` resource URI
            or the download URL.
        """
        parsed = urlparse(uri)
        if parsed.scheme != "image":
            msg = f"Expected an image:// URI, got scheme '{parsed.scheme}'"
            raise ValueError(msg)
        image_id = parsed.netloc or ""
        qs = parse_qs(parsed.query)

        fmt = qs.get("format", [""])[0]
        width = int(qs.get("width", ["0"])[0])
        height = int(qs.get("height", ["0"])[0])
        quality = int(qs.get("quality", ["90"])[0])
        quality = max(1, min(100, quality))

        # Check for pending (fire-and-forget) generation
        pending = service.get_pending(image_id)
        if pending is not None and pending.status == "generating":
            meta = {
                "status": "generating",
                "image_id": image_id,
                "prompt": pending.prompt,
                "provider": pending.provider,
                "progress": pending.progress,
                "progress_message": pending.progress_message,
                "elapsed_seconds": round(time.time() - pending.created_at, 1),
            }
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps(meta, indent=2))]
            )

        if pending is not None and pending.status == "failed":
            meta = {
                "status": "failed",
                "image_id": image_id,
                "prompt": pending.prompt,
                "provider": pending.provider,
                "error": pending.error,
            }
            service.cleanup_pending(image_id)
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps(meta, indent=2))]
            )

        # Completed pending — clean up and fall through to normal display
        if pending is not None and pending.status == "completed":
            service.cleanup_pending(image_id)

        record = await asyncio.to_thread(service.get_image, image_id)
        data = await asyncio.to_thread(record.original_path.read_bytes)
        content_type = record.content_type

        # Apply resize/crop first (always from original to prevent quality
        # degradation — see ADR-0006)
        if width > 0 and height > 0:
            data = await asyncio.to_thread(crop_to_dimensions, data, width, height)
        elif width > 0:
            orig_w, orig_h = record.original_dimensions
            ratio = width / orig_w
            new_height = round(orig_h * ratio)
            data = await asyncio.to_thread(resize_image, data, width, new_height)
        elif height > 0:
            orig_w, orig_h = record.original_dimensions
            ratio = height / orig_h
            new_width = round(orig_w * ratio)
            data = await asyncio.to_thread(resize_image, data, new_width, height)

        # Apply format conversion last (one encode from spatial result)
        if fmt:
            data, content_type = await asyncio.to_thread(
                convert_format, data, fmt, quality
            )

        # Determine final dimensions — use stored metadata when no spatial
        # transform was applied to avoid an extra Pillow decode.
        transforms_changed_size = width > 0 or height > 0
        if transforms_changed_size:
            final_img = await asyncio.to_thread(lambda: PILImage.open(io.BytesIO(data)))
            final_w, final_h = final_img.size
        else:
            final_w, final_h = record.original_dimensions

        # Always cap the ImageContent to a thumbnail (max 512px, WebP,
        # quality 80) to stay under the ~1 MB tool-result size limit
        # imposed by Claude Desktop and other MCP clients.  The full-
        # resolution image remains available via the image:// resource URI.
        def _make_thumb(src: bytes) -> tuple[bytes, str, tuple[int, int]]:
            td, tm = generate_thumbnail(src, _THUMBNAIL_MAX_PX, "webp", 80)
            tw, th = PILImage.open(io.BytesIO(td)).size
            return td, tm, (tw, th)

        thumb_data, thumb_mime, thumb_dims = await asyncio.to_thread(_make_thumb, data)
        thumb_b64 = base64.b64encode(thumb_data).decode("ascii")

        transform_params: dict[str, int | str] = {}
        if fmt:
            transform_params["format"] = fmt
        if width:
            transform_params["width"] = width
        if height:
            transform_params["height"] = height
        if fmt and quality != 90:
            transform_params["quality"] = quality

        original_stat = await asyncio.to_thread(record.original_path.stat)
        metadata: dict[str, object] = {
            "image_id": record.id,
            "prompt": record.prompt,
            "provider": record.provider,
            "model": record.provider_metadata.get("model"),
            "prompt_style": record.provider_metadata.get("prompt_style"),
            "dimensions": [final_w, final_h],
            "thumbnail_dimensions": list(thumb_dims),
            "original_size_bytes": original_stat.st_size,
            "format": content_type,
            "transforms_applied": transform_params,
        }

        # Auto-generate a download link when on HTTP transport with
        # BASE_URL configured and with_link is True.
        if with_link:
            base_url = (config.base_url or "").rstrip("/")
            if base_url:
                from .artifacts import get_artifact_store

                try:
                    store = get_artifact_store()
                    token = store.create_token(uri, ttl_seconds=300)
                    metadata["download_url"] = f"{base_url}/artifacts/{token}"
                except RuntimeError:
                    pass  # stdio transport — artifact store not initialised

        return ToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=thumb_b64,
                    mimeType=thumb_mime,
                ),
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
            ]
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("images"), mimeType="image/svg+xml")],
        app=AppConfig(resourceUri=_IMAGE_GALLERY_URI),
    )
    async def browse_gallery(
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Browse all generated images in an interactive visual gallery.

        Opens a gallery view showing thumbnail previews of every image in the
        scratch directory.  The UI renders immediately from the first page of
        thumbnails returned by this tool, then paginates using the
        ``gallery_page`` helper.

        For non-UI clients the response is a JSON object with ``total``,
        ``page``, ``page_size``, and ``items``.  Each completed item includes
        ``image_id``, ``prompt``, ``provider``, ``dimensions``,
        ``created_at``, ``thumbnail_b64`` (128 px WebP, base64-encoded),
        and ``content_type``.  Pending/generating items include ``status``,
        ``progress``, and ``progress_message`` instead of a thumbnail.

        Use ``show_image`` with the returned ``image_id`` to view a single
        image at full resolution with metadata.

        Returns:
            JSON with gallery data (total count, page metadata, thumbnail
            items for page 1) as a :class:`~fastmcp.tools.ToolResult`.
        """
        images = sorted(service.list_images(), key=lambda r: r.created_at, reverse=True)
        pending = sorted(
            service.list_pending(), key=lambda p: p.created_at, reverse=True
        )
        total = len(images) + len(pending)

        # Build page-1 items: pending first (newest), then completed
        page_size = _GALLERY_PAGE_SIZE
        all_items: list[dict[str, object]] = []
        for p in pending:
            if len(all_items) >= page_size:
                break
            all_items.append(
                {
                    "image_id": p.id,
                    "status": p.status,
                    "prompt": p.prompt,
                    "provider": p.provider,
                    "progress": p.progress,
                    "progress_message": p.progress_message,
                }
            )
        for img in images:
            if len(all_items) >= page_size:
                break
            img_data = await asyncio.to_thread(img.original_path.read_bytes)
            thumb_bytes, _ = await asyncio.to_thread(
                generate_thumbnail, img_data, _GALLERY_THUMBNAIL_MAX_PX, "webp", 80
            )
            all_items.append(
                {
                    "image_id": img.id,
                    "status": "completed",
                    "prompt": img.prompt,
                    "provider": img.provider,
                    "dimensions": list(img.original_dimensions),
                    "created_at": datetime.fromtimestamp(
                        img.created_at, tz=UTC
                    ).isoformat(),
                    "thumbnail_b64": base64.b64encode(thumb_bytes).decode(),
                    "content_type": img.content_type,
                }
            )

        gallery_data = {
            "total": total,
            "page": 1,
            "page_size": page_size,
            "items": all_items,
        }

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(gallery_data),
                )
            ]
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(resourceUri=_IMAGE_GALLERY_URI, visibility=["app"]),
    )
    async def gallery_page(
        page: int = 1,
        page_size: int = _GALLERY_PAGE_SIZE,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Return a page of image thumbnails for the gallery UI.

        App-only helper called by the gallery UI to load additional pages when
        the user paginates.  Not intended for direct model invocation.

        Args:
            page: 1-based page number.
            page_size: Number of items per page (1-24, default 12).

        Returns:
            JSON with ``total``, ``page``, ``page_size``, and ``items``.
            Each completed item includes ``thumbnail_b64`` (128 px WebP).
            Pending/generating items omit the thumbnail.
        """
        images = sorted(service.list_images(), key=lambda r: r.created_at, reverse=True)
        pending = sorted(
            service.list_pending(), key=lambda p: p.created_at, reverse=True
        )
        total = len(images) + len(pending)

        page = max(1, page)
        page_size = max(1, min(24, page_size))
        start = (page - 1) * page_size

        # Merge pending + completed; pending items go first (newest)
        all_pending = list(pending)
        all_completed = list(images)
        all_meta: list[tuple[str, PendingGeneration | ImageRecord]] = [
            ("pending", p) for p in all_pending
        ] + [("completed", img) for img in all_completed]
        page_slice = all_meta[start : start + page_size]

        items: list[dict[str, object]] = []
        for kind, record in page_slice:
            if kind == "pending" and isinstance(record, PendingGeneration):
                items.append(
                    {
                        "image_id": record.id,
                        "status": record.status,
                        "prompt": record.prompt,
                        "provider": record.provider,
                        "progress": record.progress,
                        "progress_message": record.progress_message,
                    }
                )
            elif isinstance(record, ImageRecord):
                img_data = await asyncio.to_thread(record.original_path.read_bytes)
                thumb_bytes, _ = await asyncio.to_thread(
                    generate_thumbnail, img_data, _GALLERY_THUMBNAIL_MAX_PX, "webp", 80
                )
                items.append(
                    {
                        "image_id": record.id,
                        "status": "completed",
                        "prompt": record.prompt,
                        "provider": record.provider,
                        "dimensions": list(record.original_dimensions),
                        "created_at": datetime.fromtimestamp(
                            record.created_at, tz=UTC
                        ).isoformat(),
                        "thumbnail_b64": base64.b64encode(thumb_bytes).decode(),
                        "content_type": record.content_type,
                    }
                )

        return json.dumps(
            {"total": total, "page": page, "page_size": page_size, "items": items}
        )

    _LIGHTBOX_MAX_BYTES = 1 * 1024 * 1024  # 1 MB size cap for lightbox images
    _LIGHTBOX_MAX_PX = 1024  # resize target when image exceeds size cap

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(resourceUri=_IMAGE_GALLERY_URI, visibility=["app"]),
    )
    async def gallery_full_image(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Return full-resolution image data for the gallery lightbox.

        App-only helper called by the gallery lightbox to load a single image
        at full (or near-full) resolution.  Images larger than 1 MB are
        downscaled to 1024 px wide WebP before encoding.

        Args:
            image_id: The image ID to load.

        Returns:
            JSON with ``image_id``, ``b64``, ``content_type``, ``dimensions``,
            ``prompt``, ``provider``, and ``created_at``.
        """
        record = await asyncio.to_thread(service.get_image, image_id)
        # get_transformed_image with no transforms returns original bytes
        img_bytes, content_type = await asyncio.to_thread(
            service.get_transformed_image, image_id
        )
        if len(img_bytes) > _LIGHTBOX_MAX_BYTES:
            img_bytes, content_type = await asyncio.to_thread(
                service.get_transformed_image,
                image_id,
                "webp",
                _LIGHTBOX_MAX_PX,
                0,
                85,
            )
        return json.dumps(
            {
                "image_id": record.id,
                "b64": base64.b64encode(img_bytes).decode(),
                "content_type": content_type,
                "dimensions": list(record.original_dimensions),
                "prompt": record.prompt,
                "provider": record.provider,
                "created_at": datetime.fromtimestamp(
                    record.created_at, tz=UTC
                ).isoformat(),
            }
        )

    @mcp.tool(
        icons=[Icon(src=_LUCIDE.format("layers"), mimeType="image/svg+xml")],
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": False,
        },
    )
    async def list_providers(
        force_refresh: bool = False,
        service: ImageService = Depends(get_service),
    ) -> str:
        """List available image generation providers, models, and capabilities.

        Returns provider names, available models, prompt_style (``"clip"``
        or ``"natural_language"``), and capability details. Each call
        includes a ``refreshed_at`` timestamp. Pass ``force_refresh=true``
        if providers may have changed since the last check.

        Also available as the ``info://providers`` resource for clients
        that support MCP resources.

        Args:
            force_refresh: When ``True``, re-runs capability discovery on
                all registered providers before returning, updating cached
                results. Use when providers may have changed (e.g., new
                SD WebUI checkpoints loaded).

        Returns:
            JSON object with provider names, capabilities, and a
            ``refreshed_at`` ISO 8601 timestamp.
        """
        if force_refresh:
            await service.discover_all_capabilities()
        providers = service.list_providers()
        result = {
            "refreshed_at": datetime.now(UTC).isoformat(),
            "providers": providers,
        }
        return json.dumps(result, indent=2)

    # create_download_link is only available on HTTP transports —
    # stdio has no HTTP server to host the artifact endpoint.
    if transport != "stdio":
        _register_download_link_tool(mcp)


def _register_download_link_tool(mcp: FastMCP) -> None:
    """Register the ``create_download_link`` tool on *mcp*.

    Separated from :func:`register_tools` so it can be conditionally
    called only when an HTTP transport is active.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register the tool on.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("link"), mimeType="image/svg+xml")],
    )
    async def create_download_link(
        uri: str,
        ttl_seconds: int = 300,
        service: ImageService = Depends(get_service),
        config: ServerConfig = Depends(get_config),
    ) -> str:
        """Create a one-time download URL for an image.

        Creates a temporary HTTP endpoint that serves the image once,
        then invalidates the link. Use this to pass images to other
        MCP servers (e.g., save to a vault, attach to email).

        The URI should be an ``image://`` resource URI, optionally with
        transform parameters (``format``, ``width``, ``height``,
        ``quality``).

        Requires ``IMAGE_GENERATION_MCP_BASE_URL`` to be configured.
        Only available on HTTP transport (not stdio).

        Args:
            uri: A full ``image://`` resource URI, e.g.
                ``image://abc123/view`` or
                ``image://abc123/view?format=webp&width=512``.
            ttl_seconds: Link lifetime in seconds (default 300 / 5 minutes).

        Returns:
            JSON with ``download_url``, ``expires_in_seconds``, and ``uri``.

        Raises:
            ValueError: If ``IMAGE_GENERATION_MCP_BASE_URL`` is not
                configured or the URI references an unknown image.
        """
        from urllib.parse import urlparse

        # Validate BASE_URL is configured
        base_url = (config.base_url or "").rstrip("/")
        if not base_url:
            msg = (
                "IMAGE_GENERATION_MCP_BASE_URL is required for download links. "
                "Set it to the public base URL of this server "
                "(e.g. https://mcp.example.com)."
            )
            raise ValueError(msg)

        # Validate the URI references a registered image
        parsed = urlparse(uri)
        image_id = parsed.netloc or ""
        if not image_id:
            msg = f"Invalid image URI: {uri!r}. Expected format: image://{{image_id}}/view"
            raise ValueError(msg)

        # Raises ImageProviderError if the image is not found
        await asyncio.to_thread(service.get_image, image_id)

        from image_generation_mcp.artifacts import get_artifact_store

        store = get_artifact_store()
        token = store.create_token(uri, ttl_seconds=ttl_seconds)

        download_url = f"{base_url}/artifacts/{token}"
        result = {
            "download_url": download_url,
            "expires_in_seconds": ttl_seconds,
            "uri": uri,
        }
        logger.info(
            "Created download link for image_id=%r ttl=%ds url=%s",
            image_id,
            ttl_seconds,
            download_url,
        )
        return json.dumps(result, indent=2)
