"""Tests for MCP server factory — auth wiring, read-only mode, and tools."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest

from image_generation_mcp.server import (
    _build_remote_auth,
    _resolve_auth_mode,
    make_server,
)

# OIDC vars required by _build_oidc_auth()
_OIDC_REQUIRED = {
    "IMAGE_GENERATION_MCP_BASE_URL": "https://mcp.example.com",
    "IMAGE_GENERATION_MCP_OIDC_CONFIG_URL": "https://auth.example.com/.well-known/openid-configuration",
    "IMAGE_GENERATION_MCP_OIDC_CLIENT_ID": "image-generation-mcp",
    "IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET": "test-secret",
}

# Minimal vars for remote auth mode
_REMOTE_REQUIRED = {
    "IMAGE_GENERATION_MCP_BASE_URL": "https://mcp.example.com",
    "IMAGE_GENERATION_MCP_OIDC_CONFIG_URL": "https://auth.example.com/.well-known/openid-configuration",
}

# Fake OIDC discovery response
_DISCOVERY_RESPONSE = {
    "issuer": "https://auth.example.com",
    "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/token",
}


class TestAuthModeSelection:
    """Tests for make_server() auth mode selection.

    Covers all four modes: multi (both configured), bearer-only,
    OIDC-only, and none.
    """

    def test_no_auth_when_nothing_configured(self) -> None:
        """Default: no auth when no auth env vars are set."""
        server = make_server()
        assert server.auth is None

    def test_bearer_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bearer-only: StaticTokenVerifier when only BEARER_TOKEN is set."""
        from fastmcp.server.auth import StaticTokenVerifier

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        server = make_server()
        assert isinstance(server.auth, StaticTokenVerifier)

    def test_oidc_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDC-only: OIDCProxy when only OIDC vars are set."""
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = make_server()

        assert server.auth is mock_oidc

    def test_multi_auth_when_both_configured(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Multi-auth: MultiAuth when both BEARER_TOKEN and OIDC vars are set."""
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
            server = make_server()

        assert isinstance(server.auth, MultiAuth)
        assert "mode=multi" in caplog.text

    def test_multi_auth_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OIDCProxy must be server= (not in verifiers=) for OAuth routes to mount."""
        from fastmcp.server.auth import MultiAuth, StaticTokenVerifier

        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = make_server()

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
        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls):
            server = make_server()

        from fastmcp.server.auth import MultiAuth

        assert isinstance(server.auth, MultiAuth)
        assert server.auth.required_scopes == []


class TestResolveAuthMode:
    """Tests for _resolve_auth_mode() auto-detection logic."""

    def test_no_vars_returns_none(self) -> None:
        assert _resolve_auth_mode() is None

    def test_explicit_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "remote")
        assert _resolve_auth_mode() == "remote"

    def test_explicit_oidc_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "oidc-proxy")
        assert _resolve_auth_mode() == "oidc-proxy"

    def test_explicit_overrides_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AUTH_MODE=remote takes precedence even when client credentials are set."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "remote")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)
        assert _resolve_auth_mode() == "remote"

    def test_auto_oidc_proxy_with_client_creds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auto-detects oidc-proxy when all four OIDC vars are set."""
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)
        assert _resolve_auth_mode() == "oidc-proxy"

    def test_auto_remote_without_client_creds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auto-detects remote when only BASE_URL + CONFIG_URL are set."""
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)
        assert _resolve_auth_mode() == "remote"

    def test_invalid_auth_mode_warns_and_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unknown AUTH_MODE logs warning and falls back to auto-detection.

        The warning is emitted by ``fastmcp_pvl_core.resolve_auth_mode`` —
        we only assert on the return value to avoid coupling this test to
        core's internal log-key format.
        """
        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "bogus")
        with caplog.at_level(logging.WARNING):
            result = _resolve_auth_mode()
        assert result is None

    def test_config_url_only_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CONFIG_URL alone (no BASE_URL) is not enough for any OIDC mode."""
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_OIDC_CONFIG_URL",
            "https://auth.example.com/.well-known/openid-configuration",
        )
        assert _resolve_auth_mode() is None


class TestBuildRemoteAuth:
    """Tests for _build_remote_auth() — RemoteAuthProvider construction."""

    def test_returns_none_when_vars_missing(self) -> None:
        assert _build_remote_auth() is None

    def test_returns_none_when_base_url_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_OIDC_CONFIG_URL",
            "https://auth.example.com/.well-known/openid-configuration",
        )
        assert _build_remote_auth() is None

    def test_returns_none_when_httpx_missing(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Returns None with install hint when httpx is not importable."""
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        # Setting sys.modules["httpx"] = None causes Python to raise
        # ImportError regardless of prior import state (order-independent).
        with (
            patch.dict("sys.modules", {"httpx": None}),
            caplog.at_level(logging.WARNING),
        ):
            result = _build_remote_auth()

        assert result is None
        assert "httpx" in caplog.text

    def test_returns_remote_auth_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns RemoteAuthProvider when env vars and discovery are valid."""
        from fastmcp.server.auth import RemoteAuthProvider

        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            result = _build_remote_auth()

        assert isinstance(result, RemoteAuthProvider)

    def test_returns_none_on_discovery_failure(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Returns None and logs error when discovery fetch fails."""
        import httpx

        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        with (
            patch("httpx.get", side_effect=httpx.ConnectError("connection refused")),
            caplog.at_level(logging.ERROR),
        ):
            result = _build_remote_auth()

        assert result is None
        assert "discovery_failed" in caplog.text

    def test_returns_none_on_missing_jwks_uri(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Returns None when discovery response lacks jwks_uri."""
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"issuer": "https://auth.example.com"}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("httpx.get", return_value=mock_resp),
            caplog.at_level(logging.ERROR),
        ):
            result = _build_remote_auth()

        assert result is None
        assert "discovery_incomplete" in caplog.text

    def test_passes_audience_and_scopes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Audience and scopes from env vars are passed to JWTVerifier."""
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)
        monkeypatch.setenv("IMAGE_GENERATION_MCP_OIDC_AUDIENCE", "my-audience")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES", "read,write")

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        mock_verifier = MagicMock()
        mock_verifier_cls = MagicMock(return_value=mock_verifier)

        with (
            patch("httpx.get", return_value=mock_resp),
            patch("fastmcp.server.auth.JWTVerifier", mock_verifier_cls),
        ):
            _build_remote_auth()

        mock_verifier_cls.assert_called_once_with(
            jwks_uri="https://auth.example.com/.well-known/jwks.json",
            issuer="https://auth.example.com",
            audience="my-audience",
            required_scopes=["read", "write"],
        )


