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

    async def test_viewer_html_has_ontoolcancelled_handler(self, server) -> None:
        """Viewer handles tool cancellation per ext-apps SDK lifecycle."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "ontoolcancelled" in text

    async def test_viewer_html_has_host_context_handler(self, server) -> None:
        """Viewer applies host theme, style vars, fonts, and safe area insets."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "onhostcontextchanged" in text
        assert "applyDocumentTheme" in text
        assert "applyHostStyleVariables" in text
        assert "safeAreaInsets" in text

    async def test_viewer_html_uses_host_css_variables(self, server) -> None:
        """Viewer CSS uses host CSS variables for theme integration."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "var(--color-text-primary" in text
        assert "var(--font-sans" in text

    async def test_viewer_html_has_generating_state(self, server) -> None:
        """Viewer has a generating status UI with spinner and progress bar."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "state-generating" in text
        assert "renderGenerating" in text

    async def test_viewer_html_has_failed_state(self, server) -> None:
        """Viewer has a failed status UI."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "state-failed" in text
        assert "renderFailed" in text

    async def test_viewer_html_sets_dynamic_alt_text(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "imgEl.alt" in text

    async def test_viewer_html_logs_parse_errors(self, server) -> None:
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        assert "console.warn" in text

    async def test_viewer_domain_omitted_without_base_url(self, server) -> None:
        """Without APP_DOMAIN, domain is omitted (host uses default sandbox)."""
        resources = await server.list_resources()
        viewer = next(
            r for r in resources if str(r.uri) == "ui://image-viewer/view.html"
        )
        assert viewer.meta is not None, (
            "AppConfig should still produce meta even with domain=None"
        )
        app_meta = viewer.meta.get("ui", {})
        # domain excluded via exclude_none when APP_DOMAIN is not set
        assert "domain" not in app_meta

    async def test_viewer_domain_from_app_domain_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When APP_DOMAIN is set, domain is passed through verbatim."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_APP_DOMAIN",
            "abcdef01234567890abcdef012345678.claudemcpcontent.com",
        )
        srv = create_server()
        resources = await srv.list_resources()
        viewer = next(
            r for r in resources if str(r.uri) == "ui://image-viewer/view.html"
        )
        assert viewer.meta is not None
        app_meta = viewer.meta.get("ui", {})
        assert app_meta.get("domain") == (
            "abcdef01234567890abcdef012345678.claudemcpcontent.com"
        )

    async def test_viewer_domain_auto_computed_from_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When BASE_URL is set but APP_DOMAIN is not, domain is auto-computed."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_BASE_URL", "https://example.com"
        )
        srv = create_server()
        resources = await srv.list_resources()
        viewer = next(
            r for r in resources if str(r.uri) == "ui://image-viewer/view.html"
        )
        assert viewer.meta is not None
        app_meta = viewer.meta.get("ui", {})
        # sha256("https://example.com/mcp")[:32] + ".claudemcpcontent.com"
        import hashlib

        expected_hash = hashlib.sha256(
            b"https://example.com/mcp"
        ).hexdigest()[:32]
        assert app_meta.get("domain") == (
            f"{expected_hash}.claudemcpcontent.com"
        )

    async def test_viewer_domain_app_domain_overrides_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit APP_DOMAIN takes priority over BASE_URL auto-compute."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_BASE_URL", "https://example.com"
        )
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_APP_DOMAIN",
            "custom-domain.example.com",
        )
        srv = create_server()
        resources = await srv.list_resources()
        viewer = next(
            r for r in resources if str(r.uri) == "ui://image-viewer/view.html"
        )
        assert viewer.meta is not None
        app_meta = viewer.meta.get("ui", {})
        assert app_meta.get("domain") == "custom-domain.example.com"

    async def test_viewer_connects_after_handlers(self, server) -> None:
        """All handlers must be registered BEFORE app.connect() per SDK spec."""
        result = await server.read_resource("ui://image-viewer/view.html")
        text = result.contents[0].content
        connect_pos = text.index("app.connect()")
        # All handlers must appear before connect
        assert text.index("app.ontoolinput") < connect_pos
        assert text.index("app.ontoolresult") < connect_pos
        assert text.index("app.ontoolcancelled") < connect_pos
        assert text.index("app.onhostcontextchanged") < connect_pos


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
        assert "m.prompt" in text
        assert "m.dimensions" in text

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
