"""Tests for the MCP Apps image gallery — resource registration and tool wiring."""

from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image as PILImage

from fastmcp import FastMCP
from image_generation_mcp._server_resources import register_resources
from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.mcp_server import create_server
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageRecord, ImageService, PendingGeneration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 32, height: int = 32) -> bytes:
    """Generate a minimal RGBA PNG in memory."""
    img = PILImage.new("RGBA", (width, height), color=(100, 150, 200, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _add_image(service: ImageService, tmp_path: Path, idx: int) -> ImageRecord:
    """Register a synthetic unique image in *service* and return its record."""
    from image_generation_mcp.providers.types import ImageResult

    # Use different colour per idx so each image has a unique hash/ID
    png = _make_png_bytes(width=32 + idx, height=32 + idx)
    result = ImageResult(image_data=png, content_type="image/png")
    return service.register_image(
        result,
        "placeholder",
        prompt=f"prompt {idx}",
    )


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    """Server with no read-only restriction."""
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
    return create_server()


# ---------------------------------------------------------------------------
# Resource registration
# ---------------------------------------------------------------------------


class TestGalleryResource:
    """ui://image-gallery/view.html resource must be registered and well-formed."""

    async def test_gallery_resource_registered(self, server) -> None:
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://image-gallery/view.html" in uris

    async def test_gallery_returns_html(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "<!DOCTYPE html>" in text

    async def test_gallery_html_imports_ext_apps_sdk(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "@modelcontextprotocol/ext-apps" in text

    async def test_gallery_html_has_lifecycle_handlers(self, server) -> None:
        """All required ext-apps lifecycle handlers must be present."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "ontoolinput" in text
        assert "ontoolresult" in text
        assert "onhostcontextchanged" in text

    async def test_gallery_html_handlers_before_connect(self, server) -> None:
        """Handlers must be registered before app.connect()."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        last_handler = max(
            text.index("ontoolinput"),
            text.index("ontoolresult"),
            text.index("onhostcontextchanged"),
        )
        assert text.index("app.connect()") > last_handler

    async def test_gallery_html_uses_host_css_variables(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "var(--color-text-primary" in text
        assert "var(--font-sans" in text
        assert "var(--color-background-secondary" in text

    async def test_gallery_html_has_host_context_styling(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "applyDocumentTheme" in text
        assert "applyHostStyleVariables" in text
        assert "safeAreaInsets" in text

    async def test_gallery_html_has_pagination(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "gallery_page" in text
        assert "callServerTool" in text
        assert "page-btn" in text

    async def test_gallery_html_has_download_button(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "card-dl" in text
        assert "app.downloadFile" in text
        assert "resource_link" in text
        assert "getHostCapabilities" in text

    async def test_gallery_html_has_open_link_fallback(self, server) -> None:
        """Download must fall back to openLink when downloadFile is unavailable."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "openLinks" in text
        assert "app.openLink" in text
        assert "openLink" in text

    async def test_gallery_html_has_empty_state(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "state-empty" in text
        assert "No images yet" in text

    async def test_gallery_html_has_pending_spinner(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "card-pending" in text
        assert "spinner" in text

    async def test_gallery_resource_has_app_meta(self, server) -> None:
        resources = await server.list_resources()
        gallery = next(
            r for r in resources if str(r.uri) == "ui://image-gallery/view.html"
        )
        assert gallery.meta is not None
        app_meta = gallery.meta.get("ui", {})
        assert app_meta  # AppConfig must produce non-empty ui meta

    async def test_gallery_domain_omitted_without_base_url(self, server) -> None:
        resources = await server.list_resources()
        gallery = next(
            r for r in resources if str(r.uri) == "ui://image-gallery/view.html"
        )
        assert gallery.meta is not None
        app_meta = gallery.meta.get("ui", {})
        assert "domain" not in app_meta


# ---------------------------------------------------------------------------
# browse_gallery tool
# ---------------------------------------------------------------------------


class TestBrowseGallery:
    """browse_gallery must return correct structure and app wiring."""

    def _mcp(self) -> FastMCP:
        mcp = FastMCP("test")
        register_tools(mcp)
        return mcp

    async def test_browse_gallery_tool_registered(self, server) -> None:
        tools = await server.list_tools()
        names = [t.name for t in tools]
        assert "browse_gallery" in names

    async def test_browse_gallery_has_app_config(self, server) -> None:
        """browse_gallery must reference the gallery resource URI."""
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "browse_gallery")
        assert tool.meta is not None
        app_meta = tool.meta.get("ui", {})
        assert app_meta.get("resourceUri") == "ui://image-gallery/view.html"

    async def test_browse_gallery_is_readonly(self, server) -> None:
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "browse_gallery")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False

    async def test_browse_gallery_empty_returns_zero_total(
        self, service: ImageService
    ) -> None:
        """Empty service returns total=0 and items=[]."""
        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        cfg = MagicMock()
        result = await tool.fn(service=service, config=cfg)

        text_content = next(c for c in result.content if c.type == "text")
        data = json.loads(text_content.text)
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    async def test_browse_gallery_returns_thumbnail_for_image(
        self, service: ImageService, tmp_path: Path
    ) -> None:
        """browse_gallery embeds a base64 thumbnail for each completed image."""
        _add_image(service, tmp_path, 0)

        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        cfg = MagicMock()
        result = await tool.fn(service=service, config=cfg)

        text_content = next(c for c in result.content if c.type == "text")
        data = json.loads(text_content.text)
        assert data["total"] == 1
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["status"] == "completed"
        assert item["prompt"] == "prompt 0"
        assert item["provider"] == "placeholder"
        assert "thumbnail_b64" in item
        # Verify it decodes as valid base64
        thumb_bytes = base64.b64decode(item["thumbnail_b64"])
        assert len(thumb_bytes) > 0

    async def test_browse_gallery_pending_included(
        self, service: ImageService
    ) -> None:
        """In-progress generations appear as pending items (no thumbnail)."""
        pend = PendingGeneration(
            id="pend001",
            prompt="pending image",
            provider="openai",
            status="generating",
            progress=0.5,
            progress_message="Step 5/10",
        )
        service._pending["pend001"] = pend

        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        cfg = MagicMock()
        result = await tool.fn(service=service, config=cfg)

        text_content = next(c for c in result.content if c.type == "text")
        data = json.loads(text_content.text)
        assert data["total"] == 1

        item = data["items"][0]
        assert item["image_id"] == "pend001"
        assert item["status"] == "generating"
        assert item["progress"] == 0.5
        assert "thumbnail_b64" not in item

    async def test_browse_gallery_text_fallback_parseable(
        self, service: ImageService
    ) -> None:
        """Non-UI clients receive valid JSON as the text content."""
        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        cfg = MagicMock()
        result = await tool.fn(service=service, config=cfg)

        text_contents = [c for c in result.content if c.type == "text"]
        assert len(text_contents) >= 1

        data = json.loads(text_contents[0].text)
        assert "total" in data
        assert "items" in data
        assert "page" in data
        assert "page_size" in data

    async def test_browse_gallery_page_size_is_twelve(
        self, service: ImageService, tmp_path: Path
    ) -> None:
        """browse_gallery returns at most 12 items on the first page."""
        for i in range(15):
            _add_image(service, tmp_path, i)

        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        cfg = MagicMock()
        result = await tool.fn(service=service, config=cfg)

        data = json.loads(
            next(c for c in result.content if c.type == "text").text
        )
        assert data["total"] == 15
        assert len(data["items"]) == 12  # page_size cap


# ---------------------------------------------------------------------------
# gallery_page tool
# ---------------------------------------------------------------------------


class TestGalleryPage:
    """gallery_page must paginate correctly and be app-only."""

    def _mcp(self) -> FastMCP:
        mcp = FastMCP("test")
        register_tools(mcp)
        return mcp

    async def test_gallery_page_is_app_only(self, server) -> None:
        """gallery_page must carry visibility=["app"] in its app meta."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None
        # The app meta is attached to the FastMCP tool object
        # Check via server.list_tools() which returns all tools including app-only
        tools = await server.list_tools()
        gp = next((t for t in tools if t.name == "gallery_page"), None)
        if gp is not None and gp.meta:
            app_meta = gp.meta.get("ui", {})
            visibility = app_meta.get("visibility", [])
            # app-only means "model" is NOT in visibility
            assert "model" not in visibility

    async def test_gallery_page_returns_all_items_single_page(
        self, service: ImageService, tmp_path: Path
    ) -> None:
        """Page 1 with page_size>=count returns all images."""
        for i in range(3):
            _add_image(service, tmp_path, i)

        mcp = self._mcp()
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=9, service=service)

        data = json.loads(result)
        assert data["total"] == 3
        assert data["page"] == 1
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["status"] == "completed"
            assert "thumbnail_b64" in item
            base64.b64decode(item["thumbnail_b64"])  # must be valid base64

    async def test_gallery_page_pagination_second_page(
        self, service: ImageService, tmp_path: Path
    ) -> None:
        """Pages must not overlap and together cover all items."""
        for i in range(5):
            _add_image(service, tmp_path, i)

        mcp = self._mcp()
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None

        r1 = await tool.fn(page=1, page_size=3, service=service)
        r2 = await tool.fn(page=2, page_size=3, service=service)

        d1 = json.loads(r1)
        d2 = json.loads(r2)

        assert d1["total"] == 5
        assert d2["total"] == 5
        assert len(d1["items"]) == 3
        assert len(d2["items"]) == 2  # remainder

        ids_p1 = {item["image_id"] for item in d1["items"]}
        ids_p2 = {item["image_id"] for item in d2["items"]}
        assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"
        assert len(ids_p1 | ids_p2) == 5, "Pages together must cover all items"

    async def test_gallery_page_empty_returns_zero(
        self, service: ImageService
    ) -> None:
        mcp = self._mcp()
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=9, service=service)
        data = json.loads(result)
        assert data["total"] == 0
        assert data["items"] == []

    async def test_gallery_page_clamps_page_size(
        self, service: ImageService
    ) -> None:
        """page_size is clamped to max 24."""
        mcp = self._mcp()
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=999, service=service)
        data = json.loads(result)
        assert data["page_size"] <= 24

    async def test_gallery_page_pending_has_no_thumbnail(
        self, service: ImageService
    ) -> None:
        """Pending/generating items are returned without thumbnail data."""
        pend = PendingGeneration(
            id="pend001",
            prompt="in progress",
            provider="openai",
            status="generating",
            progress=0.3,
            progress_message="Processing",
        )
        service._pending["pend001"] = pend

        mcp = self._mcp()
        tool = await mcp.get_tool("gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=9, service=service)
        data = json.loads(result)
        assert data["total"] == 1

        item = data["items"][0]
        assert item["status"] == "generating"
        assert "thumbnail_b64" not in item
        assert item["progress"] == 0.3
