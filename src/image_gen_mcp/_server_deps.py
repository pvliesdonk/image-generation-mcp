"""Shared dependency injection and lifespan for the MCP server.

Provides :func:`get_service` and :func:`make_service_lifespan` which are
imported by the tool, resource, and prompt registration modules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.lifespan import lifespan

from image_gen_mcp.providers.placeholder import PlaceholderImageProvider
from image_gen_mcp.service import ImageService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from image_gen_mcp.config import ServerConfig

logger = logging.getLogger(__name__)


def make_service_lifespan(config: ServerConfig) -> Any:
    """Create a lifespan function that closes over a pre-loaded config.

    Args:
        config: A fully-loaded :class:`~image_gen_mcp.config.ServerConfig`
            instance produced by a single :func:`load_config` call in
            :func:`~image_gen_mcp.mcp_server.create_server`.

    Returns:
        A FastMCP lifespan coroutine that initialises the service object and
        yields ``{"service": service, "config": config}`` to the lifespan
        context.
    """

    @lifespan
    async def _service_lifespan(
        server: FastMCP,  # noqa: ARG001
    ) -> AsyncIterator[dict[str, Any]]:
        """Initialise the ImageService at server startup."""
        logger.info("Service starting up (read_only=%s)", config.read_only)

        service = ImageService(
            scratch_dir=config.scratch_dir,
            default_provider=config.default_provider,
        )

        # Always register placeholder (zero-cost, no API key needed)
        service.register_provider("placeholder", PlaceholderImageProvider())

        # Register OpenAI if API key is configured
        if config.openai_api_key:
            from image_gen_mcp.providers.openai import OpenAIImageProvider

            service.register_provider(
                "openai",
                OpenAIImageProvider(api_key=config.openai_api_key),
            )

        # Register A1111 if host is configured
        if config.a1111_host:
            from image_gen_mcp.providers.a1111 import A1111ImageProvider

            service.register_provider(
                "a1111",
                A1111ImageProvider(host=config.a1111_host, model=config.a1111_model),
            )

        try:
            yield {"service": service, "config": config}
        finally:
            for provider in service._providers.values():
                if hasattr(provider, "aclose"):
                    await provider.aclose()
            logger.info("Service shut down")

    return _service_lifespan


def get_service(ctx: Context = CurrentContext()) -> ImageService:
    """Resolve the ImageService from lifespan context.

    Used as a ``Depends()`` default in tool/resource/prompt signatures.

    Raises:
        RuntimeError: If the server lifespan has not run.
    """
    service = ctx.lifespan_context.get("service")
    if not isinstance(service, ImageService):
        msg = "Service not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return service
