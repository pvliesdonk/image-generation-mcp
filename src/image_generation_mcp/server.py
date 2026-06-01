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
    register_file_exchange,
    register_server_info_tool,
    resolve_auth_mode,
    wire_middleware_stack,
)
from fastmcp_pvl_core import (
    build_event_store as _core_build_event_store,
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

<<<<<<< before updating
    # MCP File Exchange wiring (spec-compliant): mounts /artifacts/{token},
    # registers create_download_link, advertises the experimental.file_exchange
    # capability.  Tools publish via the handle passed into register_tools.
    #
    # We pass `transport` explicitly (NOT "auto") because "auto" reads env
    # vars (`{PREFIX}_TRANSPORT` / `FASTMCP_TRANSPORT`) that the CLI doesn't
    # set — leaving "auto" would silently disable file-exchange in
    # production.  The CLI knows the transport from its own --transport flag
    # and passes it to make_server, so we have the authoritative value here.
    fx_transport: str = "http" if transport in ("http", "sse") else "stdio"
    file_exchange = register_file_exchange(
=======
    # Optional: enable opt-in per-subject authorization on tools / resources /
    # prompts.  See fastmcp-pvl-core's README "Authorization" section for the
    # design.  Tools, resources, and prompts opt in by setting
    # ``meta={"required_scope": "<scope>"}``; absence of the key means
    # unrestricted.  The middleware is only installed when ``acl_path`` is set.
    #
    # from fastmcp_pvl_core import (
    #     AuthorizationMiddleware,
    #     load_acl,
    #     make_acl_authorizer,
    # )
    #
    # if config.acl_path is not None:
    #     authorizer = make_acl_authorizer(load_acl(config.acl_path))
    #     mcp.add_middleware(AuthorizationMiddleware(authorizer=authorizer))

    register_tools(mcp)
    register_resources(mcp)
    register_prompts(mcp)
    register_apps(mcp)

    register_server_info_tool(
        mcp,
        server_name="image-generation-mcp",
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
    # DOMAIN-WIRING-END

    # DOMAIN-FILE-EXCHANGE-START — file-exchange wiring (download direction
    # always; upload direction opt-in by uncommenting). Kept across copier
    # update so opt-in customisations (consumer_sink=, produces=, upload
    # receiver) survive subsequent template updates.
    #
    # To publish files from a tool body, capture the returned handle
    # — see docs/guides/file-exchange.md for the module-level singleton
    # pattern (e.g. ``_file_exchange = register_file_exchange(...)``).
    register_file_exchange(
>>>>>>> after updating
        mcp,
        namespace="image-generation-mcp",
        env_prefix=_ENV_PREFIX,
        produces=("image/png", "image/webp", "image/jpeg"),
        transport=fx_transport,  # type: ignore[arg-type]
    )

<<<<<<< before updating
    register_tools(mcp, transport=transport, file_exchange=file_exchange)
    register_resources(mcp)
    register_prompts(mcp)

    # IG-specific: expose resources as tools for clients without resource support.
    # Apply AFTER all registrations so the transform sees every resource.
    mcp.add_transform(ResourcesAsTools(mcp))

    if config.read_only:
        mcp.disable(tags={"write"})
=======
    # Optional upload direction — uncomment + flesh out the helpers below
    # to accept agent-pushed files via POST /<namespace>/uploads/{token}.
    # The route mounts only when transport is HTTP/SSE AND
    # IMAGE_GENERATION_MCP_BASE_URL is set; sync receivers run in a thread.
    # See docs/guides/file-exchange.md for the full pattern. When
    # uncommenting, move the two ``from`` imports below to the
    # module-level import block at the top of this file.
    #
    # from typing import Any
    #
    # from fastmcp_pvl_core import (
    #     UploadRecord,
    #     register_file_exchange_upload,
    # )
    #
    # def _validate_upload_target(target_id: str, extra: dict[str, Any] | None) -> None:
    #     """Pre-link validator: reject obviously bad target_ids in-band.
    #
    #     Runs inside create_upload_link before the token is minted, so an
    #     LLM gets a clean tool error rather than after a wasted upload
    #     round-trip.
    #     """
    #     # Example: reject anything outside the domain's allowlist.
    #     # raise ValueError(f"target_id not allowed: {target_id}")
    #     pass
    #
    # def _upload_receiver(record: UploadRecord, body: bytes) -> dict[str, Any]:
    #     """Commit the uploaded bytes. Raise ValueError → 400,
    #     FileExistsError → 409, anything else → 500 (with traceback
    #     logged). Return value MUST be a dict — non-dict returns are
    #     treated as receiver bugs (500 + WARNING log)."""
    #     # TODO: replace with your storage logic.
    #     return {"path": record.target_id, "size_bytes": len(body)}
    #
    # register_file_exchange_upload(
    #     mcp,
    #     namespace="image-generation-mcp",
    #     env_prefix=_ENV_PREFIX,
    #     transport="auto",
    #     receiver=_upload_receiver,
    #     pre_link_validator=_validate_upload_target,
    # )
    # DOMAIN-FILE-EXCHANGE-END
>>>>>>> after updating

    return mcp
