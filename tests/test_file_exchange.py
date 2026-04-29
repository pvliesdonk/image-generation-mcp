"""End-to-end tests for the MCP File Exchange wiring.

The bespoke ``ArtifactStore`` + ``create_download_link`` pair has been
replaced with :func:`fastmcp_pvl_core.register_file_exchange`. These tests
cover the producer round-trip (publish → mint URL → fetch bytes) and the
spec invariant that ``lazy=...`` callables are invoked on every
``create_download_link`` call (not cached on the publish-registry side),
which is what makes the on-the-fly transform pipeline keep working under
the new model.
"""

from __future__ import annotations

import asyncio
import json
import unittest.mock
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from fastmcp_pvl_core import (
    FileExchangeHandle,
    FileRefPreview,
    register_file_exchange,
)
from mcp.types import TextContent

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    """ImageService with a temp scratch directory + placeholder provider."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


def _make_handle(mcp: FastMCP) -> FileExchangeHandle:
    """Wire register_file_exchange in 'http' mode for a unit test."""
    with unittest.mock.patch.dict(
        "os.environ",
        {
            "TEST_BASE_URL": "https://mcp.example.com",
            "TEST_TRANSPORT": "http",
            "TEST_FILE_EXCHANGE_ENABLED": "true",
        },
    ):
        return register_file_exchange(
            mcp,
            namespace="test-image-mcp",
            env_prefix="TEST",
            produces=("image/png", "image/webp"),
            transport="http",
        )


class TestMakeServerWiring:
    """``make_server`` mounts the file-exchange route on http transports.

    Regression test for the bug where ``register_file_exchange(transport="auto")``
    silently disabled file-exchange because the CLI doesn't export the
    ``IMAGE_GENERATION_MCP_TRANSPORT`` env var that ``"auto"`` relies on.
    The server now passes ``transport`` through explicitly.
    """

    async def test_artifacts_route_mounted_on_http_transport(self) -> None:
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.config import ProjectConfig
        from image_generation_mcp.server import make_server

        config = ProjectConfig(server=ServerConfig(base_url="https://mcp.example.com"))
        with unittest.mock.patch.dict(
            "os.environ",
            {
                # register_file_exchange reads BASE_URL straight from env
                # (ServerConfig is read independently for auth/etc).  In
                # production both come from the same env var; in this test
                # we set the env var explicitly.
                "IMAGE_GENERATION_MCP_BASE_URL": "https://mcp.example.com",
                "IMAGE_GENERATION_MCP_FILE_EXCHANGE_ENABLED": "true",
            },
        ):
            mcp = make_server(transport="http", config=config)
        # Route is mounted via FastMCP.custom_route, which appends to
        # _additional_http_routes.
        routes = getattr(mcp, "_additional_http_routes", []) or []
        paths = [getattr(r, "path", "") for r in routes]
        assert any("/artifacts/" in p for p in paths), (
            f"expected /artifacts/{{token}} route on http transport, got {paths!r}"
        )

    async def test_artifacts_route_not_mounted_on_stdio_transport(self) -> None:
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.config import ProjectConfig
        from image_generation_mcp.server import make_server

        config = ProjectConfig(server=ServerConfig(base_url="https://mcp.example.com"))
        mcp = make_server(transport="stdio", config=config)
        routes = getattr(mcp, "_additional_http_routes", []) or []
        paths = [getattr(r, "path", "") for r in routes]
        assert not any("/artifacts/" in p for p in paths), (
            f"expected NO /artifacts route on stdio transport, got {paths!r}"
        )


class TestProducerRoundTrip:
    """publish() → file_ref → create_download_link → URL → fetch bytes."""

    async def test_publish_returns_file_ref_with_origin_id(self) -> None:
        mcp = FastMCP("test")
        handle = _make_handle(mcp)
        file_ref = await handle.publish(
            source=b"hello world",
            origin_id="img-abc",
            mime_type="image/png",
            ext="png",
            preview=FileRefPreview(description="test"),
        )
        assert file_ref.origin_id == "img-abc"
        assert file_ref.mime_type == "image/png"
        assert "http" in file_ref.transfer
        assert file_ref.transfer["http"]["tool"] == "create_download_link"

    async def test_create_download_link_mints_url_for_published(self) -> None:
        mcp = FastMCP("test")
        handle = _make_handle(mcp)
        await handle.publish(
            source=b"the bytes",
            origin_id="img-xyz",
            mime_type="image/png",
            ext="png",
        )
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None
        result = await tool.fn(origin_id="img-xyz", ttl_seconds=60)
        assert "url" in result
        assert result["url"].startswith("https://mcp.example.com/artifacts/")
        assert result["mime_type"] == "image/png"

    async def test_create_download_link_unknown_origin_id_returns_error(
        self,
    ) -> None:
        mcp = FastMCP("test")
        _make_handle(mcp)
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None
        result = await tool.fn(origin_id="never-published")
        assert "error" in result
        assert result["error"] == "transfer_failed"


class TestLazyResolvedPerCall:
    """A ``lazy=...`` callable is invoked on every create_download_link call.

    This is the spec invariant that lets show_image keep on-the-fly
    transforms working under the new model — bytes are computed when a
    download URL is requested, not at publish time.
    """

    async def test_lazy_invoked_once_per_create_download_link_call(self) -> None:
        mcp = FastMCP("test")
        handle = _make_handle(mcp)

        invocations = 0

        def _lazy() -> bytes:
            nonlocal invocations
            invocations += 1
            return b"computed-on-demand"

        await handle.publish(
            lazy=_lazy,
            origin_id="img-lazy",
            mime_type="image/png",
            ext="png",
        )
        # publish() with lazy must NOT invoke the callable.
        assert invocations == 0

        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

        result1 = await tool.fn(origin_id="img-lazy")
        assert "url" in result1
        assert invocations == 1

        result2 = await tool.fn(origin_id="img-lazy")
        assert "url" in result2
        assert invocations == 2


class TestShowImagePublishesViaHandle:
    """show_image's ``file_ref`` derives from the wired file_exchange handle."""

    @pytest.fixture
    def _registered(self, service: ImageService) -> tuple[ImageService, str]:
        result = asyncio.run(
            PlaceholderImageProvider().generate("show test", aspect_ratio="1:1")
        )
        record = service.register_image(result, "placeholder", prompt="show test")
        return service, record.id

    async def test_show_image_origin_id_matches_image_id_for_default_uri(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        service, image_id = _registered
        mcp = FastMCP("test")
        handle = _make_handle(mcp)
        register_tools(mcp, file_exchange=handle)
        tool = await mcp.get_tool("show_image")
        assert tool is not None
        cfg = unittest.mock.MagicMock()
        cfg.server.base_url = "https://mcp.example.com"
        result = await tool.fn(
            uri=f"image://{image_id}/view",
            with_link=True,
            service=service,
            config=cfg,
        )
        text = next(c for c in result.content if isinstance(c, TextContent))
        meta = json.loads(text.text)
        assert meta["file_ref"]["origin_id"] == image_id

    async def test_show_image_origin_id_differs_for_transform_variants(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        """Default and transform-variant URIs publish under DIFFERENT origin_ids
        — no URL-query-string smuggling at the file_exchange layer."""
        service, image_id = _registered
        mcp = FastMCP("test")
        handle = _make_handle(mcp)
        register_tools(mcp, file_exchange=handle)
        tool = await mcp.get_tool("show_image")
        assert tool is not None
        cfg = unittest.mock.MagicMock()
        cfg.server.base_url = "https://mcp.example.com"

        async def _show(uri: str) -> str:
            res = await tool.fn(uri=uri, with_link=True, service=service, config=cfg)
            text = next(c for c in res.content if isinstance(c, TextContent))
            return json.loads(text.text)["file_ref"]["origin_id"]

        default_id = await _show(f"image://{image_id}/view")
        webp_id = await _show(f"image://{image_id}/view?format=webp")
        small_id = await _show(f"image://{image_id}/view?format=webp&width=128")

        assert default_id == image_id
        assert webp_id != default_id
        assert small_id != default_id
        assert webp_id != small_id
