"""CLI tests for Image Generation MCP.

Uses the standard typer ``CliRunner`` pattern: ``--help`` exits via
typer before any command body runs, so these tests don't import
``server.py`` or start uvicorn — keeping them fast and free of side
effects.
"""

from __future__ import annotations

from typer.testing import CliRunner

from image_generation_mcp.cli import app


def test_help_exits_zero() -> None:
    """`image-generation-mcp --help` lists the serve command."""
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.output


def test_serve_help_exits_zero() -> None:
    """`image-generation-mcp serve --help` documents the transport flag."""
    result = CliRunner().invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "stdio" in result.output


def test_no_args_shows_help() -> None:
    """Bare invocation shows help text via ``no_args_is_help=True``.

    Typer/Click exits with code 2 (missing command) but still prints the
    help output.  Pinning the exit code locks in the documented behaviour
    so a future typer version that routes bare invocation to a different
    code (e.g. 1 for runtime error) surfaces as a test failure.
    """
    result = CliRunner().invoke(app, [])
    assert result.exit_code == 2
    assert "serve" in result.output
