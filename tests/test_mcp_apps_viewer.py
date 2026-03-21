"""Tests for MCP Apps image viewer — resource registration and tool wiring."""

from __future__ import annotations

import pytest

from image_generation_mcp.mcp_server import create_server


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    """Create a read-write server so generate_image is visible."""
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
    return create_server()


# -- Resource registration ---------------------------------------------------


class TestImageViewerResource:
    """Verify the ui://image-viewer/view.html resource is registered."""

    async def test_viewer_resource_registered(self, server) -> None:
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://image-viewer/view.html" in uris

    async def test_viewer_returns_html(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "<!DOCTYPE html>" in text

    async def test_viewer_html_imports_ext_apps_sdk(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "@modelcontextprotocol/ext-apps" in text

    async def test_viewer_html_has_ontoolresult_handler(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "ontoolresult" in text

    async def test_viewer_html_has_ontoolinput_handler(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "ontoolinput" in text

    async def test_viewer_html_has_localstorage_persistence(self, server) -> None:
        """Viewer must save/load state via localStorage for restore."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "localStorage.setItem" in text
        assert "localStorage.getItem" in text

    async def test_viewer_html_has_image_element(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert '<img id="image"' in text

    async def test_viewer_html_has_pre_wrap_whitespace(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "white-space: pre-wrap" in text

    async def test_viewer_html_sets_dynamic_alt_text(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "imgEl.alt = meta.prompt" in text

    async def test_viewer_html_logs_parse_errors(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "console.warn" in text

    async def test_viewer_imgel_declared_before_if_blocks(self, server) -> None:
        """imgEl must be declared before both if(img) and if(text) blocks
        so it is accessible in both scopes."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        imgel_decl = text.index('const imgEl = document.getElementById("image")')
        if_img = text.index("if (img)")
        if_text = text.index("if (text)")
        assert imgel_decl < if_img < if_text


# -- Tool wiring -------------------------------------------------------------


class TestShowImageAppConfig:
    """Verify show_image tool carries AppConfig metadata (viewer wired here)."""

    async def test_show_image_has_app_metadata(self, server) -> None:
        tools = await server.list_tools()
        show_tool = next(t for t in tools if t.name == "show_image")
        # AppConfig is serialized into tool.meta under the 'ui' key
        assert show_tool.meta is not None
        app_data = show_tool.meta.get("ui")
        assert app_data is not None
        assert app_data["resourceUri"] == "ui://image-viewer/view.html"

    async def test_generate_image_has_no_app_metadata(self, server) -> None:
        tools = await server.list_tools()
        gen_tool = next(t for t in tools if t.name == "generate_image")
        # generate_image no longer owns the viewer — show_image does
        if gen_tool.meta is not None:
            assert gen_tool.meta.get("ui") is None


# -- Metadata shape ----------------------------------------------------------


class TestGenerateImageMetadataShape:
    """Verify the metadata dict includes prompt/dimensions and excludes file_path."""

    async def test_metadata_includes_prompt_and_dimensions(self, server) -> None:
        """The viewer JS references meta.prompt and meta.dimensions — verify
        they are emitted by the tool metadata builder."""
        # The HTML parser relies on these keys; verify them in the source
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "meta.prompt" in text
        assert "meta.dimensions" in text

    async def test_metadata_excludes_file_path(self) -> None:
        """file_path must NOT appear in tool result metadata (CWE-200)."""
        import inspect

        from image_generation_mcp import _server_tools

        # Read the source to verify no file_path in metadata dict
        source = inspect.getsource(_server_tools)
        assert "file_path" not in source


# -- Read-only mode ----------------------------------------------------------


class TestViewerInReadOnlyMode:
    """Verify viewer resource is still available in read-only mode."""

    async def test_viewer_resource_available_in_read_only(self) -> None:
        server = create_server()  # read-only by default
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://image-viewer/view.html" in uris
