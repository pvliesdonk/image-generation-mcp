"""Project configuration for image-generation-mcp.

Composes ``fastmcp_pvl_core.ServerConfig`` for transport/auth/event-store
fields; adds image-generation domain fields below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from fastmcp_pvl_core import ServerConfig, env, parse_bool, parse_list

logger = logging.getLogger(__name__)

_ENV_PREFIX = "IMAGE_GENERATION_MCP"


_DEFAULT_SCRATCH_DIR = Path.home() / ".image-generation-mcp" / "images"
_DEFAULT_STYLES_DIR = Path.home() / ".image-generation-mcp" / "styles"


@dataclass
class ProjectConfig:
    """Image-generation-mcp configuration loaded from environment variables.

    The ``server`` field carries generic FastMCP server config (transport,
    auth, event store). Domain fields (provider keys, scratch dir, etc.)
    live directly on this dataclass.
    """

    # CONFIG-FIELDS-START — image-generation domain fields; kept across copier update
    server: ServerConfig = field(default_factory=ServerConfig)
    server_name: str | None = None
    read_only: bool = True
    scratch_dir: Path = field(default_factory=lambda: _DEFAULT_SCRATCH_DIR)
    openai_api_key: str | None = None
    google_api_key: str | None = None
    sd_webui_host: str | None = None
    sd_webui_model: str | None = None
    default_provider: str = "auto"
    transform_cache_size: int = 64
    paid_providers: frozenset[str] = frozenset({"openai"})
    styles_dir: Path = field(default_factory=lambda: _DEFAULT_STYLES_DIR)
    # CONFIG-FIELDS-END


def load_config() -> ProjectConfig:
    """Load configuration from environment variables.

    Reads:

    - ``IMAGE_GENERATION_MCP_READ_ONLY``: disable write tools; default ``true``.
    - ``IMAGE_GENERATION_MCP_SCRATCH_DIR``: image save directory.
    - ``IMAGE_GENERATION_MCP_OPENAI_API_KEY``: OpenAI API key.
    - ``IMAGE_GENERATION_MCP_GOOGLE_API_KEY``: Google API key (Gemini).
    - ``IMAGE_GENERATION_MCP_SD_WEBUI_HOST``: SD WebUI URL (also accepts deprecated ``A1111_HOST``).
    - ``IMAGE_GENERATION_MCP_SD_WEBUI_MODEL``: SD WebUI checkpoint name (also accepts deprecated ``A1111_MODEL``).
    - ``IMAGE_GENERATION_MCP_DEFAULT_PROVIDER``: default provider; default ``"auto"``.
    - ``IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE``: transform LRU cache size; default ``64``.
    - ``IMAGE_GENERATION_MCP_PAID_PROVIDERS``: comma-separated list; default ``"openai"``.
    - ``IMAGE_GENERATION_MCP_STYLES_DIR``: style preset dir; default ``~/.image-generation-mcp/styles/``.

    Plus all generic ``ServerConfig`` env vars (BASE_URL, BEARER_TOKEN,
    OIDC_*, EVENT_STORE_URL, SERVER_NAME, INSTRUCTIONS) — see
    ``fastmcp_pvl_core.ServerConfig.from_env``.

    Returns:
        A populated :class:`ProjectConfig` instance.
    """
    server = ServerConfig.from_env(env_prefix=_ENV_PREFIX)

    # CONFIG-FROM-ENV-START — image-generation domain reads; kept across copier update
    server_name = env(_ENV_PREFIX, "SERVER_NAME")
    read_only = parse_bool(env(_ENV_PREFIX, "READ_ONLY", "true"))

    scratch_dir = Path(env(_ENV_PREFIX, "SCRATCH_DIR") or _DEFAULT_SCRATCH_DIR)

    openai_api_key = env(_ENV_PREFIX, "OPENAI_API_KEY")
    google_api_key = env(_ENV_PREFIX, "GOOGLE_API_KEY")

    sd_webui_host = env(_ENV_PREFIX, "SD_WEBUI_HOST")
    if not sd_webui_host and (legacy := env(_ENV_PREFIX, "A1111_HOST")):
        logger.warning(
            "IMAGE_GENERATION_MCP_A1111_HOST is deprecated — "
            "use IMAGE_GENERATION_MCP_SD_WEBUI_HOST instead"
        )
        sd_webui_host = legacy

    sd_webui_model = env(_ENV_PREFIX, "SD_WEBUI_MODEL")
    if not sd_webui_model and (legacy := env(_ENV_PREFIX, "A1111_MODEL")):
        logger.warning(
            "IMAGE_GENERATION_MCP_A1111_MODEL is deprecated — "
            "use IMAGE_GENERATION_MCP_SD_WEBUI_MODEL instead"
        )
        sd_webui_model = legacy

    default_provider = env(_ENV_PREFIX, "DEFAULT_PROVIDER") or "auto"
    if default_provider == "a1111":
        logger.warning(
            "DEFAULT_PROVIDER='a1111' is deprecated — use 'sd_webui' instead"
        )
        default_provider = "sd_webui"

    raw_cache = env(_ENV_PREFIX, "TRANSFORM_CACHE_SIZE")
    transform_cache_size = 64
    if raw_cache:
        try:
            transform_cache_size = int(raw_cache)
        except ValueError:
            logger.warning(
                "Invalid TRANSFORM_CACHE_SIZE=%r — using default 64", raw_cache
            )

    raw_paid = env(_ENV_PREFIX, "PAID_PROVIDERS")
    paid_providers = (
        frozenset(p.lower() for p in parse_list(raw_paid))
        if raw_paid is not None
        else frozenset({"openai"})
    )

    styles_dir = Path(env(_ENV_PREFIX, "STYLES_DIR") or _DEFAULT_STYLES_DIR)

    config = ProjectConfig(
        server=server,
        server_name=server_name,
        read_only=read_only,
        scratch_dir=scratch_dir,
        openai_api_key=openai_api_key,
        google_api_key=google_api_key,
        sd_webui_host=sd_webui_host,
        sd_webui_model=sd_webui_model,
        default_provider=default_provider,
        transform_cache_size=transform_cache_size,
        paid_providers=paid_providers,
        styles_dir=styles_dir,
    )
    # CONFIG-FROM-ENV-END

    logger.debug("load_config: read_only=%s", config.read_only)
    return config
