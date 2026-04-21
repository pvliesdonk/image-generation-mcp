"""Shared dependency injection and lifespan for the MCP server.

Provides :func:`get_service` and :func:`make_service_lifespan` which are
imported by the tool, resource, and prompt registration modules.

Also exposes :func:`_get_service_from_store`, a module-level accessor used
by the artifact HTTP handler (which runs outside FastMCP request context).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.lifespan import lifespan

from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from image_generation_mcp.config import ProjectConfig

logger = logging.getLogger(__name__)

# Module-level reference for non-MCP-context callers (e.g. artifact handler).
_service_store: ImageService | None = None


def _get_service_from_store() -> ImageService:
    """Return the module-level ImageService reference.

    Used by the artifact HTTP handler, which runs outside FastMCP's
    request-context dependency injection.

    Returns:
        The active :class:`~image_generation_mcp.service.ImageService`.

    Raises:
        RuntimeError: If the server lifespan has not yet run.
    """
    if _service_store is None:
        msg = "Service not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return _service_store


def make_service_lifespan(config: ProjectConfig) -> Any:
    """Create a lifespan function that closes over a pre-loaded config.

    Args:
        config: A fully-loaded :class:`~image_generation_mcp.config.ProjectConfig`
            instance produced by a single :func:`load_config` call in
            :func:`~image_generation_mcp.mcp_server.create_server`.

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
        global _service_store

        logger.info("Service starting up (read_only=%s)", config.read_only)

        service = ImageService(
            scratch_dir=config.scratch_dir,
            default_provider=config.default_provider,
            transform_cache_size=config.transform_cache_size,
        )

        # Always register placeholder (zero-cost, no API key needed)
        service.register_provider("placeholder", PlaceholderImageProvider())

        # Register OpenAI if API key is configured
        if config.openai_api_key:
            from image_generation_mcp.providers.openai import OpenAIImageProvider

            service.register_provider(
                "openai",
                OpenAIImageProvider(api_key=config.openai_api_key),
            )

        # Register Gemini if API key is configured
        if config.google_api_key:
            from image_generation_mcp.providers.gemini import GeminiImageProvider

            service.register_provider(
                "gemini",
                GeminiImageProvider(api_key=config.google_api_key),
            )

        # Register SD WebUI if host is configured
        if config.sd_webui_host:
            from image_generation_mcp.providers.sd_webui import SdWebuiImageProvider

            service.register_provider(
                "sd_webui",
                SdWebuiImageProvider(
                    host=config.sd_webui_host, model=config.sd_webui_model
                ),
            )

        # Discover capabilities for all registered providers
        await service.discover_all_capabilities()

        # Load style library
        service.load_styles(config.styles_dir)

        # Populate module-level store for artifact handler access
        _service_store = service

        # Initialise artifact store
        from image_generation_mcp.artifacts import ArtifactStore, set_artifact_store

        artifact_store = ArtifactStore()
        set_artifact_store(artifact_store)

        try:
            yield {"service": service, "config": config}
        finally:
            _service_store = None
            await service.aclose()
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


def get_config(ctx: Context = CurrentContext()) -> ProjectConfig:
    """Resolve the ProjectConfig from lifespan context.

    Used as a ``Depends()`` default in tool/resource/prompt signatures.

    Raises:
        RuntimeError: If the server lifespan has not run.
    """
    from image_generation_mcp.config import ProjectConfig

    config = ctx.lifespan_context.get("config")
    if not isinstance(config, ProjectConfig):
        msg = "Config not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return config
