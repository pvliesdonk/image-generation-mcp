"""Tests for background task support and progress reporting."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp import FastMCP

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService


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
    assert "_KEEPALIVE_INTERVAL_S" in source


async def test_keepalive_fires_during_slow_generate(tmp_path: object) -> None:
    """Keepalive sends ctx.info() when generation takes longer than the interval."""
    from pathlib import Path

    tmp = Path(str(tmp_path))
    svc = ImageService(scratch_dir=tmp)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    # Wrap generate to introduce a delay longer than the keepalive interval
    original_generate = svc.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.05)
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    svc.generate = slow_generate  # type: ignore[assignment]

    mcp = FastMCP("test")
    register_tools(mcp)
    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    cfg = MagicMock()
    cfg.paid_providers = frozenset()
    progress = MagicMock()
    progress.set_total = AsyncMock()
    progress.set_message = AsyncMock()
    progress.increment = AsyncMock()

    with patch("image_generation_mcp._server_tools._KEEPALIVE_INTERVAL_S", 0.01):
        await tool.fn(
            prompt="keepalive test",
            provider="placeholder",
            service=svc,
            config=cfg,
            ctx=ctx,
            progress=progress,
        )

    # ctx.info should have been called at least once by the keepalive task
    assert ctx.info.call_count >= 1
    msg = ctx.info.call_args_list[0][0][0]
    assert "Image generation in progress" in msg


async def test_keepalive_handles_ctx_info_exception(tmp_path: object) -> None:
    """Keepalive continues even if ctx.info() raises an exception."""
    from pathlib import Path

    tmp = Path(str(tmp_path))
    svc = ImageService(scratch_dir=tmp)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    original_generate = svc.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.05)
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    svc.generate = slow_generate  # type: ignore[assignment]

    mcp = FastMCP("test")
    register_tools(mcp)
    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    # First call raises, subsequent calls succeed
    ctx.info = AsyncMock(side_effect=[RuntimeError("connection lost"), None, None])
    cfg = MagicMock()
    cfg.paid_providers = frozenset()
    progress = MagicMock()
    progress.set_total = AsyncMock()
    progress.set_message = AsyncMock()
    progress.increment = AsyncMock()

    with patch("image_generation_mcp._server_tools._KEEPALIVE_INTERVAL_S", 0.01):
        # Should not raise despite ctx.info() failure
        result = await tool.fn(
            prompt="error test",
            provider="placeholder",
            service=svc,
            config=cfg,
            ctx=ctx,
            progress=progress,
        )

    # Generation still succeeded
    assert result is not None
