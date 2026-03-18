"""Configuration loading from environment variables.

All environment variables share the ``IMAGE_GEN_MCP_`` prefix (controlled by
:data:`_ENV_PREFIX`).  Add your domain-specific configuration fields to
:class:`ServerConfig` and read them in :func:`load_config`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Change this to match your service.  All env vars will be prefixed with it.
# e.g. _ENV_PREFIX = "WEATHER_MCP" → WEATHER_MCP_READ_ONLY, WEATHER_MCP_PORT …
# ---------------------------------------------------------------------------
_ENV_PREFIX = "IMAGE_GEN_MCP"


def get_log_level() -> int:
    """Return the configured log level from ``IMAGE_GEN_MCP_LOG_LEVEL``.

    Accepts standard Python level names (``DEBUG``, ``INFO``, ``WARNING``,
    ``ERROR``).  Falls back to :data:`logging.INFO` when the variable is
    unset or contains an unrecognised value.

    Returns:
        An ``int`` log level constant from the :mod:`logging` module.
    """
    raw = os.environ.get(f"{_ENV_PREFIX}_LOG_LEVEL", "").strip().upper()
    if not raw:
        return logging.INFO
    level = logging.getLevelNamesMapping().get(raw)
    if level is None:
        logger.warning("Unrecognised LOG_LEVEL=%r — falling back to INFO", raw)
        return logging.INFO
    return level


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


_DEFAULT_SCRATCH_DIR = Path.home() / ".image-gen-mcp" / "images"


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
    """

    read_only: bool = True
    scratch_dir: Path = field(default_factory=lambda: _DEFAULT_SCRATCH_DIR)
    openai_api_key: str | None = None
    a1111_host: str | None = None
    default_provider: str = "auto"


def load_config() -> ServerConfig:
    """Load configuration from environment variables.

    Reads:

    - ``IMAGE_GEN_MCP_READ_ONLY``: disable write tools; default ``true``.
    - ``IMAGE_GEN_MCP_SCRATCH_DIR``: image save directory.
    - ``IMAGE_GEN_MCP_OPENAI_API_KEY``: OpenAI API key.
    - ``IMAGE_GEN_MCP_A1111_HOST``: A1111 WebUI URL.
    - ``IMAGE_GEN_MCP_DEFAULT_PROVIDER``: default provider; default ``"auto"``.

    Returns:
        A populated :class:`ServerConfig` instance.
    """
    raw_read_only = _env("READ_ONLY")
    read_only = _parse_bool(raw_read_only) if raw_read_only is not None else True
    logger.debug("load_config: read_only=%s (raw=%r)", read_only, raw_read_only)

    raw_scratch = _env("SCRATCH_DIR")
    scratch_dir = Path(raw_scratch) if raw_scratch else _DEFAULT_SCRATCH_DIR

    return ServerConfig(
        read_only=read_only,
        scratch_dir=scratch_dir,
        openai_api_key=_env("OPENAI_API_KEY"),
        a1111_host=_env("A1111_HOST"),
        default_provider=_env("DEFAULT_PROVIDER") or "auto",
    )
