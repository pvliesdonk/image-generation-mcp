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
from urllib.parse import parse_qs, urlparse

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.apps import AppConfig
from fastmcp.server.context import Context
from fastmcp.tools import ToolResult
from mcp.types import Icon, ImageContent, ResourceLink, TextContent
from PIL import Image as PILImage

from ._server_deps import get_service
from ._server_resources import _IMAGE_VIEWER_URI
from .processing import convert_format, crop_to_dimensions, resize_image
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


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
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
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Generate an image and return metadata with resource URIs.

        Call list_providers first to see available providers and model IDs.
        Returns metadata including the image_id and resource URIs. Call
        show_image with the image URI (e.g. ``image://{image_id}/view``) to
        display the image.

        Args:
            prompt: Text description of the desired image.
            provider: Which provider to use. ``"auto"`` (default) selects
                based on prompt analysis. ``"openai"`` — best for text,
                logos, and general-purpose. ``"a1111"`` — best for
                photorealism, portraits, and artistic styles.
                ``"placeholder"`` — instant zero-cost solid-color PNG
                for testing.
            negative_prompt: Things to avoid in the image. A1111 supports
                this natively via CLIP. OpenAI appends as an "Avoid:"
                clause (weaker effect). Placeholder ignores it.
            aspect_ratio: Desired ratio (``1:1``, ``16:9``, ``9:16``,
                ``3:2``, ``2:3``).
            quality: Quality level. ``"hd"`` vs ``"standard"`` only
                affects OpenAI (gpt-image-1 maps both to its highest
                tier). A1111 and placeholder ignore this parameter.
            background: Background transparency. ``"opaque"`` (default)
                generates a solid background. ``"transparent"`` requests
                an image with a transparent background. Only supported
                by some providers (OpenAI gpt-image-1, placeholder).
                A1111 and dall-e-3 ignore this parameter.
            model: Specific model to use (e.g., a checkpoint name for
                A1111, or ``"dall-e-3"`` for OpenAI). Use
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

        await ctx.report_progress(0, 2, "Generating image")
        try:
            provider_name, result = await service.generate(
                prompt,
                provider=provider,
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

        await ctx.report_progress(1, 2, "Saving to scratch")

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

        await ctx.report_progress(2, 2, "Done")

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
                ResourceLink(
                    type="resource_link",
                    uri=f"image://{record.id}/view",
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
        service: ImageService = Depends(get_service),
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

        Returns:
            The requested image as base64-encoded ``ImageContent`` plus
            JSON metadata (image_id, dimensions, format, applied
            transforms).
        """
        parsed = urlparse(uri)
        image_id = parsed.hostname or parsed.netloc
        qs = parse_qs(parsed.query)

        fmt = qs.get("format", [""])[0]
        width = int(qs.get("width", [0])[0])
        height = int(qs.get("height", [0])[0])
        quality = int(qs.get("quality", [90])[0])

        record = await asyncio.to_thread(service.get_image, image_id)
        data = await asyncio.to_thread(record.original_path.read_bytes)
        content_type = record.content_type

        # Apply resize/crop first (always from original to prevent quality
        # degradation — see ADR-0006)
        if width > 0 and height > 0:
            data = await asyncio.to_thread(crop_to_dimensions, data, width, height)
        elif width > 0:
            img = PILImage.open(io.BytesIO(data))
            ratio = width / img.width
            new_height = round(img.height * ratio)
            data = await asyncio.to_thread(resize_image, data, width, new_height)
        elif height > 0:
            img = PILImage.open(io.BytesIO(data))
            ratio = height / img.height
            new_width = round(img.width * ratio)
            data = await asyncio.to_thread(resize_image, data, new_width, height)

        # Apply format conversion last (one encode from spatial result)
        if fmt:
            data, content_type = await asyncio.to_thread(
                convert_format, data, fmt, quality
            )

        img_b64 = base64.b64encode(data).decode("ascii")

        # Determine final dimensions
        final_img = PILImage.open(io.BytesIO(data))
        final_w, final_h = final_img.size

        transform_params: dict[str, int | str] = {}
        if fmt:
            transform_params["format"] = fmt
        if width:
            transform_params["width"] = width
        if height:
            transform_params["height"] = height
        if fmt and quality != 90:
            transform_params["quality"] = quality

        metadata = {
            "image_id": record.id,
            "prompt": record.prompt,
            "provider": record.provider,
            "dimensions": [final_w, final_h],
            "original_size_bytes": record.original_path.stat().st_size,
            "format": content_type,
            "transforms_applied": transform_params,
        }

        return ToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=img_b64,
                    mimeType=content_type,
                ),
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
            ]
        )

    @mcp.tool(
        icons=[Icon(src=_LUCIDE.format("layers"), mimeType="image/svg+xml")],
    )
    async def list_providers(
        service: ImageService = Depends(get_service),
    ) -> str:
        """List available image generation providers.

        Returns:
            JSON object with provider names and availability info.
        """
        providers = service.list_providers()
        return json.dumps(providers, indent=2)
