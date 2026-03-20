"""Tests for the get_image and list_images tools."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from PIL import Image

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import ImageProviderError, ImageResult
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from pathlib import Path


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
async def image_result() -> ImageResult:
    """Generate a 16:9 test image via PlaceholderImageProvider."""
    provider = PlaceholderImageProvider()
    return await provider.generate("tool test", aspect_ratio="16:9")


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    """Create an ImageService with a temp scratch directory."""
    return ImageService(scratch_dir=tmp_path)


@pytest.fixture
def registered(
    service: ImageService, image_result: ImageResult
) -> tuple[ImageService, str]:
    """Register a test image and return (service, image_id)."""
    record = service.register_image(
        image_result, "placeholder", prompt="tool test"
    )
    return service, record.id


# -- Tool registration --------------------------------------------------------


class TestToolRegistration:
    """Verify the new tools are registered with correct metadata."""

    async def test_get_image_registered(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("get_image")
        assert tool is not None

    async def test_get_image_no_write_tag(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("get_image")
        assert "write" not in (tool.tags or set())

    async def test_list_images_registered(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("list_images")
        assert tool is not None

    async def test_list_images_no_write_tag(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("list_images")
        assert "write" not in (tool.tags or set())


# -- get_image: service-layer logic (same as resource) ------------------------


class TestGetImageRetrieval:
    """Test the retrieval and transform logic used by get_image."""

    def test_original_bytes_roundtrip(
        self,
        registered: tuple[ImageService, str],
        image_result: ImageResult,
    ) -> None:
        """Reading with no transforms returns original bytes."""
        service, image_id = registered
        record = service.get_image(image_id)
        data = record.original_path.read_bytes()
        assert data == image_result.image_data

    def test_format_conversion_to_webp(
        self, registered: tuple[ImageService, str]
    ) -> None:
        """Format conversion produces valid WebP."""
        from image_generation_mcp.processing import convert_format

        service, image_id = registered
        record = service.get_image(image_id)
        original = record.original_path.read_bytes()
        data, content_type = convert_format(original, "webp")
        assert content_type == "image/webp"
        img = Image.open(io.BytesIO(data))
        assert img.format == "WEBP"

    def test_crop_to_dimensions(
        self, registered: tuple[ImageService, str]
    ) -> None:
        """Width+height center-crops to exact dimensions."""
        from image_generation_mcp.processing import crop_to_dimensions

        service, image_id = registered
        record = service.get_image(image_id)
        original = record.original_path.read_bytes()
        data = crop_to_dimensions(original, 200, 200)
        img = Image.open(io.BytesIO(data))
        assert img.size == (200, 200)

    def test_proportional_resize_width(
        self, registered: tuple[ImageService, str]
    ) -> None:
        """Width-only resize preserves aspect ratio."""
        from image_generation_mcp.processing import resize_image

        service, image_id = registered
        record = service.get_image(image_id)
        original = record.original_path.read_bytes()
        img = Image.open(io.BytesIO(original))
        ratio = 320 / img.width
        new_height = round(img.height * ratio)
        data = resize_image(original, 320, new_height)
        result_img = Image.open(io.BytesIO(data))
        assert result_img.width == 320
        assert result_img.height == new_height

    def test_proportional_resize_height(
        self, registered: tuple[ImageService, str]
    ) -> None:
        """Height-only resize preserves aspect ratio."""
        from image_generation_mcp.processing import resize_image

        service, image_id = registered
        record = service.get_image(image_id)
        original = record.original_path.read_bytes()
        img = Image.open(io.BytesIO(original))
        ratio = 200 / img.height
        new_width = round(img.width * ratio)
        data = resize_image(original, new_width, 200)
        result_img = Image.open(io.BytesIO(data))
        assert result_img.height == 200
        assert result_img.width == new_width

    def test_unknown_id_raises(self, service: ImageService) -> None:
        """get_image raises for nonexistent ID."""
        with pytest.raises(ImageProviderError, match="not found"):
            service.get_image("nonexistent_id")


# -- list_images: service-layer logic -----------------------------------------


class TestListImagesRetrieval:
    """Test the listing logic used by list_images."""

    def test_empty_service_returns_empty(self, service: ImageService) -> None:
        assert service.list_images() == []

    def test_single_image_listed(
        self, registered: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered
        images = service.list_images()
        assert len(images) == 1
        assert images[0].id == image_id

    def test_listed_image_has_expected_fields(
        self, registered: tuple[ImageService, str]
    ) -> None:
        service, _image_id = registered
        img = service.list_images()[0]
        assert img.provider == "placeholder"
        assert img.prompt == "tool test"
        assert img.content_type == "image/png"
        assert img.original_dimensions[0] > 0
        assert img.created_at > 0


# -- Read-only visibility -----------------------------------------------------


class TestReadOnlyVisibility:
    """New tools are visible in both read-only and read-write mode."""

    async def test_get_image_visible_read_only(self) -> None:
        from image_generation_mcp.mcp_server import create_server

        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "get_image" in tool_names

    async def test_list_images_visible_read_only(self) -> None:
        from image_generation_mcp.mcp_server import create_server

        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_images" in tool_names

    async def test_get_image_visible_read_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from image_generation_mcp.mcp_server import create_server

        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "get_image" in tool_names

    async def test_list_images_visible_read_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from image_generation_mcp.mcp_server import create_server

        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        server = create_server()
        tool_names = [t.name for t in await server.list_tools()]
        assert "list_images" in tool_names
