"""Command-line interface for Image Generation MCP."""

from __future__ import annotations

import logging
from typing import Literal

import typer
from fastmcp_pvl_core import (
    build_event_store,
    configure_logging_from_env,
    maybe_start_debugpy,
    normalise_http_path,
)

from image_generation_mcp.config import _ENV_PREFIX, ProjectConfig

app = typer.Typer(
    name="image-generation-mcp",
    help="MCP server for AI image generation via OpenAI, Google GenAI, or Stable Diffusion WebUI",
    no_args_is_help=True,
    add_completion=False,
)

Transport = Literal["stdio", "http", "sse"]


@app.callback()
def _root(
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Enable debug logging."
    ),
) -> None:
    """Root callback — bootstraps logging for every subcommand.

    ``configure_logging_from_env`` sets the root logger *level* and
    configures FastMCP's own logger tree, but does NOT attach a handler
    to the root logger — so ``image_generation_mcp.*`` loggers would have
    no output.  Attach one here.  Kept idempotent via the
    ``if not root.handlers`` guard so repeated calls (e.g. from
    ``make_server()`` on the same process) are safe.
    """
    configure_logging_from_env(verbose=verbose)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    if verbose:
        # httpx/httpcore are noisy at DEBUG; keep them quiet.  Core doesn't
        # own these deps, so the silencing stays domain-local.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


@app.command()
def serve(
    transport: Transport = typer.Option(
        "stdio", help="MCP transport (stdio / http / sse)."
    ),
    host: str = typer.Option("0.0.0.0", help="Bind host (http only)."),
    port: int = typer.Option(8000, help="Bind port (http only)."),
    http_path: str | None = typer.Option(
        None,
        "--http-path",
        "--path",
        help=(f"Mount path (http only, default: ${_ENV_PREFIX}_HTTP_PATH or /mcp)."),
    ),
) -> None:
    """Run the MCP server."""
    import os

    from image_generation_mcp.server import make_server

    # Optional remote-debugger listener — placed in ``serve`` (not the
    # typer root callback) so non-server commands like ``--help``,
    # ``--version``, or future ``dump-config``-style subcommands are
    # never blocked by ``IMAGE_GENERATION_MCP_DEBUG_WAIT=true``.  No-op
    # unless ``IMAGE_GENERATION_MCP_DEBUG_PORT`` is set; ``debugpy`` is only
    # present when the image was built with ``--build-arg DEBUG=true``
    # (a missing import logs a WARNING and continues).  ``_root`` has
    # already attached the StreamHandler by the time ``serve`` runs, so
    # the helper's INFO/WARNING logs route through the configured
    # formatter rather than Python's lastResort.
    maybe_start_debugpy(_ENV_PREFIX)

    config = ProjectConfig.from_env()
    server = make_server(transport=transport, config=config)

    if transport == "http":
        import uvicorn

        path = normalise_http_path(
            http_path or os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH")
        )
        event_store = build_event_store(_ENV_PREFIX, config.server)
        # lifespan="on" is essential: FastMCP's server_lifespan (startup/shutdown
        # hooks, including service init) runs through the ASGI lifespan protocol.
        # timeout_graceful_shutdown=3 lets SIGTERM drain requests within 3s so
        # containers (Docker/k8s) stop cleanly.
        uvicorn.run(
            server.http_app(path=path, event_store=event_store),
            host=host,
            port=port,
            lifespan="on",
            timeout_graceful_shutdown=3,
        )
    else:
        server.run(transport=transport)


def main() -> None:
    """CLI entry point — used by ``[project.scripts]`` in pyproject.toml."""
    app()


if __name__ == "__main__":
    main()
