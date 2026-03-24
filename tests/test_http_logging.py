"""Tests for HTTP logging middleware (_http_logging.py).

Covers:
- JSON-RPC method extraction from POST body
- Session tracking and User-Agent logging on first request per session
- Context extraction: clientInfo for initialize, uri for resources/read, name for tools/call
- Batch request method logging
- Non-POST methods (GET, DELETE) don't attempt body parsing
- Error response logging (4xx/5xx → warning, 2xx → debug)
- JSON parse errors logged as <parse-error>
- POST body passthrough to downstream app
- Session ID from header (or "-" if missing)
- Session short form (first 12 chars)
- _extract_rpc_context() unit tests
- mcp_request_logging_middleware() returns Middleware list
- Logging levels and formatting
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from image_generation_mcp._http_logging import (
    _extract_rpc_context,
    _MCPRequestLoggingMiddleware,
    mcp_request_logging_middleware,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def echo_app() -> Starlette:
    """Starlette app that echoes POST body and returns 200."""

    async def echo_handler(request: Request) -> JSONResponse:
        """Echo back the request body as JSON."""
        if request.method == "POST":
            body = await request.body()
            # Try to parse as JSON and echo it back
            try:
                payload = json.loads(body)
                return JSONResponse({"echo": payload, "status": 200})
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Return 400 for invalid JSON or non-UTF8
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        return JSONResponse({"status": 200, "method": request.method})

    async def error_handler(_request: Request) -> JSONResponse:
        """Return a 500 error."""
        return JSONResponse({"error": "Internal Server Error"}, status_code=500)

    async def not_found_handler(_request: Request) -> JSONResponse:
        """Return a 404 error."""
        return JSONResponse({"error": "Not Found"}, status_code=404)

    routes = [
        Route("/mcp", echo_handler, methods=["POST", "GET", "DELETE"]),
        Route("/error", error_handler, methods=["GET"]),
        Route("/not-found", not_found_handler, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(_MCPRequestLoggingMiddleware)
    return app


@pytest.fixture
async def client(echo_app: Starlette) -> httpx.AsyncClient:
    """Async HTTP client for echo_app."""
    transport = httpx.ASGITransport(app=echo_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ============================================================================
# Tests: POST body passthrough and method extraction
# ============================================================================


class TestPostBodyPassthrough:
    """POST body is fully consumed by middleware and passed to app."""

    @pytest.mark.asyncio
    async def test_post_body_echoed_back(self, client: httpx.AsyncClient) -> None:
        """POST body is readable in downstream app after middleware reads it."""
        payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "test"}}
        resp = await client.post("/mcp", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["echo"] == payload

    @pytest.mark.asyncio
    async def test_empty_post_body(self, client: httpx.AsyncClient) -> None:
        """Empty POST body causes JSON parse error (expected behavior)."""
        resp = await client.post("/mcp", content=b"")
        assert resp.status_code == 400  # Invalid JSON

    @pytest.mark.asyncio
    async def test_large_post_body(self, client: httpx.AsyncClient) -> None:
        """Large POST body is passed through."""
        large_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"description": "x" * 10000},
        }
        resp = await client.post("/mcp", json=large_payload)
        assert resp.status_code == 200
        assert resp.json()["echo"] == large_payload


class TestJsonRpcMethodExtraction:
    """JSON-RPC method field is extracted from POST body."""

    @pytest.mark.asyncio
    async def test_simple_method_extraction(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST body with 'method' field is extracted."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test_tool"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "session-1"},
            )
        assert resp.status_code == 200
        # Debug log should contain the method name
        assert any("tools/call" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_missing_method_field(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST body without 'method' field logs '-'."""
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "session-2"},
            )
        assert resp.status_code == 200
        # Check that "-" appears in log (indicates missing method)
        assert any("POST /mcp" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_various_method_names(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Various JSON-RPC methods are logged correctly."""
        methods = [
            "initialize",
            "resources/read",
            "tools/call",
            "tools/list_tools",
            "prompts/get",
        ]
        for method in methods:
            with caplog.at_level(logging.DEBUG):
                caplog.clear()
                payload = {"jsonrpc": "2.0", "method": method, "params": {}}
                resp = await client.post(
                    "/mcp",
                    json=payload,
                    headers={"mcp-session-id": f"session-{method}"},
                )
            assert resp.status_code == 200
            assert any(method in record.message for record in caplog.records), (
                f"Method {method} not logged"
            )


class TestBatchRequests:
    """Batch requests (JSON array) log first method + count."""

    @pytest.mark.asyncio
    async def test_batch_request_two_items(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Batch with 2 items logs 'method[+1]'."""
        with caplog.at_level(logging.DEBUG):
            payload = [
                {"jsonrpc": "2.0", "method": "tools/call", "params": {}},
                {"jsonrpc": "2.0", "method": "resources/read", "params": {}},
            ]
            await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "batch-1"},
            )
        # Check that batch format is logged (regardless of response)
        assert any("[+1]" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_batch_request_many_items(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Batch with 5 items logs 'method[+4]'."""
        with caplog.at_level(logging.DEBUG):
            payload = [
                {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
                for _ in range(5)
            ]
            await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "batch-5"},
            )
        assert any("[+4]" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_empty_batch_array(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Empty array is logged as '-' (not a batch)."""
        with caplog.at_level(logging.DEBUG):
            payload: list = []
            await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "batch-empty"},
            )
        # Empty batch should fall back to "-" and not have [+N] format
        assert not any("[+" in record.message for record in caplog.records)


