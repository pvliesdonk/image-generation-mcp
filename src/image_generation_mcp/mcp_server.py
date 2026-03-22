"""Generic FastMCP server scaffold.

Exposes tools, resources, and prompts registered in the ``_server_*``
submodules.  Uses a lifespan hook to build the service object once at
startup and tear it down on shutdown.

The server is configured entirely via environment variables (see
:mod:`image_generation_mcp.config`).  Call :func:`create_server` to
build a configured :class:`~fastmcp.FastMCP` instance.
"""

from __future__ import annotations

import logging
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.transforms import ResourcesAsTools

from image_generation_mcp.config import _ENV_PREFIX, load_config

from ._server_deps import make_service_lifespan
from ._server_prompts import register_prompts
from ._server_resources import register_resources
from ._server_tools import register_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def _build_default_instructions(*, read_only: bool) -> str:
    """Build the default instructions string based on read-only state.

    Args:
        read_only: Whether write tools are disabled on this instance.

    Returns:
        Instructions string suitable for the ``instructions`` parameter
        of :class:`~fastmcp.FastMCP`.
    """
    mode_line = (
        "This instance is READ-ONLY — image generation is disabled."
        if read_only
        else "This instance is READ-WRITE — image generation is available."
    )
    return (
        "AI image generation server supporting multiple providers "
        "(OpenAI gpt-image-1/dall-e-3, Stable Diffusion via A1111, "
        "and a zero-cost placeholder). "
        f"{mode_line} "
        "Start by calling list_providers to see which providers are "
        "configured, then use generate_image to create images."
    )


def _build_bearer_auth() -> Any:
    """Build a StaticTokenVerifier from ``IMAGE_GENERATION_MCP_BEARER_TOKEN``.

    When the env var is set (non-empty), returns a
    :class:`~fastmcp.server.auth.StaticTokenVerifier` that
    validates ``Authorization: Bearer <token>`` headers against the
    configured static token.

    Returns:
        A configured ``StaticTokenVerifier``, or ``None`` when the env var
        is absent or empty.
    """
    token = os.environ.get(f"{_ENV_PREFIX}_BEARER_TOKEN", "").strip()
    if not token:
        logger.debug("Bearer auth: BEARER_TOKEN not set — skipping")
        return None
    logger.debug("Bearer auth: BEARER_TOKEN is set (value redacted)")
    from fastmcp.server.auth import StaticTokenVerifier

    return StaticTokenVerifier(
        tokens={token: {"client_id": "bearer", "scopes": ["read", "write"]}}
    )


def _resolve_auth_mode() -> str | None:
    """Determine OIDC auth mode from env vars.

    Auto-detection logic:

    - Explicit ``AUTH_MODE`` env var takes precedence (``remote`` or ``oidc-proxy``).
    - If ``BASE_URL`` + ``OIDC_CONFIG_URL`` + ``CLIENT_ID`` + ``CLIENT_SECRET``
      are set → ``oidc-proxy`` (backward compatible).
    - If ``BASE_URL`` + ``OIDC_CONFIG_URL`` are set (no client credentials)
      → ``remote``.
    - Otherwise → ``None`` (no OIDC).

    Returns:
        ``"remote"``, ``"oidc-proxy"``, or ``None``.
    """
    explicit = os.environ.get(f"{_ENV_PREFIX}_AUTH_MODE", "").strip().lower()
    if explicit in ("remote", "oidc-proxy"):
        return explicit
    if explicit:
        logger.warning(
            "AUTH_MODE=%r is not a recognised value (expected 'remote' or "
            "'oidc-proxy') — falling back to auto-detection",
            explicit,
        )

    base_url = os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip()
    config_url = os.environ.get(f"{_ENV_PREFIX}_OIDC_CONFIG_URL", "").strip()
    client_id = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_SECRET", "").strip()

    if client_id and client_secret and config_url and base_url:
        return "oidc-proxy"
    if config_url and base_url:
        return "remote"
    return None


