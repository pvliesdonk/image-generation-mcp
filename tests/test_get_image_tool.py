"""Tests for ResourcesAsTools transform — tool-only client access to resources."""

from __future__ import annotations

import pytest

from image_generation_mcp.mcp_server import create_server


class TestResourcesAsToolsRegistration:
    """Verify ResourcesAsTools generates list_resources and read_resource tools."""

    async def test_list_resources_tool_exists(self) -> None:
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names

    async def test_read_resource_tool_exists(self) -> None:
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "read_resource" in tool_names

    async def test_original_tools_still_present(self) -> None:
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_providers" in tool_names

    async def test_hand_written_get_image_removed(self) -> None:
        """get_image and list_images are no longer registered as tools."""
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "get_image" not in tool_names
        assert "list_images" not in tool_names


class TestResourcesAsToolsReadOnly:
    """Verify transform works in both read-only and read-write modes."""

    async def test_read_only_has_resource_tools(self) -> None:
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names

    async def test_read_write_has_resource_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names

    async def test_read_write_has_generate_and_resource_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "generate_image" in tool_names
        assert "list_resources" in tool_names
        assert "read_resource" in tool_names
