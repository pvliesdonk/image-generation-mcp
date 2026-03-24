"""Tests for CLI argument parsing and serve command.

Covers:
- _normalise_http_path edge cases
- _build_parser: serve subcommand, transport choices, defaults
- main: verbose flag, log level configuration, ValueError handling
- _cmd_serve: ImportError on missing FastMCP, http vs stdio transport dispatch
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from image_generation_mcp.cli import (
    _build_parser,
    _cmd_serve,
    _normalise_http_path,
    main,
)

# ---------------------------------------------------------------------------
# _normalise_http_path
# ---------------------------------------------------------------------------


class TestNormaliseHttpPath:
    """Tests for _normalise_http_path edge cases."""

    def test_none_returns_default(self) -> None:
        assert _normalise_http_path(None) == "/mcp"

    def test_empty_string_returns_default(self) -> None:
        assert _normalise_http_path("") == "/mcp"

    def test_whitespace_only_returns_default(self) -> None:
        assert _normalise_http_path("   ") == "/mcp"

    def test_adds_leading_slash(self) -> None:
        assert _normalise_http_path("api") == "/api"

    def test_removes_trailing_slash(self) -> None:
        assert _normalise_http_path("/api/") == "/api"

    def test_root_slash_preserved(self) -> None:
        assert _normalise_http_path("/") == "/"

    def test_already_normalised(self) -> None:
        assert _normalise_http_path("/mcp") == "/mcp"

    def test_no_leading_slash_and_trailing(self) -> None:
        assert _normalise_http_path("mcp/") == "/mcp"


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for argument parser construction."""

    def test_serve_subcommand_exists(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.command == "serve"

    def test_serve_default_transport_stdio(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.transport == "stdio"

    def test_serve_transport_sse(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve", "--transport", "sse"])
        assert args.transport == "sse"

    def test_serve_transport_http(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve", "--transport", "http"])
        assert args.transport == "http"

    def test_serve_invalid_transport_raises(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["serve", "--transport", "invalid"])

    def test_serve_default_host(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.host == "0.0.0.0"

    def test_serve_default_port(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.port == 8000

    def test_serve_default_path_none(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.path is None

    def test_serve_custom_host_port_path(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "serve",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
                "--path",
                "/custom",
            ]
        )
        assert args.host == "127.0.0.1"
        assert args.port == 9000
        assert args.path == "/custom"

    def test_verbose_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--verbose", "serve"])
        assert args.verbose is True

    def test_no_verbose_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["serve"])
        assert args.verbose is False

    def test_missing_subcommand_raises(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ---------------------------------------------------------------------------
# _cmd_serve
# ---------------------------------------------------------------------------


class TestCmdServe:
    """Tests for the serve command handler."""

    def test_cmd_serve_stdio_transport(self) -> None:
        """serve with stdio transport calls server.run(transport='stdio')."""
        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with patch("image_generation_mcp.mcp_server.create_server", mock_create):
            args = argparse.Namespace(
                transport="stdio",
                host="0.0.0.0",
                port=8000,
                path=None,
            )
            _cmd_serve(args)

        mock_server.run.assert_called_once_with(transport="stdio")

    def test_cmd_serve_http_transport(self) -> None:
        """serve with http transport calls server.run with host/port/path."""
        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with patch("image_generation_mcp.mcp_server.create_server", mock_create):
            args = argparse.Namespace(
                transport="http",
                host="0.0.0.0",
                port=8000,
                path=None,
            )
            _cmd_serve(args)

        mock_server.run.assert_called_once()
        call_kwargs = mock_server.run.call_args.kwargs
        assert call_kwargs["transport"] == "http"
        assert call_kwargs["host"] == "0.0.0.0"
        assert call_kwargs["port"] == 8000
        assert call_kwargs["path"] == "/mcp"
        assert "middleware" in call_kwargs

    def test_cmd_serve_http_custom_path(self) -> None:
        """serve with http and custom path uses normalised path."""
        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with patch("image_generation_mcp.mcp_server.create_server", mock_create):
            args = argparse.Namespace(
                transport="http",
                host="localhost",
                port=9000,
                path="custom",
            )
            _cmd_serve(args)

        mock_server.run.assert_called_once()
        call_kwargs = mock_server.run.call_args.kwargs
        assert call_kwargs["transport"] == "http"
        assert call_kwargs["host"] == "localhost"
        assert call_kwargs["port"] == 9000
        assert call_kwargs["path"] == "/custom"
        assert "middleware" in call_kwargs

    def test_cmd_serve_http_path_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """serve with http uses IMAGE_GENERATION_MCP_HTTP_PATH env when path arg is None."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_HTTP_PATH", "/from-env")
        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with patch("image_generation_mcp.mcp_server.create_server", mock_create):
            args = argparse.Namespace(
                transport="http",
                host="0.0.0.0",
                port=8000,
                path=None,
            )
            _cmd_serve(args)

        mock_server.run.assert_called_once()
        call_kwargs = mock_server.run.call_args.kwargs
        assert call_kwargs["transport"] == "http"
        assert call_kwargs["path"] == "/from-env"
        assert "middleware" in call_kwargs

    def test_cmd_serve_stdio_warns_for_http_args(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-http transport logs a warning when http-only args are set."""
        import logging

        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with (
            patch("image_generation_mcp.mcp_server.create_server", mock_create),
            caplog.at_level(logging.WARNING, logger="image_generation_mcp.cli"),
        ):
            args = argparse.Namespace(
                transport="stdio",
                host="127.0.0.1",  # non-default host triggers warning
                port=8000,
                path=None,
            )
            _cmd_serve(args)

        assert "--host, --port and --path" in caplog.text

    def test_cmd_serve_import_error_exits(self) -> None:
        """ImportError from create_server triggers sys.exit(1)."""
        import sys

        with (
            patch.dict(sys.modules, {"image_generation_mcp.mcp_server": None}),
            pytest.raises(SystemExit) as exc_info,
        ):
            args = argparse.Namespace(
                transport="stdio",
                host="0.0.0.0",
                port=8000,
                path=None,
            )
            _cmd_serve(args)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() entry point."""

    def test_main_serve_verbose(self) -> None:
        """main with --verbose sets DEBUG log level and calls configure_logging."""
        mock_server = MagicMock()
        mock_create = MagicMock(return_value=mock_server)

        with (
            patch("image_generation_mcp.mcp_server.create_server", mock_create),
            patch("sys.argv", ["image-generation-mcp", "--verbose", "serve"]),
            patch("image_generation_mcp.cli.configure_logging") as mock_cfg_log,
        ):
            main()

        mock_cfg_log.assert_called_once_with("DEBUG")
        mock_server.run.assert_called_once()

    def test_main_no_verbose_info_level(self) -> None:
        """main without --verbose sets INFO log level."""
        import logging

        root = logging.getLogger()
        original_level = root.level
        try:
            mock_server = MagicMock()
            mock_create = MagicMock(return_value=mock_server)
            with (
                patch("image_generation_mcp.mcp_server.create_server", mock_create),
                patch("sys.argv", ["image-generation-mcp", "serve"]),
            ):
                main()
            assert root.level == logging.INFO
        finally:
            root.setLevel(original_level)

    def test_main_value_error_exits(self) -> None:
        """main calls sys.exit(1) when command raises ValueError."""
        mock_server = MagicMock()
        mock_server.run.side_effect = ValueError("bad value")
        mock_create = MagicMock(return_value=mock_server)

        with (
            patch("image_generation_mcp.mcp_server.create_server", mock_create),
            patch("sys.argv", ["image-generation-mcp", "serve"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_no_args_exits(self) -> None:
        """main with no subcommand exits with non-zero code."""
        with (
            patch("sys.argv", ["image-generation-mcp"]),
            pytest.raises(SystemExit),
        ):
            main()