def _build_remote_auth() -> Any:
    """Build a RemoteAuthProvider for local JWT validation.

    Requires ``BASE_URL`` and ``OIDC_CONFIG_URL``.  Fetches the OIDC
    discovery document at startup to obtain ``jwks_uri`` and ``issuer``,
    then constructs a :class:`~fastmcp.server.auth.JWTVerifier` for
    local token validation.

    Does NOT require ``CLIENT_ID``, ``CLIENT_SECRET``, or ``JWT_SIGNING_KEY``.

    Returns:
        A configured :class:`~fastmcp.server.auth.RemoteAuthProvider`,
        or ``None`` when required env vars are missing.
    """
    base_url = os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip()
    config_url = os.environ.get(f"{_ENV_PREFIX}_OIDC_CONFIG_URL", "").strip()

    if not base_url or not config_url:
        missing = [
            name
            for name, val in [("BASE_URL", base_url), ("OIDC_CONFIG_URL", config_url)]
            if not val
        ]
        logger.debug("Remote auth: disabled — missing env vars: %s", ", ".join(missing))
        return None

    import httpx

    try:
        resp = httpx.get(config_url, timeout=10)
        resp.raise_for_status()
        discovery = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error(
            "Remote auth: failed to fetch OIDC discovery from %s: %s", config_url, exc
        )
        return None

    jwks_uri = discovery.get("jwks_uri")
    issuer = discovery.get("issuer")
    if not jwks_uri or not issuer:
        logger.error(
            "Remote auth: OIDC discovery missing jwks_uri or issuer at %s", config_url
        )
        return None

    audience = os.environ.get(f"{_ENV_PREFIX}_OIDC_AUDIENCE", "").strip() or None
    raw_scopes = os.environ.get(f"{_ENV_PREFIX}_OIDC_REQUIRED_SCOPES", "").strip()
    required_scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()] or None

    from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider

    verifier = JWTVerifier(
        jwks_uri=jwks_uri,
        issuer=issuer,
        audience=audience,
        required_scopes=required_scopes,
    )

    logger.debug(
        "Remote auth config:\n"
        "  config_url      = %s\n"
        "  issuer          = %s\n"
        "  jwks_uri        = %s\n"
        "  base_url        = %s\n"
        "  audience        = %s\n"
        "  required_scopes = %s",
        config_url,
        issuer,
        jwks_uri,
        base_url,
        audience or "(not set)",
        required_scopes or "(not set)",
    )

    logger.info("OIDC auth enabled (remote — token validation only)")

    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[issuer],
        base_url=base_url,
    )


def _build_oidc_auth() -> Any:
    """Build an OIDCProxy auth provider from environment variables, or return None.

    All four of ``BASE_URL``, ``OIDC_CONFIG_URL``, ``OIDC_CLIENT_ID``, and
    ``OIDC_CLIENT_SECRET`` must be set to enable authentication.  If any is
    absent the server starts unauthenticated.

    By default the proxy verifies the upstream ``id_token`` (a standard JWT
    per OIDC Core) instead of the ``access_token``.  This works with every
    OIDC provider — including those that issue opaque access tokens (e.g.
    Authelia).  Set ``IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN=true`` to revert to
    access-token verification when you know the provider issues JWT access
    tokens and you need audience-claim validation on that token.

    Returns:
        A configured :class:`~fastmcp.server.auth.oidc_proxy.OIDCProxy` instance,
        or ``None`` when authentication is disabled.
    """
    base_url = os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip()
    config_url = os.environ.get(f"{_ENV_PREFIX}_OIDC_CONFIG_URL", "").strip()
    client_id = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get(f"{_ENV_PREFIX}_OIDC_CLIENT_SECRET", "").strip()

    if not all([base_url, config_url, client_id, client_secret]):
        missing = [
            name
            for name, val in [
                ("BASE_URL", base_url),
                ("OIDC_CONFIG_URL", config_url),
                ("OIDC_CLIENT_ID", client_id),
                ("OIDC_CLIENT_SECRET", client_secret),
            ]
            if not val
        ]
        logger.debug("OIDC auth: disabled — missing env vars: %s", ", ".join(missing))
        return None

    from fastmcp.server.auth.oidc_proxy import OIDCProxy

    jwt_signing_key = (
        os.environ.get(f"{_ENV_PREFIX}_OIDC_JWT_SIGNING_KEY", "").strip() or None
    )
    audience = os.environ.get(f"{_ENV_PREFIX}_OIDC_AUDIENCE", "").strip() or None
    raw_scopes = os.environ.get(f"{_ENV_PREFIX}_OIDC_REQUIRED_SCOPES", "openid").strip()
    required_scopes = [s.strip() for s in raw_scopes.split(",") if s.strip()] or [
        "openid"
    ]

    verify_access_token = os.environ.get(
        f"{_ENV_PREFIX}_OIDC_VERIFY_ACCESS_TOKEN", ""
    ).strip().lower() in ("true", "1", "yes")
    verify_id_token = not verify_access_token

    logger.debug(
        "OIDC auth config:\n"
        "  config_url          = %s\n"
        "  client_id           = %s\n"
        "  client_secret       = <redacted>\n"
        "  base_url            = %s\n"
        "  audience            = %s\n"
        "  required_scopes     = %s\n"
        "  jwt_signing_key     = %s\n"
        "  verify_id_token     = %s\n"
        "  verify_access_token = %s",
        config_url,
        client_id,
        base_url,
        audience or "(not set)",
        required_scopes,
        "(set)" if jwt_signing_key else "(not set)",
        verify_id_token,
        verify_access_token,
    )

    if verify_id_token and "openid" not in required_scopes:
        logger.warning(
            "OIDC: verify_id_token=True requires the 'openid' scope but it is "
            "not in IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES — the id_token may "
            "be absent from the token response; add 'openid' to the scope list "
            "or set IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN=true"
        )

    if jwt_signing_key is None and sys.platform.startswith("linux"):
        logger.warning(
            "OIDC: IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY is not set — "
            "the JWT signing key is ephemeral on Linux; all clients must "
            "re-authenticate after every server restart"
        )

    if verify_id_token:
        logger.info(
            "OIDC: verifying upstream id_token (works with opaque access tokens)"
        )
    else:
        logger.info(
            "OIDC: verifying upstream access_token as JWT "
            "(IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN=true)"
        )

    logger.info("OIDC auth enabled (oidc-proxy — DCR emulation)")

    return OIDCProxy(
        config_url=config_url,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        audience=audience,
        required_scopes=required_scopes,
        jwt_signing_key=jwt_signing_key,
        verify_id_token=verify_id_token,
        require_authorization_consent=False,
    )


