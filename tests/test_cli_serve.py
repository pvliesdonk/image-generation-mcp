"""Project-owned coverage for the typer ``serve`` command body.

The template-owned :mod:`tests.test_cli` carries only the scaffold's
help/exit tests — typer short-circuits on ``--help`` before the command body
runs, so it never exercises ``serve()``'s implementation. This module adds the
project-owned ``serve``-body coverage (both code paths, the verbose branch,
root-logger handler attach, http-path resolution, and ``main``) with
``make_server`` and ``uvicorn`` mocked so nothing binds a socket.

Kept separate from ``test_cli.py`` so the template-owned help/exit tests stay
free of project additions and merge cleanly on a ``copier update``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from image_generation_mcp.cli import app, main


def _invoke_http(
    extra_args: list[str], env: Mapping[str, str] | None = None
) -> tuple[MagicMock, MagicMock]:
    """Invoke ``serve --transport http`` with the server/uvicorn boundary mocked.

    Returns ``(server_mock, uvicorn_run_mock)`` so callers can assert on the
    ``http_app`` and ``uvicorn.run`` call arguments. Raises if the command
    exits non-zero so a broken serve body fails the test rather than silently
    skipping the assertions.
    """
    with (
        patch("image_generation_mcp.server.make_server") as make_server,
        patch("image_generation_mcp.cli.build_event_store"),
        patch("uvicorn.run") as uvicorn_run,
    ):
        server = MagicMock()
        make_server.return_value = server
        result = CliRunner().invoke(
            app, ["serve", "--transport", "http", *extra_args], env=dict(env or {})
        )
    assert result.exit_code == 0, result.output
    return server, uvicorn_run


def test_serve_stdio_runs_server() -> None:
    """`serve --transport stdio` builds the server and calls ``run``."""
    with patch("image_generation_mcp.server.make_server") as make_server:
        server = MagicMock()
        make_server.return_value = server
        result = CliRunner().invoke(app, ["serve", "--transport", "stdio"])

    assert result.exit_code == 0, result.output
    make_server.assert_called_once()
    server.run.assert_called_once_with(transport="stdio")


def test_serve_sse_falls_through_to_server_run() -> None:
    """`serve --transport sse` uses ``server.run`` (not uvicorn)."""
    with (
        patch("image_generation_mcp.server.make_server") as make_server,
        patch("uvicorn.run") as uvicorn_run,
    ):
        server = MagicMock()
        make_server.return_value = server
        result = CliRunner().invoke(app, ["serve", "--transport", "sse"])

    assert result.exit_code == 0, result.output
    server.run.assert_called_once_with(transport="sse")
    uvicorn_run.assert_not_called()


def test_serve_http_starts_uvicorn_with_lifespan() -> None:
    """`serve --transport http` starts uvicorn with host/port and lifespan wiring."""
    server, uvicorn_run = _invoke_http(["--host", "127.0.0.1", "--port", "9123"])

    uvicorn_run.assert_called_once()
    args, kwargs = uvicorn_run.call_args
    # The ASGI app handed to uvicorn must be the http_app we built, not the raw
    # server or a stale object — assert the positional arg, not just the kwargs.
    assert args[0] is server.http_app.return_value
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 9123
    # The lifespan/graceful-shutdown wiring is load-bearing (startup hooks run
    # through the ASGI lifespan; SIGTERM drains within 3s) — assert it explicitly
    # so a regression that drops it fails rather than silently skipping startup.
    assert kwargs["lifespan"] == "on"
    assert kwargs["timeout_graceful_shutdown"] == 3
    server.run.assert_not_called()


def test_serve_http_path_from_flag() -> None:
    """`--http-path` is normalised and forwarded to ``http_app``."""
    server, _ = _invoke_http(["--http-path", "foo"])
    assert server.http_app.call_args.kwargs["path"] == "/foo"


def test_serve_http_path_from_env() -> None:
    """The ``*_HTTP_PATH`` env var is used when no flag is given."""
    server, _ = _invoke_http([], env={"IMAGE_GENERATION_MCP_HTTP_PATH": "custom"})
    assert server.http_app.call_args.kwargs["path"] == "/custom"


def test_serve_http_path_flag_overrides_env() -> None:
    """An explicit ``--http-path`` flag wins over the env var."""
    server, _ = _invoke_http(
        ["--http-path", "flagwins"],
        env={"IMAGE_GENERATION_MCP_HTTP_PATH": "envloses"},
    )
    assert server.http_app.call_args.kwargs["path"] == "/flagwins"


def test_serve_http_path_default() -> None:
    """With neither flag nor env var, the mount path defaults to ``/mcp``."""
    server, _ = _invoke_http([], env={"IMAGE_GENERATION_MCP_HTTP_PATH": ""})
    assert server.http_app.call_args.kwargs["path"] == "/mcp"


def test_verbose_silences_httpx_loggers() -> None:
    """`-v` raises httpx/httpcore loggers to WARNING (verbose branch)."""
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)
    with patch("image_generation_mcp.server.make_server") as make_server:
        make_server.return_value = MagicMock()
        result = CliRunner().invoke(app, ["-v", "serve", "--transport", "stdio"])

    assert result.exit_code == 0, result.output
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_root_callback_attaches_handler_when_none() -> None:
    """The root callback attaches a StreamHandler when the root logger has none."""
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers.clear()
    try:
        with patch("image_generation_mcp.server.make_server") as make_server:
            make_server.return_value = MagicMock()
            result = CliRunner().invoke(app, ["serve", "--transport", "stdio"])
        assert result.exit_code == 0, result.output
        assert root.handlers, "expected a handler to be attached"
    finally:
        root.handlers[:] = saved


def test_main_invokes_app() -> None:
    """``main()`` delegates to the typer ``app``."""
    with patch("image_generation_mcp.cli.app") as app_mock:
        main()
    app_mock.assert_called_once_with()
