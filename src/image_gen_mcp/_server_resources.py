"""MCP resource registrations.

Exposes provider capabilities and service info as MCP resources.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from image_gen_mcp._server_deps import get_service
from image_gen_mcp.providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_QUALITY_LEVELS,
)
from image_gen_mcp.service import ImageService


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register resources on.
    """

    @mcp.resource("info://providers")
    async def provider_capabilities(
        service: ImageService = Depends(get_service),
    ) -> str:
        """Available image generation providers and their capabilities.

        Returns:
            JSON with provider names, availability, and supported features.
        """
        providers = service.list_providers()
        return json.dumps(
            {
                "providers": providers,
                "supported_aspect_ratios": SUPPORTED_ASPECT_RATIOS,
                "supported_quality_levels": SUPPORTED_QUALITY_LEVELS,
            },
            indent=2,
        )
