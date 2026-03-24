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
from typing import TYPE_CHECKING

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)

_SESSION_HEADER = "mcp-session-id"


class _MCPRequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log MCP HTTP requests with session and JSON-RPC context."""

    def __init__(self, app):
        super().__init__(app)
        self._seen_sessions: set[str] = set()

    async def dispatch(self, request: Request, call_next):
        """Log request method, JSON-RPC method, session ID, and status."""
        session_id = request.headers.get(_SESSION_HEADER, "-")
        session_short = session_id[:12] if session_id != "-" else "-"

        # Log User-Agent on first request per session.
        if session_id not in self._seen_sessions:
            self._seen_sessions.add(session_id)
            ua = request.headers.get("user-agent", "-")
            logger.info(
                "MCP new session=%s User-Agent: %s", session_short, ua
            )

        # Extract JSON-RPC method and extra context from POST body.
        rpc_method = "-"
        rpc_extra = ""
        if request.method == "POST":
            try:
                body = await request.body()
                payload = json.loads(body)
                if isinstance(payload, dict):
                    rpc_method = payload.get("method", "-")
                    params = payload.get("params", {})
                    if isinstance(params, dict):
                        rpc_extra = _extract_rpc_context(rpc_method, params)
                elif isinstance(payload, list) and payload:
                    # Batch request — show first method + count
                    rpc_method = (
                        f"{payload[0].get('method', '?')}[+{len(payload) - 1}]"
                    )
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
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


def _extract_rpc_context(method: str, params: dict) -> str:
    """Extract human-readable context from JSON-RPC params.

    Returns a short string to append to the log label, or empty string.
    """
    if method == "initialize":
        ci = params.get("clientInfo", {})
        name = ci.get("name", "?")
        ver = ci.get("version", "?")
        return f"client={name}/{ver}"

    if method == "resources/read":
        uri = params.get("uri", "?")
        return f"uri={uri}"

    if method == "tools/call":
        tool = params.get("name", "?")
        return f"tool={tool}"

    return ""


def mcp_request_logging_middleware() -> list[Middleware]:
    """Return Starlette middleware list for MCP request logging."""
    return [Middleware(_MCPRequestLoggingMiddleware)]
