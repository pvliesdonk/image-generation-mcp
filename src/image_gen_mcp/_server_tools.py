"""MCP tool registrations.

TODO: Replace the example tools with your domain tools.

Each tool function is decorated with ``@mcp.tool()`` inside
:func:`register_tools`.  Write tools should be tagged with
``tags={"write"}`` so they can be hidden in read-only mode via
``mcp.disable(tags={"write"})``.

See https://gofastmcp.com/servers/tools for the full tool API.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._server_deps import get_service

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
    """

    # -----------------------------------------------------------------------
    # Example read tool — replace with your domain tools.
    # -----------------------------------------------------------------------

    @mcp.tool()
    def ping(ctx: Any = Depends(get_service)) -> str:  # noqa: ARG001
        """Health check.

        Returns:
            The string ``'pong'``.
        """
        return "pong"

    # -----------------------------------------------------------------------
    # Example write tool — tagged so it can be hidden in read-only mode.
    # -----------------------------------------------------------------------

    @mcp.tool(tags={"write"})
    def example_write(
        message: str,
        ctx: Any = Depends(get_service),  # noqa: ARG001
    ) -> str:
        """Example write operation — replace with your domain write tools.

        Args:
            message: The message to echo back.

        Returns:
            Confirmation string.
        """
        # TODO: Replace with your actual write logic.
        logger.info("example_write called: %r", message)
        return f"wrote: {message}"
