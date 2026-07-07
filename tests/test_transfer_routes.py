"""Tests for transfer-route wiring (issue #307) — replaces test_artifacts.py.

pvl-core's ``register_transfer_routes`` registers the ``create_download_link`` /
``create_upload_link`` tools and the ``/transfer/{token}`` route, gated on an
HTTP transport with ``base_url`` set (the sink logic itself is covered by
``test_transfer_sink.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import fastmcp_pvl_core
from fastmcp_pvl_core import ServerConfig

from image_generation_mcp.config import ProjectConfig
from image_generation_mcp.server import make_server

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from fastmcp import FastMCP


def _config(
    tmp_path: Path, base_url: str | None, *, read_only: bool = False
) -> ProjectConfig:
    return ProjectConfig(
        server=ServerConfig(base_url=base_url, kv_store_url="memory://"),
        scratch_dir=tmp_path,
        read_only=read_only,
    )


def _has_transfer_route(server: FastMCP) -> bool:
    return any(
        "/transfer/" in getattr(r, "path", "") for r in server._additional_http_routes
    )


async def _has_tool(server: FastMCP, name: str) -> bool:
    try:
        return await server.get_tool(name) is not None
    except Exception:
        return False


async def test_transfer_tools_and_route_on_http_with_base_url(tmp_path: Path) -> None:
    server = make_server(
        transport="http",
        config=_config(tmp_path, base_url="https://mcp.example.com"),
    )
    assert await _has_tool(server, "create_download_link")
    assert await _has_tool(server, "create_upload_link")
    assert _has_transfer_route(server)


async def test_transfer_absent_on_stdio(tmp_path: Path) -> None:
    server = make_server(
        transport="stdio",
        config=_config(tmp_path, base_url="https://mcp.example.com"),
    )
    assert not await _has_tool(server, "create_download_link")
    assert not await _has_tool(server, "create_upload_link")
    assert not _has_transfer_route(server)


async def test_transfer_absent_on_http_without_base_url(tmp_path: Path) -> None:
    server = make_server(transport="http", config=_config(tmp_path, base_url=None))
    assert not await _has_tool(server, "create_download_link")
    assert not _has_transfer_route(server)


async def test_transfer_tools_carry_title_hints_and_icons(tmp_path: Path) -> None:
    """pvl-core registers the transfer tools bare; make_server fills the metadata."""
    server = make_server(
        transport="http",
        config=_config(tmp_path, base_url="https://mcp.example.com"),
    )
    for name, read_only in (
        ("create_download_link", True),
        ("create_upload_link", False),
    ):
        tool = await server.get_tool(name)
        assert tool is not None
        assert tool.annotations is not None
        assert tool.annotations.title  # non-empty human-readable title
        assert tool.annotations.readOnlyHint is read_only
        assert tool.icons


async def test_create_upload_link_hidden_in_read_only(tmp_path: Path) -> None:
    """create_upload_link mutates the gallery, so read-only mode must hide it."""
    server = make_server(
        transport="http",
        config=_config(tmp_path, base_url="https://mcp.example.com", read_only=True),
    )
    assert not await _has_tool(server, "create_upload_link")
    # The read-only download link stays available.
    assert await _has_tool(server, "create_download_link")


def test_upload_cap_coordinated_with_domain_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route upload cap is the smaller of the transfer and domain image caps.

    pvl-core's route 413s past its own ``max_upload_bytes``, but an image over
    the tighter domain ``max_input_image_bytes`` would otherwise pass the route
    and 500 inside ``sink.write`` (``register_imported_image`` raises). Lowering
    the route cap to the domain limit makes the boundary reject with a clean 413.
    """
    captured: dict[str, object] = {}
    real = fastmcp_pvl_core.register_transfer_routes

    def _spy(mcp, server_config, transfer_config, **kwargs):  # type: ignore[no-untyped-def]
        captured["transfer_config"] = transfer_config
        return real(mcp, server_config, transfer_config, **kwargs)

    monkeypatch.setattr(fastmcp_pvl_core, "register_transfer_routes", _spy)

    cfg = _config(tmp_path, base_url="https://mcp.example.com")
    make_server(transport="http", config=cfg)

    transfer_config = captured["transfer_config"]
    assert transfer_config.max_upload_bytes == min(  # type: ignore[attr-defined]
        cfg.transfer.max_upload_bytes, cfg.max_input_image_bytes
    )
    # With defaults the domain cap (20 MiB) is the tighter one.
    assert transfer_config.max_upload_bytes == cfg.max_input_image_bytes  # type: ignore[attr-defined]
