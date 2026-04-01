"""Shared test helpers for the image-generation-mcp test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from fastmcp.tools import Tool


async def get_tool_including_app_only(mcp: FastMCP, name: str) -> Tool | None:
    """Get a tool by name, including app-only tools hidden from the model.

    fastmcp >=3.2 filters ``visibility=["app"]`` tools from
    :meth:`FastMCP.get_tool` and :meth:`FastMCP.list_tools`.
    This helper calls the *parent class* implementation (bypassing
    ``FastMCP``'s ``_is_model_visible`` filter) so tests can look up
    and invoke app-only tools directly.

    Uses ``super(FastMCP, mcp)`` rather than ``super(type(mcp), mcp)``
    to ensure we always skip exactly ``FastMCP``'s override, even if
    *mcp* is a subclass.
    """
    from fastmcp import FastMCP as _FastMCP

    return await super(_FastMCP, mcp).get_tool(name)
