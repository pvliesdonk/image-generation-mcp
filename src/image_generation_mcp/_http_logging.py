"""HTTP request logging middleware for MCP streamable HTTP transport.

Logs every incoming request with the session ID header, JSON-RPC method,
and response status.  For POST requests the JSON-RPC ``method`` field is
extracted so logs show ``resources/read`` vs ``tools/call`` instead of
just ``POST /mcp``.
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

    async def dispatch(self, request: Request, call_next):
        """Log request method, JSON-RPC method, session ID, and status."""
        session_id = request.headers.get(_SESSION_HEADER, "-")
        session_short = session_id[:12] if session_id != "-" else "-"

        # Extract JSON-RPC method from POST body without consuming it.
        rpc_method = "-"
        if request.method == "POST":
            try:
                body = await request.body()
                payload = json.loads(body)
                if isinstance(payload, dict):
                    rpc_method = payload.get("method", "-")
                elif isinstance(payload, list) and payload:
                    # Batch request — show first method + count
                    rpc_method = f"{payload[0].get('method', '?')}[+{len(payload) - 1}]"
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                rpc_method = "<parse-error>"

        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        status = response.status_code

        label = f"{request.method} {request.url.path}"
        if rpc_method != "-":
            label = f"{label} ({rpc_method})"

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


def mcp_request_logging_middleware() -> list[Middleware]:
    """Return Starlette middleware list for MCP request logging."""
    return [Middleware(_MCPRequestLoggingMiddleware)]
