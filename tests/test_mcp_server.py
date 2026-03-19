"""Tests for MCP server factory — auth wiring, read-only mode, and tools."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError

import pytest

from image_generation_mcp.mcp_server import create_server

# OIDC vars required by _build_oidc_auth()
_OIDC_REQUIRED = {
    "IMAGE_GENERATION_MCP_BASE_URL": "https://mcp.example.com",
    "IMAGE_GENERATION_MCP_OIDC_CONFIG_URL": "https://auth.example.com/.well-known/openid-configuration",
    "IMAGE_GENERATION_MCP_OIDC_CLIENT_ID": "image-generation-mcp",
    "IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET": "test-secret",
}


class TestAuthModeSelection:
    """Tests for create_server() auth mode selection.

    Covers all four modes: multi (both configured), bearer-only,
    OIDC-only, and none.
    """

    def test_no_auth_when_nothing_configured(self) -> None:
        """Default: no auth when no auth env vars are set."""
        server = create_server()
        assert server.auth is None

    def test_bearer_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bearer-only: StaticTokenVerifier when only BEARER_TOKEN is set."""
        from fastmcp.server.auth import StaticTokenVerifier

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        server = create_server()
        assert isinstance(server.auth, StaticTokenVerifier)

    def test_oidc_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDC-only: OIDCProxy when only OIDC vars are set."""
        from unittest.mock import MagicMock, patch

        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = create_server()

        assert server.auth is mock_oidc

    def test_multi_auth_when_both_configured(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Multi-auth: MultiAuth when both BEARER_TOKEN and OIDC vars are set."""
        from unittest.mock import MagicMock, patch

        from fastmcp.server.auth import MultiAuth

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with (
            patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls),
            caplog.at_level(logging.INFO),
        ):
            server = create_server()

        assert isinstance(server.auth, MultiAuth)
        assert "Multi-auth enabled" in caplog.text

    def test_multi_auth_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDCProxy must be server= (not in verifiers=) for OAuth routes to mount."""
        from unittest.mock import MagicMock, patch

        from fastmcp.server.auth import MultiAuth, StaticTokenVerifier

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = create_server()

        assert isinstance(server.auth, MultiAuth)
        # OIDCProxy is an OAuthProvider — must be server=, not in verifiers=,
        # so that MultiAuth.get_routes() delegates OAuth endpoints to it.
        assert server.auth.server is mock_oidc
        verifiers = server.auth.verifiers
        assert len(verifiers) == 1
        assert isinstance(verifiers[0], StaticTokenVerifier)

    def test_multi_auth_no_required_scopes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MultiAuth must have required_scopes=[] so bearer tokens aren't rejected."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = create_server()

        from fastmcp.server.auth import MultiAuth

        assert isinstance(server.auth, MultiAuth)
        assert server.auth.required_scopes == []


class TestVersionLogging:
    """Tests for server version logging at startup."""

    def test_version_logged_on_startup(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Server config log line includes version."""
        with caplog.at_level(logging.INFO):
            create_server()
        assert "Server config:" in caplog.text
        assert "version=" in caplog.text

    def test_version_fallback_when_not_installed(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Version falls back to 'dev' when package is not installed."""
        from unittest.mock import patch

        with (
            patch(
                "image_generation_mcp.mcp_server.version",
                side_effect=PackageNotFoundError(),
            ),
            caplog.at_level(logging.INFO),
        ):
            create_server()
        assert "version=dev" in caplog.text


class TestReadOnlyMode:
    """Tests for read-only vs read-write tool visibility."""

    async def test_read_only_by_default(self) -> None:
        """Server is read-only by default — write tools are hidden."""
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names
        assert "generate_image" not in tool_names

    async def test_read_write_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting READ_ONLY=false makes write tools visible."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names
        assert "generate_image" in tool_names
