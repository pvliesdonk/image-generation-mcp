"""Command-line interface for image-generation-mcp.

Provides a ``serve`` subcommand.  The entry point is :func:`main`,
registered as ``image-generation-mcp`` in ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from fastmcp.utilities.logging import configure_logging

from image_generation_mcp.config import _ENV_PREFIX

logger = logging.getLogger(__name__)

_PROG = "image-generation-mcp"
_DEFAULT_HTTP_PATH = "/mcp"


def _normalise_http_path(path: str | None) -> str:
    """Normalise an HTTP endpoint path for FastMCP streamable HTTP transport.

    Ensures a leading slash and removes a trailing slash (except for root ``/``).
    Empty values fall back to ``/mcp``.
    """
    if path is None:
        return _DEFAULT_HTTP_PATH
    normalised = path.strip()
    if not normalised:
        return _DEFAULT_HTTP_PATH
    if not normalised.startswith("/"):
        normalised = f"/{normalised}"
    if len(normalised) > 1:
        normalised = normalised.rstrip("/")
    return normalised


def _cmd_serve(args: argparse.Namespace) -> None:
    """Run the MCP server."""
    try:
        from image_generation_mcp.mcp_server import create_server
    except ImportError:
        logger.error(
            "FastMCP is not installed. Install with: pip install image-generation-mcp[mcp]"
        )
        sys.exit(1)

    transport = args.transport
    server = create_server(transport=transport)
    env_http_path = os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
    http_path = _normalise_http_path(args.path or env_http_path)
    if transport != "http" and (
        args.host != "0.0.0.0" or args.port != 8000 or args.path is not None
    ):
        logger.warning("--host, --port and --path are only used with --transport http")
    if transport == "http":
        import uvicorn

        from image_generation_mcp._http_logging import mcp_request_logging_middleware
        from image_generation_mcp.mcp_server import build_event_store

        # EVENT_STORE_URL is intentionally read here rather than in config.py:
        # it is transport-layer configuration specific to HTTP mode and has no
        # meaning for stdio/sse transports, so it does not belong in ServerConfig.
        event_store_url = os.environ.get(f"{_ENV_PREFIX}_EVENT_STORE_URL")
        event_store = build_event_store(event_store_url)

        app = server.http_app(
            path=http_path,
            middleware=mcp_request_logging_middleware(),
            event_store=event_store,
        )
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        server.run(transport=transport)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="FastMCP server — replace this description",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    serve_parser = sub.add_parser("serve", help="run the MCP server")
    serve_parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="MCP transport: stdio (default), sse, or http (streamable-http)",
    )
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="host to bind to for http transport (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port for http transport (default: 8000)",
    )
    serve_parser.add_argument(
        "--path",
        default=None,
        help=(
            f"mount path for http transport (default: ${_ENV_PREFIX}_HTTP_PATH or /mcp)"
        ),
    )

    return parser


_COMMANDS = {
    "serve": _cmd_serve,
}


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # App loggers (image_generation_mcp.*) propagate to root; FastMCP
    # loggers (fastmcp.*) have propagate=False and are configured via
    # FASTMCP_LOG_LEVEL at import time.  -v overrides both to DEBUG.
    level = logging.DEBUG if args.verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)

    if args.verbose:
        configure_logging("DEBUG")
        # httpx is noisy at DEBUG — keep it at WARNING.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

    cmd = _COMMANDS[args.command]
    try:
        cmd(args)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