class TestRemoteAuthIntegration:
    """Integration tests: make_server() with remote auth mode."""

    def test_remote_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Remote mode: RemoteAuthProvider when only BASE_URL + CONFIG_URL are set."""
        from fastmcp.server.auth import RemoteAuthProvider

        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            server = make_server()

        assert isinstance(server.auth, RemoteAuthProvider)

    def test_remote_plus_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Remote + bearer: MultiAuth with RemoteAuthProvider as server."""
        from fastmcp.server.auth import (
            MultiAuth,
            RemoteAuthProvider,
            StaticTokenVerifier,
        )

        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)
        monkeypatch.setenv("IMAGE_GENERATION_MCP_BEARER_TOKEN", "my-secret-token")

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            server = make_server()

        assert isinstance(server.auth, MultiAuth)
        assert isinstance(server.auth.server, RemoteAuthProvider)
        assert len(server.auth.verifiers) == 1
        assert isinstance(server.auth.verifiers[0], StaticTokenVerifier)

    def test_explicit_remote_overrides_auto_oidc_proxy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AUTH_MODE=remote uses RemoteAuthProvider even with client credentials."""
        from fastmcp.server.auth import RemoteAuthProvider

        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "remote")
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            server = make_server()

        assert isinstance(server.auth, RemoteAuthProvider)

    def test_explicit_oidc_proxy_without_client_creds_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AUTH_MODE=oidc-proxy without client creds logs a warning."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_AUTH_MODE", "oidc-proxy")
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        with caplog.at_level(logging.WARNING):
            server = make_server()

        assert server.auth is None
        # Core logs 'No auth configured' when build_auth returns None despite
        # explicit AUTH_MODE; legacy IG message "could not be initialized" is gone.
        assert "No auth configured" in caplog.text

    def test_startup_log_remote(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Remote mode logs 'remote — token validation only'."""
        for var, val in _REMOTE_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_resp = MagicMock()
        mock_resp.json.return_value = _DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("httpx.get", return_value=mock_resp),
            caplog.at_level(logging.INFO),
        ):
            make_server()

        assert "mode=remote" in caplog.text

    def test_startup_log_oidc_proxy(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """OIDCProxy mode logs 'oidc-proxy — DCR emulation'."""
        for var, val in _OIDC_REQUIRED.items():
            monkeypatch.setenv(var, val)

        mock_oidc = MagicMock()
        mock_cls = MagicMock(return_value=mock_oidc)
        with (
            patch("fastmcp.server.auth.oidc_proxy.OIDCProxy", mock_cls),
            caplog.at_level(logging.INFO),
        ):
            make_server()

        assert "mode=oidc-proxy" in caplog.text


class TestVersionLogging:
    """Tests for server version logging at startup."""

    def test_version_logged_on_startup(self, caplog: pytest.LogCaptureFixture) -> None:
        """Server config log line includes version."""
        with caplog.at_level(logging.INFO):
            make_server()
        assert "Server config:" in caplog.text
        assert "version=" in caplog.text

    def test_version_fallback_when_not_installed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Version falls back to 'unknown' when package is not installed."""
        with (
            patch(
                "image_generation_mcp.server._pkg_version",
                side_effect=PackageNotFoundError(),
            ),
            caplog.at_level(logging.INFO),
        ):
            make_server()
        assert "version=unknown" in caplog.text


class TestReadOnlyMode:
    """Tests for read-only vs read-write tool visibility."""

    async def test_read_only_by_default(self) -> None:
        """Server is read-only by default — write tools are hidden."""
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names
        assert "generate_image" not in tool_names

    async def test_read_write_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting READ_ONLY=false makes write tools visible."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names
        assert "generate_image" in tool_names
