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

    async def test_viewer_html_has_image_element(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert '<img id="image"' in text


# -- Tool wiring -------------------------------------------------------------


class TestGenerateImageAppConfig:
    """Verify generate_image tool carries AppConfig metadata."""

    async def test_generate_image_has_app_metadata(self, server) -> None:
        tools = await server.list_tools()
        gen_tool = next(t for t in tools if t.name == "generate_image")
        # AppConfig is serialized into tool.meta under the 'ui' key
        assert gen_tool.meta is not None
        app_data = gen_tool.meta.get("ui")
        assert app_data is not None
        assert app_data["resourceUri"] == "ui://image-viewer/view.html"


# -- Read-only mode ----------------------------------------------------------


class TestViewerInReadOnlyMode:
    """Verify viewer resource is still available in read-only mode."""

    async def test_viewer_resource_available_in_read_only(self) -> None:
        server = create_server()  # read-only by default
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://image-viewer/view.html" in uris
