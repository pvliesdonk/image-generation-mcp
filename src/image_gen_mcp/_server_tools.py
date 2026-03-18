"""MCP tool registrations for image generation.

Exposes ``generate_image`` and ``list_providers`` tools to MCP clients.
``generate_image`` is tagged ``write`` (hidden in read-only mode).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent

from ._server_deps import get_service
from .service import ImageService

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
    """

    @mcp.tool(tags={"write"})
    async def generate_image(
        prompt: str,
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the desired image.
            provider: Provider name or ``"auto"`` for automatic selection.
            negative_prompt: Things to avoid in the image.
            aspect_ratio: Desired ratio (``1:1``, ``16:9``, ``9:16``,
                ``3:2``, ``2:3``).
            quality: Quality level (``standard`` or ``hd``).

        Returns:
            The generated image as ImageContent with metadata.
        """
        provider_name, result = await service.generate(
            prompt,
            provider=provider,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
        )

        # Save to scratch directory (blocking I/O → offload to thread)
        file_path = await asyncio.to_thread(
            service.save_to_scratch, result, provider_name
        )

        # Build base64 for MCP ImageContent
        b64_data = service.get_image_base64(result)

        # Build metadata
        metadata = {
            **result.provider_metadata,
            "provider": provider_name,
            "file_path": str(file_path),
            "size_bytes": result.size_bytes,
        }

        return ToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=b64_data,
                    mimeType=result.content_type,
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
