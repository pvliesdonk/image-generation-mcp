"""Tests for the MCP Apps image gallery — resource registration and tool wiring."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from PIL import Image as PILImage

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.mcp_server import create_server
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageRecord, ImageService, PendingGeneration

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp.tools import Tool


async def _get_tool(mcp: FastMCP, name: str) -> Tool | None:
    """Get a tool by name, including app-only tools hidden in fastmcp >=3.2."""
    return await super(type(mcp), mcp).get_tool(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 32, height: int = 32) -> bytes:
    """Generate a minimal RGBA PNG in memory."""
    img = PILImage.new("RGBA", (width, height), color=(100, 150, 200, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _add_image(service: ImageService, idx: int) -> ImageRecord:
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

    async def test_gallery_html_has_vendored_sdk(self, server) -> None:
        """SDK must be inlined via import-map, not loaded from CDN."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "importmap" in text
        assert "unpkg.com" not in text

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

    async def test_gallery_html_download_requires_downloadfile(self, server) -> None:
        """Download buttons are only shown when downloadFile capability is present.
        The openLink fallback is intentionally omitted: download_url is never
        returned in gallery tool responses, so the fallback would be dead code.
        """
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "downloadFile" in text
        # openLink fallback removed — download_url not in tool responses
        assert 'dlMode = "openLink"' not in text

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
        # AppConfig must produce a "ui" key (may be empty dict when no
        # domain or CSP is configured, e.g. in test/stdio setups).
        assert "ui" in gallery.meta
        assert isinstance(gallery.meta["ui"], dict)

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

        result = await tool.fn(service=service)

        text_content = next(c for c in result.content if c.type == "text")
        data = json.loads(text_content.text)
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1

    async def test_browse_gallery_returns_thumbnail_for_image(
        self, service: ImageService
    ) -> None:
        """browse_gallery embeds a base64 thumbnail for each completed image."""
        _add_image(service, 0)

        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        result = await tool.fn(service=service)

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

    async def test_browse_gallery_pending_included(self, service: ImageService) -> None:
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

        result = await tool.fn(service=service)

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

        result = await tool.fn(service=service)

        text_contents = [c for c in result.content if c.type == "text"]
        assert len(text_contents) >= 1

        data = json.loads(text_contents[0].text)
        assert "total" in data
        assert "items" in data
        assert "page" in data
        assert "page_size" in data

    async def test_browse_gallery_page_size_is_twelve(
        self, service: ImageService
    ) -> None:
        """browse_gallery returns at most 12 items on the first page."""
        for i in range(15):
            _add_image(service, i)

        mcp = self._mcp()
        tool = await mcp.get_tool("browse_gallery")
        assert tool is not None

        result = await tool.fn(service=service)

        data = json.loads(next(c for c in result.content if c.type == "text").text)
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
        # App-only tools are hidden from list_tools/get_tool in fastmcp >=3.2;
        # use the parent class method to access all registered tools.
        gp = await _get_tool(server, "gallery_page")
        assert gp is not None, "gallery_page must be registered"
        assert gp.meta is not None, "gallery_page must have meta"
        app_meta = gp.meta.get("ui", {})
        visibility = app_meta.get("visibility", [])
        # app-only means "app" is in visibility and "model" is NOT
        assert "app" in visibility
        assert "model" not in visibility

    async def test_gallery_page_returns_all_items_single_page(
        self, service: ImageService
    ) -> None:
        """Page 1 with page_size>=count returns all images."""
        for i in range(3):
            _add_image(service, i)

        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_page")
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
        self, service: ImageService
    ) -> None:
        """Pages must not overlap and together cover all items."""
        for i in range(5):
            _add_image(service, i)

        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_page")
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

    async def test_gallery_page_empty_returns_zero(self, service: ImageService) -> None:
        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=9, service=service)
        data = json.loads(result)
        assert data["total"] == 0
        assert data["items"] == []

    async def test_gallery_page_clamps_page_size(self, service: ImageService) -> None:
        """page_size is clamped to max 24."""
        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_page")
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
        tool = await _get_tool(mcp, "gallery_page")
        assert tool is not None

        result = await tool.fn(page=1, page_size=9, service=service)
        data = json.loads(result)
        assert data["total"] == 1

        item = data["items"][0]
        assert item["status"] == "generating"
        assert "thumbnail_b64" not in item
        assert item["progress"] == 0.3


# ---------------------------------------------------------------------------
# gallery_full_image tool
# ---------------------------------------------------------------------------


