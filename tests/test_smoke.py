"""Smoke tests for Image Generation MCP."""

from __future__ import annotations

from image_generation_mcp.server import make_server


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    server = make_server()
    assert server is not None
