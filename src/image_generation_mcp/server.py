"""Image Generation MCP — FastMCP server entry point.

Composes the primitives from ``fastmcp-pvl-core`` into IG's
``make_server()``.  See https://gofastmcp.com/servers for the FastMCP
server surface and the fastmcp-pvl-core README for the helpers used here.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastmcp import FastMCP
from fastmcp.server.event_store import EventStore
from fastmcp.server.transforms import ResourcesAsTools
from fastmcp_pvl_core import (
    ServerConfig,
    build_auth,
    build_instructions,
    configure_logging_from_env,
    wire_middleware_stack,
)
from fastmcp_pvl_core import (
    build_event_store as _core_build_event_store,
)
from fastmcp_pvl_core import (
    resolve_auth_mode as _core_resolve_auth_mode,
)
from mcp.types import Icon

from image_generation_mcp._server_deps import make_service_lifespan
from image_generation_mcp._server_prompts import register_prompts
from image_generation_mcp._server_resources import register_resources
from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.config import _ENV_PREFIX, ProjectConfig

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"
_DEFAULT_SERVER_NAME = "image-generation-mcp"


def _load_server_config() -> ServerConfig:
    """Load only the generic ``ServerConfig`` slice from IG env vars.

    Compat helper used by ``_resolve_auth_mode`` / ``_build_remote_auth``
    wrappers that preserve their historical zero-arg call shape.
    """
    return ServerConfig.from_env(env_prefix=_ENV_PREFIX)


def _resolve_auth_mode() -> str | None:
    """Resolve the configured auth mode from IG env vars.

    Backward-compat wrapper around :func:`fastmcp_pvl_core.resolve_auth_mode`
    that still returns ``None`` (not ``"none"``) when no auth is configured,
    matching the pre-retrofit contract expected by tests.
    """
    mode = _core_resolve_auth_mode(_load_server_config())
    return None if mode == "none" else mode


def _build_remote_auth() -> object | None:
    """Build a ``RemoteAuthProvider`` from IG env vars, or ``None``.

    Backward-compat wrapper around
    :func:`fastmcp_pvl_core.build_remote_auth`.
    """
    from fastmcp_pvl_core import build_remote_auth

    return build_remote_auth(_load_server_config())


def _build_bearer_auth() -> object | None:
    """Build a ``StaticTokenVerifier`` from IG env vars, or ``None``.

    Backward-compat wrapper around
    :func:`fastmcp_pvl_core.build_bearer_auth`.
    """
    from fastmcp_pvl_core import build_bearer_auth

    return build_bearer_auth(_load_server_config())


def _build_oidc_auth() -> object | None:
    """Build an ``OIDCProxy`` from IG env vars, or ``None``.

    Backward-compat wrapper around
    :func:`fastmcp_pvl_core.build_oidc_proxy_auth`.
    """
    from fastmcp_pvl_core import build_oidc_proxy_auth

    return build_oidc_proxy_auth(_load_server_config())


# Module-level name used inside ``make_server`` + re-exported for tests.
resolve_auth_mode = _core_resolve_auth_mode


def build_event_store(url: str | None = None) -> EventStore:
    """Build an ``EventStore`` for SSE polling/resumability.

    Thin shim over :func:`fastmcp_pvl_core.build_event_store`: wraps the
    legacy URL-only call shape used by ``cli.py`` and delegates the actual
    backend selection to the shared core helper.

    Args:
        url: Event store URL from ``IMAGE_GENERATION_MCP_EVENT_STORE_URL``.

    Returns:
        A configured :class:`~mcp.server.streamable_http.EventStore`.
    """
    return _core_build_event_store(_ENV_PREFIX, ServerConfig(event_store_url=url))


def make_server(
    *,
    transport: str = "stdio",
    config: ProjectConfig | None = None,
) -> FastMCP:
    """Construct the Image Generation MCP FastMCP server.

    Args:
        transport: ``"stdio"`` / ``"http"`` / ``"sse"``.  HTTP-only
            features (artifact downloads) are wired only when transport
            != ``"stdio"``.
        config: Optional pre-loaded config; defaults to env-based load.

    Returns:
        A configured :class:`fastmcp.FastMCP` instance.
    """
    if config is None:
        from image_generation_mcp.config import load_config

        config = load_config()
    configure_logging_from_env()

    auth = build_auth(config.server)
    auth_mode = resolve_auth_mode(config.server) if auth is not None else "none"
    if auth_mode == "none":
        logger.warning(
            "No auth configured — server accepts unauthenticated connections"
        )
    else:
        logger.info("Auth enabled: mode=%s", auth_mode)

    try:
        pkg_ver = _pkg_version("image-generation-mcp")
    except PackageNotFoundError:
        pkg_ver = "unknown"

    server_name = config.server_name or _DEFAULT_SERVER_NAME

    logger.info(
        "Server config: name=%s version=%s auth=%s mode=%s",
        server_name,
        pkg_ver,
        auth_mode,
        "read-only" if config.read_only else "read-write",
    )

    mcp = FastMCP(
        name=server_name,
        instructions=build_instructions(
            read_only=config.read_only,
            env_prefix=_ENV_PREFIX,
            domain_line=(
                "AI image generation server supporting multiple providers "
                "(OpenAI gpt-image-1/dall-e-3, Google Gemini image, "
                "Stable Diffusion via SD WebUI, and a zero-cost placeholder). "
                "Start by calling list_providers to see configured providers."
            ),
        ),
        icons=[Icon(src=_LUCIDE.format("palette"), mimeType="image/svg+xml")],
        lifespan=make_service_lifespan(config),
        auth=auth,
    )

    wire_middleware_stack(mcp)

    register_tools(mcp, transport=transport)
    register_resources(mcp)
    register_prompts(mcp)

    if transport != "stdio":
        from image_generation_mcp.artifacts import make_artifact_handler

        artifact_handler = make_artifact_handler()

        from starlette.requests import Request
        from starlette.responses import Response

        @mcp.custom_route("/artifacts/{token}", methods=["GET"])
        async def _artifact_route(request: Request) -> Response:
            return await artifact_handler(request)

    # IG-specific: expose resources as tools for clients without resource support.
    # Apply AFTER all registrations so the transform sees every resource.
    mcp.add_transform(ResourcesAsTools(mcp))

    if config.read_only:
        mcp.disable(tags={"write"})

    return mcp
