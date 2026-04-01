"""Tests for fire-and-forget background task support in generate_image."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from fastmcp import FastMCP
from mcp.types import TextContent

from image_generation_mcp._server_tools import _BACKGROUND_TASKS, register_tools
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


async def test_generate_image_returns_generating_immediately(
    tmp_path: Path,
) -> None:
    """generate_image returns status='generating' without waiting for completion."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    mcp = FastMCP("test")
    register_tools(mcp)
    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await tool.fn(
        prompt="fire-and-forget test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )

    text_items = [c for c in result.content if isinstance(c, TextContent)]
    assert len(text_items) == 1
    metadata = json.loads(text_items[0].text)
    assert metadata["status"] == "generating"
    assert "image_id" in metadata


async def test_background_tasks_set_holds_reference(tmp_path: Path) -> None:
    """_BACKGROUND_TASKS holds a strong reference to the task during generation."""
    svc = ImageService(scratch_dir=tmp_path)

    # Use a slow provider to keep the task alive long enough to inspect
    original_provider = PlaceholderImageProvider()
    original_generate = original_provider.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.2)
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    original_provider.generate = slow_generate  # type: ignore[assignment]
    svc.register_provider("placeholder", original_provider)

    mcp = FastMCP("test")
    register_tools(mcp)
    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    size_before = len(_BACKGROUND_TASKS)
    await tool.fn(
        prompt="background tasks test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )
    # Task was added to _BACKGROUND_TASKS while still running
    assert len(_BACKGROUND_TASKS) > size_before

    # Wait for the background task to finish
    await asyncio.sleep(0.5)
    # Task removed itself on completion
    assert len(_BACKGROUND_TASKS) == size_before


async def test_background_task_completes_after_return(tmp_path: Path) -> None:
    """Background task registers the image after generate_image returns."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    mcp = FastMCP("test")
    register_tools(mcp)
    tool = await mcp.get_tool("generate_image")
    assert tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await tool.fn(
        prompt="completion test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )

    text_items = [c for c in result.content if isinstance(c, TextContent)]
    image_id = json.loads(text_items[0].text)["image_id"]

    # Placeholder is near-instant; after a brief wait the image is registered
    await asyncio.sleep(0.1)

    show_tool = await mcp.get_tool("show_image")
    assert show_tool is not None
    show_cfg = MagicMock()
    show_cfg.base_url = None
    show_result = await show_tool.fn(
        uri=f"image://{image_id}/view",
        service=svc,
        config=show_cfg,
    )
    show_text = [c for c in show_result.content if isinstance(c, TextContent)]
    show_meta = json.loads(show_text[0].text)
    # After completion the pending entry is cleaned up and show_image returns
    # the normal image thumbnail (status key absent or not 'generating'/'failed')
    assert show_meta.get("status") not in ("generating", "failed")


async def test_show_image_redirects_to_check_for_in_progress(
    tmp_path: Path,
) -> None:
    """show_image redirects to check_generation_status while task is running."""
    svc = ImageService(scratch_dir=tmp_path)

    # Use a slow provider so we can inspect mid-generation state
    original_provider = PlaceholderImageProvider()
    original_generate = original_provider.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.5)
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    original_provider.generate = slow_generate  # type: ignore[assignment]
    svc.register_provider("placeholder", original_provider)

    mcp = FastMCP("test")
    register_tools(mcp)
    gen_tool = await mcp.get_tool("generate_image")
    show_tool = await mcp.get_tool("show_image")
    assert gen_tool is not None
    assert show_tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await gen_tool.fn(
        prompt="slow generation test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )
    text_items = [c for c in result.content if isinstance(c, TextContent)]
    image_id = json.loads(text_items[0].text)["image_id"]

    # Call show_image immediately — should redirect to check_generation_status
    show_cfg = MagicMock()
    show_cfg.base_url = None
    show_result = await show_tool.fn(
        uri=f"image://{image_id}/view",
        service=svc,
        config=show_cfg,
    )
    show_text = [c for c in show_result.content if isinstance(c, TextContent)]
    show_meta = json.loads(show_text[0].text)
    assert show_meta["status"] == "generating"
    assert show_meta["image_id"] == image_id
    assert "check_generation_status" in show_meta["error"]

    # Wait for background task to finish to avoid warnings
    await asyncio.sleep(0.8)


async def test_check_generation_status_returns_generating(
    tmp_path: Path,
) -> None:
    """check_generation_status returns 'generating' while task is running."""
    svc = ImageService(scratch_dir=tmp_path)

    original_provider = PlaceholderImageProvider()
    original_generate = original_provider.generate

    async def slow_generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.5)
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    original_provider.generate = slow_generate  # type: ignore[assignment]
    svc.register_provider("placeholder", original_provider)

    mcp = FastMCP("test")
    register_tools(mcp)
    gen_tool = await mcp.get_tool("generate_image")
    check_tool = await mcp.get_tool("check_generation_status")
    assert gen_tool is not None
    assert check_tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await gen_tool.fn(
        prompt="status check test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )
    text_items = [c for c in result.content if isinstance(c, TextContent)]
    image_id = json.loads(text_items[0].text)["image_id"]

    # Check immediately — should be generating
    status_json = await check_tool.fn(image_id=image_id, service=svc)
    status = json.loads(status_json)
    assert status["status"] == "generating"
    assert status["image_id"] == image_id
    assert "elapsed_seconds" in status

    # Wait for completion and check again
    await asyncio.sleep(0.8)
    status_json = await check_tool.fn(image_id=image_id, service=svc)
    status = json.loads(status_json)
    assert status["status"] == "completed"


async def test_check_generation_status_returns_completed(
    tmp_path: Path,
) -> None:
    """check_generation_status returns 'completed' for finished images."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    mcp = FastMCP("test")
    register_tools(mcp)
    gen_tool = await mcp.get_tool("generate_image")
    check_tool = await mcp.get_tool("check_generation_status")
    assert gen_tool is not None
    assert check_tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await gen_tool.fn(
        prompt="completed check test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )
    text_items = [c for c in result.content if isinstance(c, TextContent)]
    image_id = json.loads(text_items[0].text)["image_id"]

    # Placeholder is near-instant
    await asyncio.sleep(0.1)
    status_json = await check_tool.fn(image_id=image_id, service=svc)
    status = json.loads(status_json)
    assert status["status"] == "completed"


async def test_check_generation_status_completed_pending_entry(
    tmp_path: Path,
) -> None:
    """check_generation_status returns 'completed' when pending.status == 'completed'."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())

    # Manually register a pending entry and mark it completed
    svc.register_pending(
        image_id="test123",
        prompt="manual test",
        provider="placeholder",
    )
    svc.complete_pending("test123")

    mcp = FastMCP("test")
    register_tools(mcp)
    check_tool = await mcp.get_tool("check_generation_status")
    assert check_tool is not None

    status_json = await check_tool.fn(image_id="test123", service=svc)
    status = json.loads(status_json)
    assert status["status"] == "completed"
    assert status["image_id"] == "test123"

    # Pending entry should be cleaned up
    assert svc.get_pending("test123") is None


async def test_check_generation_status_returns_failed(
    tmp_path: Path,
) -> None:
    """check_generation_status returns 'failed' with error for failed generations."""
    svc = ImageService(scratch_dir=tmp_path)

    from image_generation_mcp.providers.types import ImageContentPolicyError

    async def _always_raise(*_args: object, **_kwargs: object) -> None:
        raise ImageContentPolicyError("placeholder", "blocked")

    svc.register_provider("placeholder", PlaceholderImageProvider())
    svc.generate = _always_raise  # type: ignore[assignment]

    mcp = FastMCP("test")
    register_tools(mcp)
    gen_tool = await mcp.get_tool("generate_image")
    check_tool = await mcp.get_tool("check_generation_status")
    assert gen_tool is not None
    assert check_tool is not None

    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.session.check_client_capability.return_value = False
    cfg = MagicMock()
    cfg.paid_providers = frozenset()

    result = await gen_tool.fn(
        prompt="fail check test",
        provider="placeholder",
        service=svc,
        config=cfg,
        ctx=ctx,
    )
    text_items = [c for c in result.content if isinstance(c, TextContent)]
    image_id = json.loads(text_items[0].text)["image_id"]

    # Let the background task fail
    await asyncio.sleep(0.1)
    status_json = await check_tool.fn(image_id=image_id, service=svc)
    status = json.loads(status_json)
    assert status["status"] == "failed"
    assert "error" in status


async def test_check_generation_status_unknown_id(
    tmp_path: Path,
) -> None:
    """check_generation_status returns 'unknown' for non-existent image_id."""
    svc = ImageService(scratch_dir=tmp_path)

    mcp = FastMCP("test")
    register_tools(mcp)
    check_tool = await mcp.get_tool("check_generation_status")
    assert check_tool is not None

    status_json = await check_tool.fn(image_id="nonexistent", service=svc)
    status = json.loads(status_json)
    assert status["status"] == "unknown"


async def test_image_list_includes_pending_generation(
    tmp_path: Path,
) -> None:
    """image://list includes in-progress generations with 'generating' status."""
    from fastmcp import Client

    from image_generation_mcp._server_deps import make_service_lifespan
    from image_generation_mcp._server_resources import register_resources
    from image_generation_mcp.config import ServerConfig

    config = ServerConfig(scratch_dir=tmp_path, read_only=False)

    # Use an Event to block generation until we've read the pending list.
    # This replaces the previous asyncio.sleep(0.5) approach which was racy
    # on Python 3.14 where the event loop is faster.
    gate = asyncio.Event()
    original_provider = PlaceholderImageProvider()
    original_generate = original_provider.generate

    async def gated_generate(*args: object, **kwargs: object) -> object:
        await gate.wait()
        return await original_generate(*args, **kwargs)  # type: ignore[arg-type]

    original_provider.generate = gated_generate  # type: ignore[assignment]

    mcp = FastMCP("test-list-pending", lifespan=make_service_lifespan(config))
    register_tools(mcp)
    register_resources(mcp)

    async with Client(mcp) as client:
        gen_result = await client.call_tool(
            "generate_image",
            {"prompt": "list pending test", "provider": "placeholder"},
        )
        text = next(c for c in gen_result.content if c.type == "text")
        image_id = json.loads(text.text)["image_id"]

        # Read image://list while generation is guaranteed to be pending
        list_result = await client.read_resource("image://list")
        items = json.loads(list_result[0].text)  # type: ignore[union-attr]
        pending_items = [i for i in items if i.get("status") == "generating"]
        assert len(pending_items) >= 1
        pending_match = [i for i in pending_items if i["image_id"] == image_id]
        assert len(pending_match) == 1
        assert pending_match[0]["provider"] == "placeholder"
        assert pending_match[0]["prompt"] == "list pending test"
        assert "progress" in pending_match[0]
        assert "progress_message" in pending_match[0]

        # Release the gate so the background task can finish
        gate.set()
        await asyncio.sleep(0.3)
