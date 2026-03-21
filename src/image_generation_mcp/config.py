"""Configuration loading from environment variables.

All environment variables share the ``IMAGE_GENERATION_MCP_`` prefix (controlled by
:data:`_ENV_PREFIX`).  Add your domain-specific configuration fields to
:class:`ServerConfig` and read them in :func:`load_config`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Change this to match your service.  All env vars will be prefixed with it.
# e.g. _ENV_PREFIX = "WEATHER_MCP" → WEATHER_MCP_READ_ONLY, WEATHER_MCP_PORT …
# ---------------------------------------------------------------------------
_ENV_PREFIX = "IMAGE_GENERATION_MCP"


def _env(name: str, default: str | None = None) -> str | None:
    """Return the value of ``{_ENV_PREFIX}_{name}`` from the environment.

    Args:
        name: Suffix after the prefix (e.g. ``"READ_ONLY"``).
        default: Fallback when the variable is unset.

    Returns:
        The environment variable value, or *default*.
    """
    return os.environ.get(f"{_ENV_PREFIX}_{name}", default)


def _parse_bool(value: str) -> bool:
    """Parse a boolean from an environment variable string.

    Treats ``"true"``, ``"1"``, and ``"yes"`` (case-insensitive) as ``True``.

    Args:
        value: Raw environment variable string.

    Returns:
        ``True`` for truthy strings, ``False`` otherwise.
    """
    return value.strip().lower() in ("true", "1", "yes")


_DEFAULT_SCRATCH_DIR = Path.home() / ".image-generation-mcp" / "images"


@dataclass
class ServerConfig:
    """Server configuration loaded from environment variables.

    Attributes:
        read_only: When ``True`` (default), write-tagged tools are hidden.
        scratch_dir: Directory for saving generated images.
        openai_api_key: OpenAI API key for gpt-image-1 / dall-e-3.
        a1111_host: Automatic1111 WebUI base URL.
        default_provider: Default provider for generation (``"auto"``
            selects based on prompt analysis).
        transform_cache_size: Maximum number of transformed image results
            to keep in the in-memory LRU cache.
        base_url: Public base URL of the server.  Required for OIDC and
            for constructing artifact download links.
    """

    read_only: bool = True
    scratch_dir: Path = field(default_factory=lambda: _DEFAULT_SCRATCH_DIR)
    openai_api_key: str | None = None
    a1111_host: str | None = None
    a1111_model: str | None = None
    default_provider: str = "auto"
    transform_cache_size: int = 64
    base_url: str | None = None


def load_config() -> ServerConfig:
    """Load configuration from environment variables.

    Reads:

    - ``IMAGE_GENERATION_MCP_READ_ONLY``: disable write tools; default ``true``.
    - ``IMAGE_GENERATION_MCP_SCRATCH_DIR``: image save directory.
    - ``IMAGE_GENERATION_MCP_OPENAI_API_KEY``: OpenAI API key.
    - ``IMAGE_GENERATION_MCP_A1111_HOST``: A1111 WebUI URL.
    - ``IMAGE_GENERATION_MCP_A1111_MODEL``: A1111 checkpoint name for preset detection.
    - ``IMAGE_GENERATION_MCP_DEFAULT_PROVIDER``: default provider; default ``"auto"``.
    - ``IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE``: transform LRU cache size; default ``64``.
    - ``IMAGE_GENERATION_MCP_BASE_URL``: public base URL, required for OIDC and
      artifact download links.

    Returns:
        A populated :class:`ServerConfig` instance.
    """
    raw_read_only = _env("READ_ONLY")

    # Build kwargs — only set values that are explicitly configured,
    # letting ServerConfig dataclass defaults apply for the rest.
    kwargs: dict[str, Any] = {}

    if raw_read_only is not None:
        kwargs["read_only"] = _parse_bool(raw_read_only)

    if raw_scratch := _env("SCRATCH_DIR"):
        kwargs["scratch_dir"] = Path(raw_scratch)

    if key := _env("OPENAI_API_KEY"):
        kwargs["openai_api_key"] = key

    if host := _env("A1111_HOST"):
        kwargs["a1111_host"] = host

    if model := _env("A1111_MODEL"):
        kwargs["a1111_model"] = model

    if provider := _env("DEFAULT_PROVIDER"):
        kwargs["default_provider"] = provider

    if raw_cache_size := _env("TRANSFORM_CACHE_SIZE"):
        try:
            kwargs["transform_cache_size"] = int(raw_cache_size)
        except ValueError:
            logger.warning(
                "Invalid TRANSFORM_CACHE_SIZE=%r — using default 64", raw_cache_size
            )

    if base_url := _env("BASE_URL"):
        kwargs["base_url"] = base_url.rstrip("/")

    config = ServerConfig(**kwargs)
    logger.debug("load_config: read_only=%s (raw=%r)", config.read_only, raw_read_only)
    return config
