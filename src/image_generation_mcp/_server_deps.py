"""Service lifespan + dependency injection for the MCP server.

Provides :func:`get_service` / :func:`get_config` (imported by the tool,
resource, and prompt registration modules) and :func:`server_lifespan`, the
template-conformant standalone (env-loading) lifespan.
:func:`~image_generation_mcp.server.make_server` binds its own already-resolved
config via :func:`_service_context` rather than calling ``server_lifespan``
directly (so config is not loaded twice).

Also exposes :func:`_get_service_from_store`, a module-level accessor used by
the artifact HTTP handler (which runs outside FastMCP request context).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, TypedDict

from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from image_generation_mcp.domain import ImageService
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider

if TYPE_CHECKING:
    from image_generation_mcp.config import ProjectConfig

logger = logging.getLogger(__name__)

# Module-level reference for non-MCP-context callers (e.g. artifact handler).
_service_store: ImageService | None = None


class LifespanState(TypedDict):
    """Shape of the lifespan context yielded to request handlers."""

    service: ImageService
    config: ProjectConfig


def _get_service_from_store() -> ImageService:
    """Return the module-level ImageService reference.

    Used by the artifact HTTP handler, which runs outside FastMCP's
    request-context dependency injection.

    Returns:
        The active :class:`~image_generation_mcp.domain.ImageService`.

    Raises:
        RuntimeError: If the server lifespan has not yet run.
    """
    if _service_store is None:
        msg = "Service not initialised — server lifespan has not run"
        raise RuntimeError(msg)
    return _service_store


@asynccontextmanager
async def _service_context(config: ProjectConfig) -> AsyncIterator[dict[str, Any]]:
    """Initialise the ImageService for ``config`` and yield the lifespan state.

    Split out so ``make_server`` can bind its already-resolved config (avoiding
    a second env load) and tests can drive provider registration with a crafted
    :class:`ProjectConfig`. :func:`server_lifespan` wraps this with
    :meth:`ProjectConfig.from_env` for standalone (no-``make_server``) use.

    Args:
        config: A fully-loaded :class:`~image_generation_mcp.config.ProjectConfig`.

    Yields:
        ``{"service": ImageService, "config": ProjectConfig}`` for the lifespan
        context.
    """
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
        set_artifact_store(None)
        await service.aclose()
        logger.info("Service shut down")


@asynccontextmanager
async def server_lifespan(_mcp: object) -> AsyncIterator[dict[str, Any]]:
    """Start the service on startup; stop it on shutdown.

    Template-conformant standalone lifespan that loads :class:`ProjectConfig`
    from the environment. ``make_server`` does NOT wire this directly — it binds
    its already-resolved config to :func:`_service_context` (avoiding a second
    load). Use ``server_lifespan`` to wire ``FastMCP(lifespan=...)`` without
    ``make_server``.
    """
    from image_generation_mcp.config import ProjectConfig

    async with _service_context(ProjectConfig.from_env()) as state:
        yield state


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
