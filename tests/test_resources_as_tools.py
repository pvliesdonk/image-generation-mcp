"""Tests for ResourcesAsTools transform — tool-only client access to resources."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from image_generation_mcp.server import make_server

if TYPE_CHECKING:
    from pathlib import Path


class TestResourcesAsToolsRegistration:
    """Verify ResourcesAsTools generates list_resources and read_resource tools."""

    async def test_list_resources_tool_exists(self) -> None:
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names

    async def test_read_resource_tool_exists(self) -> None:
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "read_resource" in tool_names

    async def test_original_tools_still_present(self) -> None:
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names

    async def test_hand_written_get_image_removed(self) -> None:
        """get_image and list_images are no longer registered as tools."""
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "get_image" not in tool_names
        assert "list_images" not in tool_names


class TestResourcesAsToolsReadOnly:
    """Verify transform works in both read-only and read-write modes."""

    async def test_read_only_has_resource_tools(self) -> None:
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names

    async def test_read_write_has_resource_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names

    async def test_read_write_has_generate_and_resource_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = make_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "generate_image" in tool_names
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names


class TestResourcesAsToolsEndToEnd:
    """End-to-end wiring: read_resource executes the underlying resource."""

    async def test_read_resource_tool_returns_image_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Calling read_resource with image://list returns valid JSON.

        Exercises the full wiring: ResourcesAsTools tool -> server lifespan ->
        image_list resource -> ImageService.list_images(). Uses an isolated
        scratch dir so the result is a deterministic empty JSON array.
        """
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SCRATCH_DIR", str(tmp_path))
        server = make_server()
        async with Client(server) as client:
            result = await client.call_tool("read_resource", {"uri": "image://list"})

        assert result is not None
        assert not result.is_error
        # Result contains one TextContent item with JSON text
        assert len(result.content) == 1
        parsed = json.loads(result.content[0].text)
        assert isinstance(parsed, list)
        assert parsed == []  # isolated scratch dir, no images
