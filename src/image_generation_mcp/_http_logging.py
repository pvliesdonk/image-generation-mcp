"""HTTP request logging middleware for MCP streamable HTTP transport.

Logs every incoming request with the session ID header, JSON-RPC method,
and response status.  For POST requests the JSON-RPC ``method`` field is
extracted so logs show ``resources/read`` vs ``tools/call`` instead of
just ``POST /mcp``.

Special handling:
- ``initialize`` requests: logs ``clientInfo`` (name + version).
- ``resources/read`` requests: logs the target ``uri``.
- All requests: logs ``User-Agent`` header on first occurrence per session.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_SESSION_HEADER = "mcp-session-id"
_MAX_SEEN_SESSIONS = 10_000


def _sanitize(value: str) -> str:
    """Replace CR and LF characters to prevent log injection."""
    return value.replace("\r", " ").replace("\n", " ")


class _MCPRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log MCP HTTP requests with session and JSON-RPC context."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Bounded LRU to prevent unbounded memory growth.
        self._seen_sessions: OrderedDict[str, None] = OrderedDict()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Log request method, JSON-RPC method, session ID, and status."""
        session_id = request.headers.get(_SESSION_HEADER, "-")
        session_short = _sanitize(session_id[:12]) if session_id != "-" else "-"

        # Log User-Agent on first request per session.
        if session_id not in self._seen_sessions:
            if len(self._seen_sessions) >= _MAX_SEEN_SESSIONS:
                self._seen_sessions.popitem(last=False)
            self._seen_sessions[session_id] = None
            ua = _sanitize(request.headers.get("user-agent", "-"))
            logger.info("MCP new session=%s User-Agent: %s", session_short, ua)

        # Extract JSON-RPC method and extra context from POST body.
        rpc_method = "-"
        rpc_extra = ""
        if request.method == "POST":
            try:
                body = await request.body()
                # Cache body so downstream handlers can re-read it.
                # Uses Starlette's internal _body attr (checked in .body()).
                request._body = body
                payload = json.loads(body)
                if isinstance(payload, dict):
                    rpc_method = _sanitize(str(payload.get("method", "-")))
                    params = payload.get("params", {})
                    if isinstance(params, dict):
                        rpc_extra = _extract_rpc_context(rpc_method, params)
                elif isinstance(payload, list) and payload:
                    # Batch request — show first method + count
                    first = _sanitize(str(payload[0].get("method", "?")))
                    rpc_method = f"{first}[+{len(payload) - 1}]"
            except (json.JSONDecodeError, UnicodeDecodeError):
                rpc_method = "<parse-error>"

        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        status = response.status_code

        label = f"{request.method} {request.url.path}"
        if rpc_method != "-":
            label = f"{label} ({rpc_method})"
        if rpc_extra:
            label = f"{label} {rpc_extra}"

        if status >= 400:
            logger.warning(
                "MCP %s [session=%s] -> %d (%.0fms)",
                label,
                session_short,
                status,
                elapsed_ms,
            )
        else:
            logger.debug(
                "MCP %s [session=%s] -> %d (%.0fms)",
                label,
                session_short,
                status,
                elapsed_ms,
            )

        return response


def _extract_rpc_context(method: str, params: dict[str, object]) -> str:
    """Extract human-readable context from JSON-RPC params.

    Returns a short string to append to the log label, or empty string.
    """
    if method == "initialize":
        ci = params.get("clientInfo", {})
        if isinstance(ci, dict):
            name = _sanitize(str(ci.get("name", "?")))
            ver = _sanitize(str(ci.get("version", "?")))
        else:
            name, ver = "?", "?"
        return f"client={name}/{ver}"

    if method == "resources/read":
        uri = _sanitize(str(params.get("uri", "?")))
        return f"uri={uri}"

    if method == "tools/call":
        tool = _sanitize(str(params.get("name", "?")))
        return f"tool={tool}"

    return ""


def mcp_request_logging_middleware() -> list[Middleware]:
    """Return Starlette middleware list for MCP request logging."""
    return [Middleware(_MCPRequestLoggingMiddleware)]
