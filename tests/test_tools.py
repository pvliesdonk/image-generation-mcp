"""Tests for generate_image and show_image MCP tools.

Covers:
- generate_image returns TextContent + ResourceLink only (no ImageContent)
- generate_image has no AppConfig (viewer moved to show_image)
- show_image returns ImageContent + TextContent
- show_image with format conversion
- show_image with resize (width-only, height-only)
- show_image with crop (width+height)
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from fastmcp import FastMCP
from mcp.types import ImageContent, ResourceLink, TextContent
from PIL import Image

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    """ImageService with a temp scratch directory, placeholder provider."""
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


@pytest.fixture
def registered_image(service: ImageService) -> tuple[ImageService, str]:
    """Register a placeholder image and return (service, image_id)."""
    result = asyncio.get_event_loop().run_until_complete(
        PlaceholderImageProvider().generate("show test", aspect_ratio="1:1")
    )
    record = service.register_image(result, "placeholder", prompt="show test")
    return service, record.id


# ---------------------------------------------------------------------------
# generate_image: return shape
# ---------------------------------------------------------------------------


class TestGenerateImageReturnShape:
    """generate_image must return TextContent + ResourceLink, no ImageContent."""

    async def _call_generate(self, service: ImageService) -> object:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()

        return await tool.fn(
            prompt="test image",
            provider="placeholder",
            service=service,
            ctx=ctx,
        )

    async def test_returns_text_content(self, service: ImageService) -> None:
        result = await self._call_generate(service)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert len(text_items) == 1
        metadata = json.loads(text_items[0].text)
        assert "image_id" in metadata
        assert "original_uri" in metadata
        assert "dimensions" in metadata

    async def test_returns_resource_link(self, service: ImageService) -> None:
        result = await self._call_generate(service)
        link_items = [c for c in result.content if isinstance(c, ResourceLink)]
        assert len(link_items) == 1
        assert str(link_items[0].uri).startswith("image://")
        assert link_items[0].name == "Generated image"

    async def test_no_image_content_in_result(self, service: ImageService) -> None:
        result = await self._call_generate(service)
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items == [], "generate_image must not return ImageContent"

    async def test_no_thumbnail_size_bytes_in_metadata(
        self, service: ImageService
    ) -> None:
        result = await self._call_generate(service)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        metadata = json.loads(text_items[0].text)
        assert "thumbnail_size_bytes" not in metadata

    async def test_resource_link_uri_matches_image_id(
        self, service: ImageService
    ) -> None:
        result = await self._call_generate(service)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        metadata = json.loads(text_items[0].text)
        image_id = metadata["image_id"]

        link_items = [c for c in result.content if isinstance(c, ResourceLink)]
        assert str(link_items[0].uri) == f"image://{image_id}/view"


# ---------------------------------------------------------------------------
# generate_image: tool registration properties
# ---------------------------------------------------------------------------


class TestGenerateImageRegistration:
    """generate_image tool registration properties."""

    async def test_no_app_config(self) -> None:
        """generate_image must not carry AppConfig — viewer is on show_image."""
        mcp = FastMCP("test")
        register_tools(mcp)

        tool = await mcp.get_tool("generate_image")
        assert tool is not None
        # meta is None or ui key is absent
        if tool.meta is not None:
            assert tool.meta.get("ui") is None

    async def test_tagged_write(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)

        tool = await mcp.get_tool("generate_image")
        assert tool is not None
        assert "write" in tool.tags


# ---------------------------------------------------------------------------
# show_image: tool registration properties
# ---------------------------------------------------------------------------


class TestShowImageRegistration:
    """show_image tool registration properties."""

    async def test_registered(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)

        tool = await mcp.get_tool("show_image")
        assert tool is not None

    async def test_not_tagged_write(self) -> None:
        """show_image is a read operation — must not carry the 'write' tag."""
        mcp = FastMCP("test")
        register_tools(mcp)

        tool = await mcp.get_tool("show_image")
        assert tool is not None
        assert "write" not in tool.tags

    async def test_has_app_config(self) -> None:
        """show_image carries AppConfig pointing at the image viewer."""
        mcp = FastMCP("test")
        register_tools(mcp)

        tool = await mcp.get_tool("show_image")
        assert tool is not None
        assert tool.meta is not None
        app_data = tool.meta.get("ui")
        assert app_data is not None
        assert app_data["resourceUri"] == "ui://image-viewer/view.html"


# ---------------------------------------------------------------------------
# show_image: functional tests
# ---------------------------------------------------------------------------


class TestShowImageBasic:
    """show_image returns image bytes and metadata for a plain URI."""

    async def _call_show(
        self, service: ImageService, image_id: str, uri_suffix: str = ""
    ) -> object:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        assert tool is not None
        return await tool.fn(
            uri=f"image://{image_id}/view{uri_suffix}",
            service=service,
        )

    async def test_returns_image_content(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id)
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert len(image_items) == 1
        assert image_items[0].data  # non-empty base64

    async def test_returns_text_metadata(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert len(text_items) == 1
        meta = json.loads(text_items[0].text)
        assert meta["image_id"] == image_id
        assert "dimensions" in meta
        assert "format" in meta
        assert "transforms_applied" in meta

    async def test_no_transforms_applied_for_plain_uri(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"] == {}


class TestShowImageFormatConversion:
    """show_image with format query param converts the image."""

    async def _call_show(
        self, service: ImageService, image_id: str, query: str
    ) -> object:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        return await tool.fn(
            uri=f"image://{image_id}/view?{query}",
            service=service,
        )

    async def test_format_webp(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "format=webp")
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"

        # Verify the bytes are actually WebP
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.format == "WEBP"

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["format"] == "webp"

    async def test_format_jpeg(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "format=jpeg")
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/jpeg"

        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.format == "JPEG"


class TestShowImageResize:
    """show_image with width/height query params resizes the image."""

    async def _call_show(
        self, service: ImageService, image_id: str, query: str
    ) -> object:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        return await tool.fn(
            uri=f"image://{image_id}/view?{query}",
            service=service,
        )

    async def test_width_only_resize(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "width=100")

        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.width == 100

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["width"] == 100

    async def test_height_only_resize(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "height=60")

        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.height == 60

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["height"] == 60

    async def test_crop_width_and_height(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "width=80&height=80")

        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.size == (80, 80)

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["width"] == 80
        assert meta["transforms_applied"]["height"] == 80