class TestGalleryFullImage:
    """gallery_full_image must return base64 image data + metadata."""

    def _mcp(self) -> FastMCP:
        mcp = FastMCP("test")
        register_tools(mcp)
        return mcp

    async def test_gallery_full_image_is_app_only(self, server) -> None:
        """gallery_full_image must carry visibility=["app"] in its app meta."""
        # App-only tools are hidden from list_tools in fastmcp >=3.2;
        # use the parent class method to access all registered tools.
        tool = await _get_tool(server, "gallery_full_image")
        assert tool is not None
        assert tool.meta is not None, "gallery_full_image must have app meta"
        app_meta = tool.meta.get("ui", {})
        visibility = app_meta.get("visibility", [])
        assert "app" in visibility, f"expected 'app' in visibility, got {visibility}"
        assert "model" not in visibility

    async def test_gallery_full_image_returns_base64(
        self, service: ImageService
    ) -> None:
        """gallery_full_image must return valid base64 image bytes."""
        record = _add_image(service, 0)

        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_full_image")
        assert tool is not None

        result = await tool.fn(image_id=record.id, service=service)
        data = json.loads(result)

        assert data["image_id"] == record.id
        assert "b64" in data
        img_bytes = base64.b64decode(data["b64"])
        assert len(img_bytes) > 0

    async def test_gallery_full_image_includes_metadata(
        self, service: ImageService
    ) -> None:
        """gallery_full_image must include prompt, provider, dimensions, created_at."""
        record = _add_image(service, 0)

        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_full_image")
        assert tool is not None

        result = await tool.fn(image_id=record.id, service=service)
        data = json.loads(result)

        assert data["prompt"] == "prompt 0"
        assert data["provider"] == "placeholder"
        assert isinstance(data["dimensions"], list)
        assert len(data["dimensions"]) == 2
        assert "created_at" in data
        assert "content_type" in data

    async def test_gallery_full_image_unknown_id_raises(
        self, service: ImageService
    ) -> None:
        """gallery_full_image must raise for unknown image IDs."""
        mcp = self._mcp()
        tool = await _get_tool(mcp, "gallery_full_image")
        assert tool is not None

        from image_generation_mcp.providers.types import ImageProviderError

        with pytest.raises(ImageProviderError):
            await tool.fn(image_id="nonexistent_id", service=service)


# ---------------------------------------------------------------------------
# Lightbox HTML tests
# ---------------------------------------------------------------------------


class TestLightboxHTML:
    """Gallery HTML must contain the lightbox overlay and JS."""

    async def test_gallery_html_has_lightbox_overlay(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "lb-backdrop" in text
        assert "lb-panel" in text
        assert "lb-img" in text

    async def test_gallery_html_has_lightbox_nav(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "lb-prev" in text
        assert "lb-next" in text
        assert "navigateLb" in text

    async def test_gallery_html_has_close_button(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "lb-close" in text
        assert "closeLightbox" in text

    async def test_gallery_html_has_escape_key_handler(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "Escape" in text

    async def test_gallery_html_has_fullscreen_button(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "lb-fullscreen" in text
        assert "requestDisplayMode" in text
        assert "availableDisplayModes" in text

    async def test_gallery_html_calls_gallery_full_image(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "gallery_full_image" in text
        assert "loadFullImage" in text

    async def test_gallery_html_shows_thumbnail_preview(self, server) -> None:
        """Lightbox must show thumbnail immediately before full-res loads."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "thumbnail_b64" in text
        # The lightbox code should reference thumbnail_b64 for preview
        lb_section = text[text.index("openLightbox") :]
        assert "thumbnail_b64" in lb_section


# ---------------------------------------------------------------------------
# PiP (picture-in-picture) mode HTML tests
# ---------------------------------------------------------------------------


class TestPipModeHTML:
    """Gallery HTML must contain PiP button, CSS, and JS for mode switching."""

    async def test_gallery_html_has_pip_button(self, server) -> None:
        """PiP button element must exist, hidden by default (display:none via JS)."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "pip-btn" in text
        assert 'id="pip-btn"' in text

    async def test_gallery_html_pip_checks_available_display_modes(
        self, server
    ) -> None:
        """handleHostContext must check availableDisplayModes for 'pip'."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert '"pip"' in text
        # Must check availableDisplayModes for pip availability
        assert "availableDisplayModes" in text

    async def test_gallery_html_pip_request_enter(self, server) -> None:
        """PiP button handler must call requestDisplayMode with mode 'pip'."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        # Toggle logic: pipActive ? "inline" : "pip" → feeds into requestDisplayMode
        assert '"pip"' in text
        assert "requestDisplayMode" in text

    async def test_gallery_html_pip_request_exit(self, server) -> None:
        """Exiting PiP must request inline mode."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        # The toggle logic: pipActive ? "inline" : "pip"
        pip_section = text[text.index("pipActive") :]
        assert '"inline"' in pip_section

    async def test_gallery_html_pip_mode_css_class(self, server) -> None:
        """CSS must define .pip-mode with compact layout styles."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert ".pip-mode" in text
        assert "pip-mode" in text

    async def test_gallery_html_pip_hides_pagination(self, server) -> None:
        """PiP mode must hide pagination controls."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        # CSS rule: .main.pip-mode .pagination { display: none; }
        assert ".pip-mode .pagination" in text

    async def test_gallery_html_pip_responds_to_display_mode_changes(
        self, server
    ) -> None:
        """handleHostContext must respond to ctx.displayMode for layout switching."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "displayMode" in text
        assert "applyDisplayMode" in text

    async def test_gallery_html_pip_compact_grid(self, server) -> None:
        """PiP CSS must use a fixed 4-column grid for compact thumbnails."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "repeat(4, 1fr)" in text

    async def test_gallery_html_pip_strip_renderer(self, server) -> None:
        """renderPipStrip must exist to render compact thumbnail strip."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "renderPipStrip" in text

    async def test_gallery_html_disables_auto_resize(self, server) -> None:
        """Gallery must disable autoResize to prevent oversized iframe."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "autoResize: false" in text

    async def test_gallery_html_sends_size_changed(self, server) -> None:
        """Gallery must call sendSizeChanged after render transitions."""
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "sendSizeChanged" in text
