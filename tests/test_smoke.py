"""Smoke tests for Image Generation MCP.

Restores the template's smoke-coverage classes adapted to this server's actual
MCP surface: server construction, ``get_server_info``, and that the core domain
tools and prompts are wired. The template's example-specific smoke tests
(``status://`` resource, ``summarize`` prompt, ``_server_apps.register_apps``,
the template ``register_file_exchange`` check) don't port — this repo replaced
those scaffolds with domain features covered by their own test modules.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Client

from image_generation_mcp.server import make_server


def test_make_server_constructs() -> None:
    """make_server() returns a FastMCP instance without raising."""
    server = make_server()
    assert server is not None


async def test_get_server_info_tool_registered(client: Client[Any]) -> None:
    """``get_server_info`` is wired and returns the wrapper info block."""
    tools = {t.name for t in await client.list_tools()}
    assert "get_server_info" in tools

    result = await client.call_tool("get_server_info", {})
    first = result.content[0]
    assert hasattr(first, "text"), (
        f"expected text tool content, got {type(first).__name__}"
    )
    payload = json.loads(first.text)
    assert payload["server_name"] == "image-generation-mcp"
    assert "server_version" in payload
    assert "core_version" in payload


async def test_core_tools_registered(client: Client[Any]) -> None:
    """A core read tool is discoverable on the default (read-only) server."""
    tools = {t.name for t in await client.list_tools()}
    assert "list_providers" in tools


async def test_domain_prompts_registered(client: Client[Any]) -> None:
    """The domain prompts are registered and discoverable."""
    prompts = {p.name for p in await client.list_prompts()}
    assert {"select_provider", "sd_prompt_guide", "apply_style"} <= prompts
