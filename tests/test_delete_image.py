"""Tests for the delete_image tool and ImageService.delete_image()."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from PIL import Image as PILImage

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import ImageProviderError, ImageResult
from image_generation_mcp.server import make_server
from image_generation_mcp.service import ImageRecord, ImageService

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 32, height: int = 32) -> bytes:
    img = PILImage.new("RGBA", (width, height), color=(100, 150, 200, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _add_image(service: ImageService, idx: int = 0) -> ImageRecord:
    png = _make_png_bytes(width=32 + idx, height=32 + idx)
    result = ImageResult(image_data=png, content_type="image/png")
    return service.register_image(result, "placeholder", prompt=f"test {idx}")


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    svc = ImageService(scratch_dir=tmp_path)
    svc.register_provider("placeholder", PlaceholderImageProvider())
    return svc


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
    return make_server()


@pytest.fixture
def server_readonly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "true")
    return make_server()


# ---------------------------------------------------------------------------
# ImageService.delete_image()
# ---------------------------------------------------------------------------


class TestServiceDeleteImage:
    def test_delete_removes_image_from_registry(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        assert record.id in service._images

        service.delete_image(record.id)
        assert record.id not in service._images

    def test_delete_removes_image_file(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        assert record.original_path.exists()

        service.delete_image(record.id)
        assert not record.original_path.exists()

    def test_delete_removes_sidecar_json(
        self, service: ImageService, tmp_path: Path
    ) -> None:
        record = _add_image(service, 0)
        sidecar = tmp_path / f"{record.id}.json"
        assert sidecar.exists()

        service.delete_image(record.id)
        assert not sidecar.exists()

    def test_delete_returns_record(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        deleted = service.delete_image(record.id)
        assert deleted.id == record.id
        assert deleted.prompt == "test 0"
        assert deleted.provider == "placeholder"

    def test_delete_evicts_transform_cache(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        # Warm the transform cache
        service.get_transformed_image(record.id, "webp", 64, 0, 80)
        cache_keys = list(service._transform_cache.keys())
        assert any(k[0] == record.id for k in cache_keys)

        service.delete_image(record.id)
        remaining_keys = list(service._transform_cache.keys())
        assert not any(k[0] == record.id for k in remaining_keys)

    def test_delete_raises_for_unknown_id(self, service: ImageService) -> None:
        with pytest.raises(ImageProviderError):
            service.delete_image("nonexistent_id")

    def test_delete_second_time_raises(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        service.delete_image(record.id)
        with pytest.raises(ImageProviderError):
            service.delete_image(record.id)


# ---------------------------------------------------------------------------
# delete_image MCP tool
# ---------------------------------------------------------------------------


class TestDeleteImageTool:
    def _mcp(self) -> FastMCP:
        mcp = FastMCP("test")
        register_tools(mcp)
        return mcp

    async def test_delete_tool_registered(self, server) -> None:
        tools = await server.list_tools()
        names = [t.name for t in tools]
        assert "delete_image" in names

    async def test_delete_tool_is_destructive(self, server) -> None:
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "delete_image")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is False
        assert tool.annotations.destructiveHint is True

    async def test_delete_tool_hidden_in_readonly_mode(self, server_readonly) -> None:
        tools = await server_readonly.list_tools()
        names = [t.name for t in tools]
        assert "delete_image" not in names

    async def test_delete_tool_removes_image(self, service: ImageService) -> None:
        record = _add_image(service, 0)
        assert record.id in service._images

        mcp = self._mcp()
        tool = await mcp.get_tool("delete_image")
        assert tool is not None

        result = await tool.fn(image_id=record.id, service=service)
        assert record.id not in service._images
        assert record.id in result

    async def test_delete_tool_returns_confirmation(
        self, service: ImageService
    ) -> None:
        record = _add_image(service, 0)

        mcp = self._mcp()
        tool = await mcp.get_tool("delete_image")
        assert tool is not None

        result = await tool.fn(image_id=record.id, service=service)
        assert "test 0" in result  # prompt in confirmation
        assert "placeholder" in result  # provider in confirmation

    async def test_delete_tool_error_on_missing_id(self, service: ImageService) -> None:
        mcp = self._mcp()
        tool = await mcp.get_tool("delete_image")
        assert tool is not None

        with pytest.raises(ImageProviderError):
            await tool.fn(image_id="nonexistent_id", service=service)


# ---------------------------------------------------------------------------
# Gallery HTML — delete button presence
# ---------------------------------------------------------------------------


class TestGalleryDeleteButton:
    async def test_gallery_html_has_delete_button(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "card-del" in text
        assert "delete_image" in text

    async def test_gallery_html_has_delete_confirmation(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "confirm(" in text
        assert "cannot be undone" in text

    async def test_gallery_html_has_lightbox_delete(self, server) -> None:
        result = await server.read_resource("ui://image-gallery/view.html")
        text = result.contents[0].content
        assert "lb-delete" in text
        assert "deleteLightboxImage" in text
