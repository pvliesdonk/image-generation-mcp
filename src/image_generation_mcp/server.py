"""Image Generation MCP — FastMCP server entry point.

Composes the primitives from ``fastmcp-pvl-core`` into IG's
``make_server()``.  See https://gofastmcp.com/servers for the FastMCP
server surface and the fastmcp-pvl-core README for the helpers used here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.server.transforms import ResourcesAsTools
from fastmcp_pvl_core import (
    ServerConfig,
    build_auth,
    build_instructions,
    build_kv_store,  # noqa: F401  — re-exported for downstream projects' convenience
    configure_logging_from_env,
    env,
    register_server_info_tool,
    resolve_auth_mode,
    wire_middleware_stack,
)
from mcp.types import Icon

from image_generation_mcp._server_deps import _service_context
from image_generation_mcp.config import _ENV_PREFIX, ProjectConfig
from image_generation_mcp.prompts import register_prompts
from image_generation_mcp.resources import register_resources
from image_generation_mcp.tools import register_tools

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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
    mode = resolve_auth_mode(_load_server_config())
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
        config = ProjectConfig.from_env()
    configure_logging_from_env()

    # Operator override: INSTRUCTIONS replaces the default instructions text
    # (the override build_instructions' hint advertises), falling back to the
    # domain default when unset/empty. server_name is resolved from config below
    # (config.server_name, honouring an injected make_server(config=...)).
    instructions = env(_ENV_PREFIX, "INSTRUCTIONS") or build_instructions(
        read_only=config.read_only,
        env_prefix=_ENV_PREFIX,
        domain_line=(
            "AI image generation server supporting multiple providers "
            "(OpenAI gpt-image-2/dall-e-3, Google Gemini image, "
            "Stable Diffusion via SD WebUI, and a zero-cost placeholder). "
            "Start by calling list_providers to see configured providers."
        ),
    )

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

    @asynccontextmanager
    async def _lifespan(_mcp: object) -> AsyncIterator[dict[str, Any]]:
        """Bind the config ``make_server`` resolved to the service lifespan.

        ``server_lifespan`` is the env-loading standalone entry; here we reuse
        the already-resolved ``config`` so a caller-injected config governs the
        service and config is not loaded a second time at startup.
        """
        async with _service_context(config) as state:
            yield state

    mcp = FastMCP(
        name=server_name,
        instructions=instructions,
        icons=[Icon(src=_LUCIDE.format("palette"), mimeType="image/svg+xml")],
        lifespan=_lifespan,
        auth=auth,
    )

    wire_middleware_stack(mcp)

    register_tools(mcp, transport=transport)
    register_resources(mcp)
    register_prompts(mcp)

    register_server_info_tool(
        mcp,
        server_name=server_name,
        server_version=pkg_ver,
        # DOMAIN-UPSTREAM-START — wire upstream version reporting for servers
        # that talk to a remote service (paperless-mcp, etc.). The provider is
        # a zero-arg callable; the simplest pattern is a module-level upstream
        # client (typically constructed from env vars at import time) whose
        # version method is referenced here. ``CurrentContext()`` is a FastMCP
        # DI marker — it only resolves to a live context when used as a
        # parameter default in a tool/resource handler, so it cannot be called
        # directly from a zero-arg provider.
        # Uncomment the kwargs below as additional arguments to this call:
        # upstream_version=lambda: _upstream_client.remote_version(),
        # upstream_label="paperless",
        # DOMAIN-UPSTREAM-END
    )

    # DOMAIN-WIRING-START — project-specific wiring (custom HTTP routes,
    # transforms, mode toggles, alternative middleware, additional registrations);
    # kept across copier update. Leave empty for projects that don't customise
    # make_server() beyond the standard scaffold.
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
    # DOMAIN-WIRING-END

    return mcp
