"""Shared test helpers for the image-generation-mcp test suite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from fastmcp import FastMCP
    from fastmcp.tools import Tool

    from image_generation_mcp.config import ProjectConfig


def service_lifespan(
    config: ProjectConfig,
) -> Callable[[object], Any]:
    """Build a FastMCP lifespan that initialises the service from ``config``.

    Test-only wrapper around the production
    :func:`image_generation_mcp._server_deps._service_context`: production
    ``server_lifespan`` loads :class:`ProjectConfig` from the environment, but
    tests need to inject a crafted config (temp scratch dir, specific provider
    keys) into a ``FastMCP(lifespan=...)`` server.
    """
    from image_generation_mcp._server_deps import _service_context

    @asynccontextmanager
    async def _lifespan(_mcp: object) -> AsyncIterator[dict[str, Any]]:
        async with _service_context(config) as state:
            yield state

    return _lifespan


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