def create_server(transport: str = "stdio") -> FastMCP:
    """Create and configure the FastMCP server.

    Reads configuration from environment variables via :func:`load_config`.
    Write tools are tagged with ``{"write"}`` and hidden via
    ``mcp.disable(tags={"write"})`` when ``READ_ONLY=true``.

    Server identity is configurable via:

    - ``IMAGE_GENERATION_MCP_SERVER_NAME``: MCP server name shown to clients
      (default ``"image-generation-mcp"``).
    - ``IMAGE_GENERATION_MCP_INSTRUCTIONS``: system-level instructions injected
      into LLM context (default: dynamic description reflecting read-only state).

    Args:
        transport: The MCP transport in use (``"stdio"``, ``"sse"``, or
            ``"http"``).  Certain tools (e.g. ``create_download_link``) are
            only registered for HTTP-capable transports.

    Returns:
        A fully configured :class:`~fastmcp.FastMCP` instance ready to run.
    """
    config = load_config()
    is_read_only = config.read_only

    server_name = os.environ.get(f"{_ENV_PREFIX}_SERVER_NAME", "image-generation-mcp")
    default_instructions = _build_default_instructions(read_only=is_read_only)
    instructions = os.environ.get(f"{_ENV_PREFIX}_INSTRUCTIONS", default_instructions)

    bearer_auth = _build_bearer_auth()

    oidc_mode = _resolve_auth_mode()
    if oidc_mode == "remote":
        oidc_auth = _build_remote_auth()
    elif oidc_mode == "oidc-proxy":
        oidc_auth = _build_oidc_auth()
    else:
        oidc_auth = None

    if oidc_mode and not oidc_auth:
        logger.warning(
            "AUTH_MODE=%s requested but OIDC auth could not be initialized "
            "— check env vars and OIDC discovery endpoint",
            oidc_mode,
        )

    if bearer_auth and oidc_auth:
        from fastmcp.server.auth import MultiAuth

        auth = MultiAuth(server=oidc_auth, verifiers=[bearer_auth], required_scopes=[])
        auth_mode = f"multi({oidc_mode}+bearer)"
        logger.info(
            "Multi-auth enabled: bearer token + OIDC %s (either accepted)", oidc_mode
        )
    elif bearer_auth:
        auth = bearer_auth
        auth_mode = "bearer"
        logger.info("Bearer token auth enabled")
    elif oidc_auth:
        auth = oidc_auth
        auth_mode = oidc_mode or "oidc"
    else:
        auth = None
        auth_mode = "none"
        logger.info("No auth configured — server accepts unauthenticated connections")

    try:
        server_version = version("image-generation-mcp")
    except PackageNotFoundError:
        server_version = "dev"
    logger.info(
        "Server config: name=%s version=%s auth=%s mode=%s",
        server_name,
        server_version,
        auth_mode,
        "read-only" if is_read_only else "read-write",
    )

    mcp = FastMCP(
        server_name,
        instructions=instructions,
        lifespan=make_service_lifespan(config),
        auth=auth,
    )

    register_tools(mcp, transport=transport)
    register_resources(mcp)
    register_prompts(mcp)

    # Mount artifact download endpoint for HTTP transports
    if transport != "stdio":
        from image_generation_mcp.artifacts import make_artifact_handler

        artifact_handler = make_artifact_handler()

        from starlette.requests import Request
        from starlette.responses import Response

        @mcp.custom_route("/artifacts/{token}", methods=["GET"])
        async def _artifact_route(request: Request) -> Response:
            return await artifact_handler(request)

    # Expose resources as tools for clients that lack resource support
    # (e.g. Claude webchat via MCP). Generates list_resources/read_resource.
    # NOTE: ResourcesAsTools exposes ALL resources. If a future resource is
    # write-tagged (hidden in read-only mode), it would still be reachable
    # via read_resource unless the transform is updated with a filter.
    mcp.add_transform(ResourcesAsTools(mcp))

    # --- Visibility: hide write-tagged components in read-only mode ---

    if is_read_only:
        mcp.disable(tags={"write"})

    return mcp
