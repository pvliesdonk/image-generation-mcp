"""Tests for background task support and progress reporting."""

from __future__ import annotations

import inspect

from fastmcp import FastMCP

from mcp_imagegen._server_tools import register_tools


async def test_task_decorator_present() -> None:
    """generate_image tool metadata indicates task=True."""
    mcp = FastMCP("test")
    register_tools(mcp)

    tool = await mcp.get_tool("generate_image")  # type: ignore[misc]
    assert tool is not None
    assert tool.task_config is not None
    assert tool.task_config.mode == "optional"


async def test_list_providers_no_task() -> None:
    """list_providers tool does not have task support."""
    mcp = FastMCP("test")
    register_tools(mcp)

    tool = await mcp.get_tool("list_providers")
    assert tool is not None
    assert tool.task_config.mode == "forbidden"


async def test_progress_stages_present() -> None:
    """generate_image source contains 3 report_progress calls."""
    mcp = FastMCP("test")
    register_tools(mcp)

    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    # Inspect the function source for progress calls
    source = inspect.getsource(tool.fn)
    assert source.count("report_progress") == 3
    assert '"Generating image"' in source
    assert '"Saving to scratch"' in source
    assert '"Done"' in source
