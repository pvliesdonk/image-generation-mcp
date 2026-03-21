"""Tests for background task support and progress reporting."""

from __future__ import annotations

import inspect

from fastmcp import FastMCP

from image_generation_mcp._server_tools import register_tools


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
    """generate_image source uses Progress dependency with expected stages."""
    mcp = FastMCP("test")
    register_tools(mcp)

    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    # Inspect the function source for progress/keepalive calls
    source = inspect.getsource(tool.fn)
    assert "progress.set_total" in source
    assert "progress.increment" in source
    assert '"Generating image"' in source
    assert '"Saving to scratch"' in source
    assert '"Done"' in source


async def test_keepalive_present() -> None:
    """generate_image source contains keepalive mechanism."""
    mcp = FastMCP("test")
    register_tools(mcp)

    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    source = inspect.getsource(tool.fn)
    assert "_keepalive" in source
    assert "ctx.info" in source