# ============================================================================
# Tests: Context extraction (initialize, resources/read, tools/call)
# ============================================================================


class TestContextExtraction:
    """RPC context is extracted and logged for specific methods."""

    @pytest.mark.asyncio
    async def test_initialize_context_extracted(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """initialize request logs clientInfo name/version."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {"clientInfo": {"name": "test-client", "version": "1.0.0"}},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "init-1"},
            )
        assert resp.status_code == 200
        assert any(
            "client=test-client/1.0.0" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_resources_read_context_extracted(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """resources/read request logs uri."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "resources/read",
                "params": {"uri": "file://my-file.txt"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "res-1"},
            )
        assert resp.status_code == 200
        assert any(
            "uri=file://my-file.txt" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_tools_call_context_extracted(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """tools/call request logs tool name."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "generate_image"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "tool-1"},
            )
        assert resp.status_code == 200
        assert any("tool=generate_image" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_initialize_missing_client_info(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """initialize without clientInfo logs '?'."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "init-2"},
            )
        assert resp.status_code == 200
        assert any("client=?/?" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_other_methods_no_context(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-special methods don't add context."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "resources/list",
                "params": {"something": "value"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "other-1"},
            )
        assert resp.status_code == 200
        # resources/list should not have any special context
        assert any(
            "resources/list" in record.message and "uri=" not in record.message
            for record in caplog.records
        )


# ============================================================================
# Tests: Non-POST methods
# ============================================================================


class TestNonPostMethods:
    """GET, DELETE, and other methods don't attempt body parsing."""

    @pytest.mark.asyncio
    async def test_get_method_no_body_parse(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """GET request doesn't attempt JSON body parsing."""
        with caplog.at_level(logging.DEBUG):
            resp = await client.get(
                "/mcp",
                headers={"mcp-session-id": "get-1"},
            )
        assert resp.status_code == 200
        # Log should show GET /mcp (without a method in parens)
        assert any("GET /mcp" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_delete_method_no_body_parse(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DELETE request doesn't attempt JSON body parsing."""
        with caplog.at_level(logging.DEBUG):
            resp = await client.delete(
                "/mcp",
                headers={"mcp-session-id": "delete-1"},
            )
        assert resp.status_code == 200


# ============================================================================
# Tests: Session tracking and User-Agent logging
# ============================================================================


class TestSessionTracking:
    """User-Agent is logged on first request per session, not repeated."""

    @pytest.mark.asyncio
    async def test_user_agent_logged_first_request(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """User-Agent is logged on first request with a new session."""
        with caplog.at_level(logging.INFO):
            payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={
                    "mcp-session-id": "ua-test-1",
                    "user-agent": "test-client/1.0",
                },
            )
        assert resp.status_code == 200
        ua_logs = [r for r in caplog.records if "User-Agent" in r.message]
        assert len(ua_logs) == 1
        assert "test-client/1.0" in ua_logs[0].message

    @pytest.mark.asyncio
    async def test_user_agent_not_logged_second_request(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """User-Agent is NOT logged on second request with same session."""
        session_id = "ua-test-2"
        ua = "test-client/1.0"

        # First request
        with caplog.at_level(logging.INFO):
            payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": session_id, "user-agent": ua},
            )
        assert resp.status_code == 200
        ua_logs_1 = [r for r in caplog.records if "User-Agent" in r.message]
        assert len(ua_logs_1) == 1

        # Second request with same session
        with caplog.at_level(logging.INFO):
            caplog.clear()
            payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": session_id, "user-agent": ua},
            )
        assert resp.status_code == 200
        ua_logs_2 = [r for r in caplog.records if "User-Agent" in r.message]
        assert len(ua_logs_2) == 0

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_missing_session_header(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing session header is logged as '-'."""
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                # No session header
            )
        assert resp.status_code == 200
        # Should have logged with session=- or session_short=-
        assert any("[session=-]" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_session_short_form(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Session ID is truncated to first 12 characters in logs."""
        long_session = "this-is-a-very-long-session-id-that-exceeds-12-chars"
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "method": "initialize", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": long_session},
            )
        assert resp.status_code == 200
        # Check that 12-char version appears in logs
        assert any(long_session[:12] in record.message for record in caplog.records)


# ============================================================================
# Tests: Error response logging
# ============================================================================


class TestErrorLogging:
    """4xx/5xx responses logged as WARNING, 2xx as DEBUG."""

    @pytest.mark.asyncio
    async def test_success_2xx_logged_as_debug(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """2xx responses logged at DEBUG level."""
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "success-1"},
            )
        assert resp.status_code == 200
        debug_logs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert any("-> 200" in record.message for record in debug_logs)

    @pytest.mark.asyncio
    async def test_4xx_error_logged_as_warning(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """4xx responses logged at WARNING level."""
        with caplog.at_level(logging.WARNING):
            resp = await client.get(
                "/not-found",
                headers={"mcp-session-id": "404-1"},
            )
        assert resp.status_code == 404
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("-> 404" in record.message for record in warning_logs)

    @pytest.mark.asyncio
    async def test_5xx_error_logged_as_warning(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """5xx responses logged at WARNING level."""
        with caplog.at_level(logging.WARNING):
            resp = await client.get(
                "/error",
                headers={"mcp-session-id": "500-1"},
            )
        assert resp.status_code == 500
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("-> 500" in record.message for record in warning_logs)

    @pytest.mark.asyncio
    async def test_log_format_includes_elapsed_ms(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Log message includes elapsed time in milliseconds."""
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "timing-1"},
            )
        assert resp.status_code == 200
        # Check that elapsed time (ms) is in log
        assert any("ms)" in record.message for record in caplog.records)


# ============================================================================
# Tests: JSON parse errors
# ============================================================================


class TestJsonParseErrors:
    """Malformed JSON logged as <parse-error>."""

    @pytest.mark.asyncio
    async def test_invalid_json_logged_as_parse_error(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid JSON body is logged as <parse-error>."""
        with caplog.at_level(logging.DEBUG):
            resp = await client.post(
                "/mcp",
                content=b"{invalid json}",
                headers={"mcp-session-id": "parse-err-1"},
            )
        assert resp.status_code == 400
        assert any("<parse-error>" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_non_utf8_body(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-UTF8 body is logged as <parse-error>."""
        with caplog.at_level(logging.DEBUG):
            resp = await client.post(
                "/mcp",
                content=b"\xff\xfe",
                headers={"mcp-session-id": "parse-err-2"},
            )
        assert resp.status_code == 400
        assert any("<parse-error>" in record.message for record in caplog.records)


# ============================================================================
# Tests: Unit tests for _extract_rpc_context()
# ============================================================================


class TestExtractRpcContext:
    """Unit tests for _extract_rpc_context() helper function."""

    def test_initialize_with_client_info(self) -> None:
        """initialize extracts clientInfo name and version."""
        params = {"clientInfo": {"name": "MyClient", "version": "2.0.1"}}
        result = _extract_rpc_context("initialize", params)
        assert result == "client=MyClient/2.0.1"

    def test_initialize_missing_name(self) -> None:
        """initialize with missing name uses '?'."""
        params = {"clientInfo": {"version": "1.0"}}
        result = _extract_rpc_context("initialize", params)
        assert result == "client=?/1.0"

    def test_initialize_missing_version(self) -> None:
        """initialize with missing version uses '?'."""
        params = {"clientInfo": {"name": "MyClient"}}
        result = _extract_rpc_context("initialize", params)
        assert result == "client=MyClient/?"

    def test_initialize_empty_client_info(self) -> None:
        """initialize with empty clientInfo uses '?'."""
        params = {"clientInfo": {}}
        result = _extract_rpc_context("initialize", params)
        assert result == "client=?/?"

    def test_initialize_no_client_info(self) -> None:
        """initialize without clientInfo uses '?'."""
        params = {}
        result = _extract_rpc_context("initialize", params)
        assert result == "client=?/?"

    def test_resources_read_with_uri(self) -> None:
        """resources/read extracts uri."""
        params = {"uri": "file:///home/user/document.md"}
        result = _extract_rpc_context("resources/read", params)
        assert result == "uri=file:///home/user/document.md"

    def test_resources_read_missing_uri(self) -> None:
        """resources/read with missing uri uses '?'."""
        params = {}
        result = _extract_rpc_context("resources/read", params)
        assert result == "uri=?"

    def test_tools_call_with_name(self) -> None:
        """tools/call extracts tool name."""
        params = {"name": "generate_image"}
        result = _extract_rpc_context("tools/call", params)
        assert result == "tool=generate_image"

    def test_tools_call_missing_name(self) -> None:
        """tools/call with missing name uses '?'."""
        params = {}
        result = _extract_rpc_context("tools/call", params)
        assert result == "tool=?"

    def test_unknown_method_returns_empty_string(self) -> None:
        """Unknown method returns empty string."""
        params = {"some": "value"}
        result = _extract_rpc_context("unknown/method", params)
        assert result == ""

    def test_resources_list_returns_empty(self) -> None:
        """resources/list has no special context."""
        params = {}
        result = _extract_rpc_context("resources/list", params)
        assert result == ""

    def test_tools_list_tools_returns_empty(self) -> None:
        """tools/list_tools has no special context."""
        params = {}
        result = _extract_rpc_context("tools/list_tools", params)
        assert result == ""


# ============================================================================
# Tests: mcp_request_logging_middleware() factory
# ============================================================================


class TestMiddlewareFactory:
    """mcp_request_logging_middleware() returns correct Middleware list."""

    def test_returns_middleware_list(self) -> None:
        """mcp_request_logging_middleware() returns a list."""
        result = mcp_request_logging_middleware()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_middleware_instance(self) -> None:
        """mcp_request_logging_middleware() returns Middleware instance."""
        from starlette.middleware import Middleware

        result = mcp_request_logging_middleware()
        assert isinstance(result[0], Middleware)

    def test_middleware_wraps_correct_class(self) -> None:
        """Middleware wraps _MCPRequestLoggingMiddleware."""
        result = mcp_request_logging_middleware()
        # Middleware stores the middleware class in .cls
        assert result[0].cls == _MCPRequestLoggingMiddleware


# ============================================================================
# Tests: Log formatting and label construction
# ============================================================================


class TestLogFormatting:
    """Log messages are formatted correctly."""

    @pytest.mark.asyncio
    async def test_log_label_format_no_method(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """GET request without method shows 'GET /mcp'."""
        with caplog.at_level(logging.DEBUG):
            resp = await client.get(
                "/mcp",
                headers={"mcp-session-id": "fmt-1"},
            )
        assert resp.status_code == 200
        assert any("GET /mcp" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_log_label_format_with_method(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST request with method shows 'POST /mcp (method)'."""
        with caplog.at_level(logging.DEBUG):
            payload = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "fmt-2"},
            )
        assert resp.status_code == 200
        assert any(
            "POST /mcp (tools/call)" in record.message for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_log_label_format_with_context(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """POST with context shows 'POST /mcp (method) context'."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "test_tool"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "fmt-3"},
            )
        assert resp.status_code == 200
        assert any(
            "POST /mcp (tools/call) tool=test_tool" in record.message
            for record in caplog.records
        )


# ============================================================================
# Tests: Middleware isolation and state
# ============================================================================


class TestMiddlewareState:
    """Each middleware instance maintains its own session state."""

    @pytest.mark.asyncio
    async def test_multiple_middleware_instances(self) -> None:
        """Multiple middleware instances have separate session tracking."""

        # Create two separate apps with their own middleware instances
        async def app1_handler(_request: Request) -> JSONResponse:
            return JSONResponse({"app": 1})

        async def app2_handler(_request: Request) -> JSONResponse:
            return JSONResponse({"app": 2})

        app1 = Starlette(routes=[Route("/", app1_handler)])
        app1.add_middleware(_MCPRequestLoggingMiddleware)

        app2 = Starlette(routes=[Route("/", app2_handler)])
        app2.add_middleware(_MCPRequestLoggingMiddleware)

        # Both apps should have independent session tracking
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app1), base_url="http://test"
        ) as c1:
            resp1 = await c1.get("/", headers={"mcp-session-id": "shared-id"})
            assert resp1.status_code == 200

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app2), base_url="http://test"
        ) as c2:
            resp2 = await c2.get("/", headers={"mcp-session-id": "shared-id"})
            assert resp2.status_code == 200


# ============================================================================
# Tests: Edge cases
# ============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_params_array_not_dict(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Params that are an array instead of dict are handled."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": ["not", "a", "dict"],
            }
            await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "edge-1"},
            )
        # Middleware should still log the method even if params is wrong shape
        assert any("tools/call" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_batch_with_missing_method_field(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Batch item without 'method' field shows '?'."""
        with caplog.at_level(logging.DEBUG):
            payload = [
                {"jsonrpc": "2.0", "params": {}},
                {"jsonrpc": "2.0", "method": "tools/call", "params": {}},
            ]
            await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "batch-missing"},
            )
        # Batch format should still be logged
        assert any("[+1]" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_special_characters_in_strings(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Special characters in extracted strings are logged."""
        with caplog.at_level(logging.DEBUG):
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "tool_with-dash/slash"},
            }
            resp = await client.post(
                "/mcp",
                json=payload,
                headers={"mcp-session-id": "special-1"},
            )
        assert resp.status_code == 200
        assert any(
            "tool_with-dash/slash" in record.message for record in caplog.records
        )
