"""MCP tool registrations for image generation.

Exposes ``generate_image`` and ``list_providers`` tools to MCP clients.
``generate_image`` is tagged ``write`` (hidden in read-only mode).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.context import Context
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent

from ._server_deps import get_service
from .processing import generate_thumbnail
from .providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_QUALITY_LEVELS,
    ImageContentPolicyError,
    ImageProviderConnectionError,
)
from .service import ImageService

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
    """

    @mcp.tool(tags={"write"}, task=True)
    async def generate_image(
        prompt: str,
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        service: ImageService = Depends(get_service),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Generate an image and return a thumbnail preview with resource URIs.

        Call list_providers first to see available providers. Returns an
        inline thumbnail plus URIs for full-resolution access and
        on-demand transforms (resize, crop, format conversion).

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

        Returns:
            A thumbnail preview plus resource URIs for full-resolution
            access and on-demand transforms.
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

        await ctx.report_progress(0, 2, "Generating image")
        try:
            provider_name, result = await service.generate(
                prompt,
                provider=provider,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
            )
        except ImageContentPolicyError:
            raise ImageContentPolicyError(
                provider,
                "Content policy rejected the prompt. "
                "Try rephrasing or use a different provider.",
            ) from None
        except ImageProviderConnectionError:
            raise ImageProviderConnectionError(
                provider,
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
        )

        # Generate thumbnail (blocking Pillow -> offload)
        thumb_data, thumb_mime = await asyncio.to_thread(
            generate_thumbnail, result.image_data
        )
        thumb_b64 = base64.b64encode(thumb_data).decode("ascii")

        # Build metadata with resource URIs
        metadata = {
            "image_id": record.id,
            "original_uri": f"image://{record.id}/view",
            "metadata_uri": f"image://{record.id}/metadata",
            "resource_template": (
                f"image://{record.id}/view{{?format,width,height,quality}}"
            ),
            "original_size_bytes": result.size_bytes,
            "thumbnail_size_bytes": len(thumb_data),
            "provider": provider_name,
            "file_path": str(record.original_path),
            **result.provider_metadata,
        }

        await ctx.report_progress(2, 2, "Done")

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

    @mcp.tool()
    async def list_providers(
        service: ImageService = Depends(get_service),
    ) -> str:
        """List available image generation providers.

        Returns:
            JSON object with provider names and availability info.
        """
        providers = service.list_providers()
        return json.dumps(providers, indent=2)
