"""MCP tool registrations for image generation.

Exposes ``generate_image``, ``show_image``, and ``list_providers`` tools to
MCP clients.  ``generate_image`` is tagged ``write`` (hidden in read-only mode).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext, Depends, Progress
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
from ._server_resources import _IMAGE_VIEWER_URI
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
from .service import ImageService

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"
_THUMBNAIL_MAX_PX = 512
_KEEPALIVE_INTERVAL_S = 10


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
        progress: Progress = Progress(),
    ) -> ToolResult:
        """Generate an image and return metadata with resource URIs.

        Call list_providers first to see available providers and model IDs.
        Read info://prompt-guide for provider-specific prompt writing tips.
        SD WebUI prompt style depends on the model: use CLIP tags for
        SD 1.5/SDXL, natural language for Flux (check ``prompt_style`` in
        list_providers or in the returned metadata).
        Returns metadata including the image_id and resource URIs. Call
        show_image with the image URI (e.g. ``image://{image_id}/view``) to
        display the image.

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
            JSON metadata with image_id and resource URIs. Call
            show_image with the image URI to display the result.
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

        await progress.set_total(2)
        await progress.set_message("Generating image")

        async def _keepalive() -> None:
            """Send periodic MCP log notifications during generation.

            Prevents clients (e.g. Claude Android) from timing out the
            SSE connection when there are no MCP-level messages for an
            extended period.
            """
            elapsed = 0
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL_S)
                elapsed += _KEEPALIVE_INTERVAL_S
                try:
                    await ctx.info(f"Image generation in progress ({elapsed}s elapsed)")
                except Exception:
                    logger.warning("keepalive ctx.info failed", exc_info=True)

        keepalive_task = asyncio.create_task(_keepalive())
        try:
            provider_name, result = await service.generate(
                prompt,
                provider=resolved_name,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
                background=background,
                model=model,
            )
        except ImageContentPolicyError as e:
            raise ImageContentPolicyError(
                e.provider,
                "Content policy rejected the prompt. "
                "Try rephrasing or use a different provider.",
            ) from None
        except ImageProviderConnectionError as e:
            raise ImageProviderConnectionError(
                e.provider,
                "Provider is unreachable. Check that it is running, "
                "or try a different provider.",
            ) from None
        finally:
            keepalive_task.cancel()
            await asyncio.gather(keepalive_task, return_exceptions=True)

        await progress.increment()
        await progress.set_message("Saving to scratch")

        # Register in the image registry (blocking I/O -> offload)
        record = await asyncio.to_thread(
            service.register_image,
            result,
            provider_name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
        )

        # Build metadata with resource URIs
        metadata = {
            "image_id": record.id,
            "prompt": prompt,
            "original_uri": f"image://{record.id}/view",
            "metadata_uri": f"image://{record.id}/metadata",
            "resource_template": (
                f"image://{record.id}/view{{?format,width,height,quality}}"
            ),
            "dimensions": list(record.original_dimensions),
            "original_size_bytes": result.size_bytes,
            "provider": provider_name,
            **result.provider_metadata,
        }

        await progress.increment()
        await progress.set_message("Done")

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
                ResourceLink(
                    type="resource_link",
                    uri=AnyUrl(f"image://{record.id}/view"),
                    name="Generated image",
                ),
            ]
        )

    @mcp.tool(
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

        Returns:
            A WebP thumbnail preview (max 512px, under 1 MB) as
            ``ImageContent`` plus JSON metadata (image_id, dimensions,
            thumbnail_dimensions, format, applied transforms, model,
            and optionally download_url).  For full-resolution access,
            use the ``image://`` resource URI or the download URL.
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
        icons=[Icon(src=_LUCIDE.format("layers"), mimeType="image/svg+xml")],
        annotations={"idempotentHint": False},
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
            force_refresh: Set to ``true`` to signal that cached results
                should not be used.  The server always returns current
                data; this parameter exists to bust client-side caches
                by changing the tool input signature.

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
