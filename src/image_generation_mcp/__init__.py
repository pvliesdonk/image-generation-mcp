"""Image Generation MCP — FastMCP server for AI image generation."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("image-generation-mcp")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
