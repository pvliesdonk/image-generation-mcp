"""Tests for generate_image and show_image MCP tools.

Covers:
- generate_image returns TextContent + ResourceLink only (no ImageContent)
- generate_image has no AppConfig (viewer moved to show_image)
- show_image returns ImageContent + TextContent
- show_image with format conversion
- show_image with resize (width-only, height-only)
- show_image with crop (width+height)
- show_image metadata includes model field from provider_metadata
- show_image auto-generates download_url when base_url configured
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import unittest.mock
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, ResourceLink, TextContent
from PIL import Image

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import ImageResult
from image_generation_mcp.service import ImageService
from tests._helpers import get_tool_including_app_only

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
    result = asyncio.run(
        PlaceholderImageProvider().generate("show test", aspect_ratio="1:1")
    )
    record = service.register_image(result, "placeholder", prompt="show test")
    return service, record.id


def _make_large_png(width: int = 1024, height: int = 768) -> bytes:
    """Create a synthetic PNG larger than 512px for thumbnail cap tests."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def large_registered_image(service: ImageService) -> tuple[ImageService, str]:
    """Register a 1024x768 synthetic image and return (service, image_id)."""
    png_data = _make_large_png(1024, 768)
    result = ImageResult(image_data=png_data, content_type="image/png")
    record = service.register_image(result, "test", prompt="large test")
    return service, record.id


# ---------------------------------------------------------------------------
# generate_image: return shape
# ---------------------------------------------------------------------------


class TestGenerateImageReturnShape:
    """generate_image must return TextContent + ResourceLink, no ImageContent."""

    async def _call_generate(self, service: ImageService) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.info = AsyncMock()
        cfg = MagicMock()
        cfg.paid_providers = frozenset()

        return await tool.fn(
            prompt="test image",
            provider="placeholder",
            service=service,
            config=cfg,
            ctx=ctx,
        )

    async def test_returns_text_content(self, service: ImageService) -> None:
        result = await self._call_generate(service)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert len(text_items) == 1
        metadata = json.loads(text_items[0].text)
        assert "image_id" in metadata
        assert "original_uri" in metadata
        assert metadata["status"] == "generating"
        assert "dimensions" not in metadata
        assert "original_size_bytes" not in metadata

    async def test_returns_resource_link(self, service: ImageService) -> None:
        result = await self._call_generate(service)
        link_items = [c for c in result.content if isinstance(c, ResourceLink)]
        assert len(link_items) == 1
        assert str(link_items[0].uri).startswith("image://")
        assert link_items[0].name == "Generated image (generating)"

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
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        assert tool is not None
        cfg = MagicMock()
        cfg.server.base_url = None
        return await tool.fn(
            uri=f"image://{image_id}/view{uri_suffix}",
            service=service,
            config=cfg,
        )

    async def test_returns_image_content(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id)
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert len(image_items) == 1
        assert image_items[0].data  # non-empty base64
        # ImageContent is always a WebP thumbnail capped at 512px
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert max(img.size) <= 512

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
        assert "thumbnail_dimensions" in meta
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
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        cfg = MagicMock()
        cfg.server.base_url = None
        return await tool.fn(
            uri=f"image://{image_id}/view?{query}",
            service=service,
            config=cfg,
        )

    async def test_format_webp(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "format=webp")

        # ImageContent is always a WebP thumbnail (capped at 512px)
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.format == "WEBP"
        assert max(img.size) <= 512

        # Metadata records the requested transform
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["format"] == "webp"
        assert "thumbnail_dimensions" in meta

    async def test_format_jpeg_metadata(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Format conversion is recorded in metadata; thumbnail is still WebP."""
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "format=jpeg")

        # ImageContent is always WebP thumbnail regardless of requested format
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"

        # Metadata records the requested jpeg conversion
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["format"] == "jpeg"
        assert meta["format"] == "image/jpeg"


class TestShowImageResize:
    """show_image with width/height query params resizes the image."""

    async def _call_show(
        self, service: ImageService, image_id: str, query: str
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        cfg = MagicMock()
        cfg.server.base_url = None
        return await tool.fn(
            uri=f"image://{image_id}/view?{query}",
            service=service,
            config=cfg,
        )

    async def test_width_only_resize(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "width=100")

        # ImageContent is a WebP thumbnail; 100px < 512px cap so resize preserved
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.width == 100  # resize applied; still under 512px cap

        # Metadata records the requested width transform
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["width"] == 100
        assert meta["dimensions"][0] == 100
        assert "thumbnail_dimensions" in meta

    async def test_height_only_resize(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "height=60")

        # ImageContent is a WebP thumbnail; 60px < 512px cap so resize preserved
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.height == 60  # resize applied; still under 512px cap

        # Metadata records the requested height transform
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["height"] == 60
        assert meta["dimensions"][1] == 60
        assert "thumbnail_dimensions" in meta

    async def test_crop_width_and_height(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_show(service, image_id, "width=80&height=80")

        # ImageContent is a WebP thumbnail; 80px < 512px cap so crop preserved
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert img.size == (80, 80)  # crop applied; still under 512px cap

        # Metadata records the requested crop
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["width"] == 80
        assert meta["transforms_applied"]["height"] == 80
        assert meta["dimensions"] == [80, 80]


class TestShowImageThumbnailCap:
    """show_image caps ImageContent to a 512px WebP thumbnail for large images."""

    async def _call_show(
        self, service: ImageService, image_id: str, uri_suffix: str = ""
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        cfg = MagicMock()
        cfg.server.base_url = None
        return await tool.fn(
            uri=f"image://{image_id}/view{uri_suffix}",
            service=service,
            config=cfg,
        )

    async def test_large_image_downscaled_to_512(
        self, large_registered_image: tuple[ImageService, str]
    ) -> None:
        """A 1024x768 image is downscaled so longest edge is 512px."""
        service, image_id = large_registered_image
        result = await self._call_show(service, image_id)

        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        # Longest edge must be exactly 512 (downscaled from 1024)
        assert max(img.size) == 512
        # Aspect ratio preserved: 1024:768 = 512:384
        assert img.size == (512, 384)

    async def test_large_image_metadata_reports_original_dimensions(
        self, large_registered_image: tuple[ImageService, str]
    ) -> None:
        """Metadata dimensions reflect original size, not thumbnail."""
        service, image_id = large_registered_image
        result = await self._call_show(service, image_id)

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        # dimensions = original (no transforms requested)
        assert meta["dimensions"] == [1024, 768]
        # thumbnail_dimensions = downscaled
        assert meta["thumbnail_dimensions"] == [512, 384]

    async def test_large_image_under_1mb(
        self, large_registered_image: tuple[ImageService, str]
    ) -> None:
        """Thumbnail base64 stays well under the 1 MB client limit."""
        service, image_id = large_registered_image
        result = await self._call_show(service, image_id)

        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        # base64 string length < 1 MB
        assert len(image_items[0].data) < 1_000_000

    async def test_large_image_with_resize_still_capped(
        self, large_registered_image: tuple[ImageService, str]
    ) -> None:
        """Resize to width=800 on a 1024x768 image: dimensions=800x600, thumbnail capped to 512."""
        service, image_id = large_registered_image
        result = await self._call_show(service, image_id, "?width=800")

        # Thumbnail is still capped at 512px
        image_items = [c for c in result.content if isinstance(c, ImageContent)]
        assert image_items[0].mimeType == "image/webp"
        raw = base64.b64decode(image_items[0].data)
        img = Image.open(io.BytesIO(raw))
        assert max(img.size) == 512

        # Metadata reports the transform result, not the thumbnail
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["dimensions"] == [800, 600]
        assert meta["thumbnail_dimensions"][0] <= 512
        assert meta["transforms_applied"]["width"] == 800


# generate_image — elicitation confirmation for paid providers
# ---------------------------------------------------------------------------


class TestElicitationPaidProviders:
    """generate_image asks for confirmation before using paid providers."""

    async def _call_generate(
        self,
        service: ImageService,
        *,
        provider: str = "placeholder",
        paid_providers: frozenset[str] = frozenset(),
        elicitation_supported: bool = False,
        elicitation_accepted: bool = True,
        elicit_response: object | None = None,
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.info = AsyncMock()
        ctx.session.check_client_capability.return_value = elicitation_supported

        if elicitation_supported:
            from fastmcp.server.elicitation import AcceptedElicitation

            if elicitation_accepted:
                ctx.elicit = AsyncMock(return_value=AcceptedElicitation(data={}))
            elif elicit_response is not None:
                ctx.elicit = AsyncMock(return_value=elicit_response)
            else:
                from fastmcp.server.elicitation import CancelledElicitation

                ctx.elicit = AsyncMock(return_value=CancelledElicitation())

        cfg = MagicMock()
        cfg.paid_providers = paid_providers

        return await tool.fn(
            prompt="test image",
            provider=provider,
            service=service,
            config=cfg,
            ctx=ctx,
        )

    async def test_free_provider_no_elicitation(self, service: ImageService) -> None:
        """Free provider proceeds without elicitation regardless of support."""
        result = await self._call_generate(
            service,
            provider="placeholder",
            paid_providers=frozenset({"openai"}),
            elicitation_supported=True,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "image_id" in meta

    async def test_paid_provider_no_elicitation_support(
        self, service: ImageService
    ) -> None:
        """Paid provider proceeds silently when client lacks elicitation."""
        result = await self._call_generate(
            service,
            provider="placeholder",
            paid_providers=frozenset({"placeholder"}),
            elicitation_supported=False,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "image_id" in meta

    async def test_paid_provider_elicitation_accepted(
        self, service: ImageService
    ) -> None:
        """Paid provider proceeds after user accepts elicitation."""
        result = await self._call_generate(
            service,
            provider="placeholder",
            paid_providers=frozenset({"placeholder"}),
            elicitation_supported=True,
            elicitation_accepted=True,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "image_id" in meta

    async def test_paid_provider_elicitation_cancelled(
        self, service: ImageService
    ) -> None:
        """Paid provider returns cancellation when user cancels."""
        result = await self._call_generate(
            service,
            provider="placeholder",
            paid_providers=frozenset({"placeholder"}),
            elicitation_supported=True,
            elicitation_accepted=False,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert len(text_items) == 1
        assert "cancelled" in text_items[0].text.lower()

    async def test_paid_provider_elicitation_declined(
        self, service: ImageService
    ) -> None:
        """Paid provider returns cancellation when user declines."""
        from fastmcp.server.elicitation import DeclinedElicitation

        result = await self._call_generate(
            service,
            provider="placeholder",
            paid_providers=frozenset({"placeholder"}),
            elicitation_supported=True,
            elicitation_accepted=False,
            elicit_response=DeclinedElicitation(),
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        assert len(text_items) == 1
        assert "cancelled" in text_items[0].text.lower()


# ---------------------------------------------------------------------------
# show_image — model field in metadata
# ---------------------------------------------------------------------------


class TestShowImageModelField:
    """show_image metadata includes model from provider_metadata."""

    @pytest.fixture
    def image_with_model(self, service: ImageService) -> tuple[ImageService, str]:
        """Register an image whose provider_metadata includes a model."""
        result = asyncio.run(
            PlaceholderImageProvider().generate("model test", aspect_ratio="1:1")
        )
        # Inject a model key to simulate a real provider (e.g. OpenAI)
        result.provider_metadata["model"] = "dreamshaper_xl"
        record = service.register_image(result, "test-provider", prompt="model test")
        return service, record.id

    async def _call_show(self, service: ImageService, image_id: str) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        cfg = MagicMock()
        cfg.server.base_url = None
        return await tool.fn(
            uri=f"image://{image_id}/view",
            service=service,
            config=cfg,
        )

    async def test_model_present_in_metadata(
        self, image_with_model: tuple[ImageService, str]
    ) -> None:
        service, image_id = image_with_model
        result = await self._call_show(service, image_id)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["model"] == "dreamshaper_xl"

    async def test_model_none_when_absent(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Placeholder provider has no model key — field should be None."""
        service, image_id = registered_image
        result = await self._call_show(service, image_id)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["model"] is None


# ---------------------------------------------------------------------------
# show_image — download_url auto-generation
# ---------------------------------------------------------------------------


class TestShowImageDownloadUrl:
    """show_image auto-generates download_url when base_url is configured."""

    @pytest.fixture
    def _registered(self, service: ImageService) -> tuple[ImageService, str]:
        result = asyncio.run(
            PlaceholderImageProvider().generate("dl test", aspect_ratio="1:1")
        )
        record = service.register_image(result, "placeholder", prompt="dl test")
        return service, record.id

    async def _call_show(
        self,
        service: ImageService,
        image_id: str,
        *,
        base_url: str | None = None,
        with_link: bool = True,
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        cfg = MagicMock()
        cfg.server.base_url = base_url
        return await tool.fn(
            uri=f"image://{image_id}/view",
            with_link=with_link,
            service=service,
            config=cfg,
        )

    async def test_no_download_url_without_base_url(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        """No download_url when base_url is not configured (stdio)."""
        service, image_id = _registered
        result = await self._call_show(service, image_id, base_url=None)
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "download_url" not in meta

    async def test_download_url_with_base_url(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        """download_url present when base_url is configured."""
        from image_generation_mcp.artifacts import (
            ArtifactStore,
            set_artifact_store,
        )

        store = ArtifactStore()
        set_artifact_store(store)
        try:
            service, image_id = _registered
            result = await self._call_show(
                service, image_id, base_url="https://mcp.example.com"
            )
            text_items = [c for c in result.content if isinstance(c, TextContent)]
            meta = json.loads(text_items[0].text)
            assert "download_url" in meta
            assert meta["download_url"].startswith("https://mcp.example.com/artifacts/")
        finally:
            set_artifact_store(None)

    async def test_no_download_url_when_artifact_store_not_initialized(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        """download_url absent when artifact store not initialized (RuntimeError)."""
        service, image_id = _registered
        result = await self._call_show(
            service, image_id, base_url="https://mcp.example.com"
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "download_url" not in meta

    async def test_no_download_url_when_with_link_false(
        self, _registered: tuple[ImageService, str]
    ) -> None:
        """download_url suppressed when with_link=False."""
        service, image_id = _registered
        result = await self._call_show(
            service,
            image_id,
            base_url="https://mcp.example.com",
            with_link=False,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "download_url" not in meta


# ---------------------------------------------------------------------------
# generate_image — parameter validation errors
# ---------------------------------------------------------------------------


class TestGenerateImageParameterValidation:
    """generate_image raises ValueError for invalid parameters."""

    async def _call_generate(
        self,
        service: ImageService,
        *,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        cfg = MagicMock()
        cfg.paid_providers = frozenset()

        return await tool.fn(
            prompt="test image",
            provider="placeholder",
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
            service=service,
            config=cfg,
            ctx=ctx,
        )

    async def test_invalid_aspect_ratio_raises(self, service: ImageService) -> None:
        """Unsupported aspect_ratio raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported aspect_ratio"):
            await self._call_generate(service, aspect_ratio="5:4")

    async def test_invalid_quality_raises(self, service: ImageService) -> None:
        """Unsupported quality level raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported quality"):
            await self._call_generate(service, quality="ultra")

    async def test_invalid_background_raises(self, service: ImageService) -> None:
        """Unsupported background raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported background"):
            await self._call_generate(service, background="blur")


# ---------------------------------------------------------------------------
# generate_image — error handling (content policy, connection)
# ---------------------------------------------------------------------------


class TestGenerateImageErrorHandling:
    """generate_image errors surface through show_image in fire-and-forget mode."""

    async def _call_generate_failing(
        self, service: ImageService, side_effect: Exception
    ) -> str:
        """Call generate_image with a provider that raises, wait for failure.

        Permanently replaces service.generate with a raising coroutine so the
        patch stays active when the background task runs.  Returns image_id.
        """

        async def _always_raise(*_args: object, **_kwargs: object) -> None:
            raise side_effect

        service.generate = _always_raise  # type: ignore[assignment]

        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.info = AsyncMock()
        ctx.session.check_client_capability.return_value = False
        cfg = MagicMock()
        cfg.paid_providers = frozenset()

        result = await tool.fn(
            prompt="test image",
            provider="placeholder",
            service=service,
            config=cfg,
            ctx=ctx,
        )

        text_items = [c for c in result.content if isinstance(c, TextContent)]
        return json.loads(text_items[0].text)["image_id"]

    async def test_content_policy_error_redirects_in_show_image(
        self, service: ImageService
    ) -> None:
        """ImageContentPolicyError: show_image redirects to check_generation_status."""
        from image_generation_mcp.providers.types import ImageContentPolicyError

        image_id = await self._call_generate_failing(
            service, ImageContentPolicyError("placeholder", "blocked")
        )

        # Let the background task run and fail
        await asyncio.sleep(0.1)

        mcp = FastMCP("test")
        register_tools(mcp)
        show_tool = await mcp.get_tool("show_image")
        assert show_tool is not None
        show_cfg = MagicMock()
        show_cfg.server.base_url = None
        show_result = await show_tool.fn(
            uri=f"image://{image_id}/view",
            service=service,
            config=show_cfg,
        )
        show_text = [c for c in show_result.content if isinstance(c, TextContent)]
        meta = json.loads(show_text[0].text)
        assert meta["status"] == "failed"
        assert "check_generation_status" in meta["error"]

    async def test_connection_error_redirects_in_show_image(
        self, service: ImageService
    ) -> None:
        """ImageProviderConnectionError: show_image redirects to check_generation_status."""
        from image_generation_mcp.providers.types import ImageProviderConnectionError

        image_id = await self._call_generate_failing(
            service,
            ImageProviderConnectionError("placeholder", "connection refused"),
        )

        # Let the background task run and fail
        await asyncio.sleep(0.1)

        mcp = FastMCP("test")
        register_tools(mcp)
        show_tool = await mcp.get_tool("show_image")
        assert show_tool is not None
        show_cfg = MagicMock()
        show_cfg.server.base_url = None
        show_result = await show_tool.fn(
            uri=f"image://{image_id}/view",
            service=service,
            config=show_cfg,
        )
        show_text = [c for c in show_result.content if isinstance(c, TextContent)]
        meta = json.loads(show_text[0].text)
        assert meta["status"] == "failed"
        assert "check_generation_status" in meta["error"]


# ---------------------------------------------------------------------------
# generate_image — elicitation: check_client_capability exception path
# ---------------------------------------------------------------------------


class TestElicitationCapabilityCheckFailure:
    """check_client_capability exception defaults to no elicitation support."""

    async def test_capability_check_exception_falls_back(
        self, service: ImageService
    ) -> None:
        """Exception in check_client_capability assumes no elicitation support."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("generate_image")
        assert tool is not None

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.info = AsyncMock()
        # check_client_capability raises an exception
        ctx.session.check_client_capability.side_effect = RuntimeError("no session")

        cfg = MagicMock()
        # placeholder is in paid_providers to trigger elicitation path
        cfg.paid_providers = frozenset({"placeholder"})

        result = await tool.fn(
            prompt="test image",
            provider="placeholder",
            service=service,
            config=cfg,
            ctx=ctx,
        )
        # Should proceed (no elicitation called) and return a valid image_id
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert "image_id" in meta


# ---------------------------------------------------------------------------
# show_image — invalid scheme error
# ---------------------------------------------------------------------------


class TestShowImageInvalidScheme:
    """show_image raises ValueError for non-image:// URIs."""

    async def test_wrong_scheme_raises(self, service: ImageService) -> None:
        """Passing an https:// URI raises ValueError."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        assert tool is not None

        cfg = MagicMock()
        cfg.server.base_url = None

        with pytest.raises(ValueError, match="Expected an image://"):
            await tool.fn(
                uri="https://example.com/image.png",
                service=service,
                config=cfg,
            )


# ---------------------------------------------------------------------------
# show_image — quality in transform_params when non-default
# ---------------------------------------------------------------------------


class TestShowImageQualityTransform:
    """show_image includes quality in transforms_applied when non-default and format set."""

    async def test_quality_in_transform_params(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """quality != 90 appears in transforms_applied when format is also set."""
        service, image_id = registered_image

        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("show_image")
        assert tool is not None

        cfg = MagicMock()
        cfg.server.base_url = None

        result = await tool.fn(
            uri=f"image://{image_id}/view?format=jpeg&quality=75",
            service=service,
            config=cfg,
        )
        text_items = [c for c in result.content if isinstance(c, TextContent)]
        meta = json.loads(text_items[0].text)
        assert meta["transforms_applied"]["format"] == "jpeg"
        assert meta["transforms_applied"]["quality"] == 75


# ---------------------------------------------------------------------------
# list_providers tool — direct tool execution
# ---------------------------------------------------------------------------


class TestListProvidersTool:
    """list_providers tool returns JSON with provider info."""

    async def test_list_providers_returns_json(self, service: ImageService) -> None:
        """list_providers tool returns valid JSON with provider names."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("list_providers")
        assert tool is not None

        result = await tool.fn(service=service)
        data = json.loads(result)
        assert "refreshed_at" in data
        assert "providers" in data
        assert "placeholder" in data["providers"]
        assert data["providers"]["placeholder"]["available"] is True

    async def test_list_providers_force_refresh_calls_discover(
        self, service: ImageService
    ) -> None:
        """force_refresh=True triggers capability re-discovery."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("list_providers")

        with unittest.mock.patch.object(
            service,
            "discover_all_capabilities",
            new_callable=AsyncMock,
        ) as mock_discover:
            result = await tool.fn(force_refresh=True, service=service)
            mock_discover.assert_awaited_once()

        data = json.loads(result)
        assert "refreshed_at" in data


# ---------------------------------------------------------------------------
# create_download_link — registered on non-stdio transports
# ---------------------------------------------------------------------------


class TestCreateDownloadLinkTool:
    """create_download_link is registered on non-stdio transports only."""

    async def test_registered_on_http_transport(self) -> None:
        """create_download_link tool exists when transport='http'."""
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

    async def test_not_registered_on_stdio_transport(self) -> None:
        """create_download_link tool does not exist when transport='stdio'."""
        mcp = FastMCP("test")
        register_tools(mcp, transport="stdio")
        tool = await mcp.get_tool("create_download_link")
        assert tool is None


# ---------------------------------------------------------------------------
# Tool annotations (readOnlyHint, destructiveHint, openWorldHint)
# ---------------------------------------------------------------------------


class TestToolAnnotations:
    """Verify all tools have correct MCP tool annotations for ChatGPT compat."""

    @pytest.mark.parametrize(
        "tool_name,expected",
        [
            (
                "generate_image",
                {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "openWorldHint": True,
                },
            ),
            (
                "show_image",
                {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "openWorldHint": False,
                },
            ),
            (
                "list_providers",
                {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "openWorldHint": True,
                    "idempotentHint": False,
                },
            ),
        ],
    )
    async def test_tool_annotations(
        self, tool_name: str, expected: dict[str, bool]
    ) -> None:
        """Each tool has the expected MCP annotations."""
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool(tool_name)
        assert tool is not None
        assert tool.annotations is not None
        for key, value in expected.items():
            assert getattr(tool.annotations, key) == value, (
                f"{tool_name}.annotations.{key}: "
                f"expected {value}, got {getattr(tool.annotations, key)}"
            )

    async def test_create_download_link_annotations(self) -> None:
        """create_download_link has read-only annotations (HTTP transport)."""
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False


# ---------------------------------------------------------------------------
# edit_image tool
# ---------------------------------------------------------------------------


class TestEditImageTool:
    """edit_image returns image + editable metadata; _save_edited_image persists."""

    async def _call_edit(self, service: ImageService, image_id: str) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("edit_image")
        assert tool is not None
        return await tool.fn(image_id=image_id, service=service)

    async def test_edit_image_returns_text_and_image_content(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """edit_image returns TextContent + ImageContent with editable flag."""
        service, image_id = registered_image
        result = await self._call_edit(service, image_id)
        types = [c.type for c in result.content]
        assert "text" in types
        assert "image" in types

    async def test_edit_image_metadata_has_editable_flag(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Text content in edit_image result must set editable=true."""
        service, image_id = registered_image
        result = await self._call_edit(service, image_id)
        text_item = next(c for c in result.content if c.type == "text")
        meta = json.loads(text_item.text)
        assert meta["editable"] is True
        assert meta["image_id"] == image_id

    async def test_edit_image_returns_valid_base64(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """ImageContent from edit_image must be valid base64-encoded image data."""
        service, image_id = registered_image
        result = await self._call_edit(service, image_id)
        img_item = next(c for c in result.content if c.type == "image")
        raw = base64.b64decode(img_item.data)
        img = Image.open(io.BytesIO(raw))
        assert img.width > 0

    async def test_edit_image_unknown_id_raises(self, service: ImageService) -> None:
        """edit_image raises for an unknown image_id."""
        from image_generation_mcp.providers.types import ImageProviderError

        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await mcp.get_tool("edit_image")
        assert tool is not None

        with pytest.raises(ImageProviderError):
            await tool.fn(image_id="nonexistent", service=service)


# ---------------------------------------------------------------------------
# _save_edited_image tool
# ---------------------------------------------------------------------------


class TestSaveEditedImageTool:
    """_save_edited_image persists transform results as a new ImageRecord."""

    async def _call_save(
        self,
        service: ImageService,
        source_image_id: str,
        **kwargs: object,
    ) -> ToolResult:
        mcp = FastMCP("test")
        register_tools(mcp)
        tool = await get_tool_including_app_only(mcp, "_save_edited_image")
        assert tool is not None
        return await tool.fn(source_image_id=source_image_id, service=service, **kwargs)

    async def test_save_no_transforms_creates_copy(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Saving with no transforms creates a new image record."""
        service, image_id = registered_image
        result = await self._call_save(service, image_id)
        text_item = next(c for c in result.content if c.type == "text")
        data = json.loads(text_item.text)
        assert "image_id" in data
        assert data["source_image_id"] == image_id
        # Result must be registered (retrievable from service)
        assert service.get_image(data["image_id"]) is not None

    async def test_save_with_crop_produces_cropped_image(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Crop transform produces image with correct dimensions."""
        service, image_id = registered_image
        result = await self._call_save(
            service, image_id, crop={"x": 0, "y": 0, "w": 50, "h": 50}
        )
        text_item = next(c for c in result.content if c.type == "text")
        new_id = json.loads(text_item.text)["image_id"]
        new_record = service.get_image(new_id)
        img = Image.open(io.BytesIO(new_record.original_path.read_bytes()))
        assert img.size == (50, 50)

    async def test_save_with_rotate_produces_rotated_image(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Rotate 90° transposes width and height."""
        service, image_id = registered_image
        original_record = service.get_image(image_id)
        orig_w, orig_h = original_record.original_dimensions

        result = await self._call_save(service, image_id, rotate=90)
        text_item = next(c for c in result.content if c.type == "text")
        new_id = json.loads(text_item.text)["image_id"]
        new_record = service.get_image(new_id)
        img = Image.open(io.BytesIO(new_record.original_path.read_bytes()))
        # 90° rotation swaps width ↔ height
        assert img.size == (orig_h, orig_w)

    async def test_save_with_flip_horizontal(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """flip_horizontal produces a valid image of same dimensions."""
        service, image_id = registered_image
        original_record = service.get_image(image_id)

        result = await self._call_save(service, image_id, flip_horizontal=True)
        text_item = next(c for c in result.content if c.type == "text")
        new_id = json.loads(text_item.text)["image_id"]
        new_record = service.get_image(new_id)
        img = Image.open(io.BytesIO(new_record.original_path.read_bytes()))
        assert img.size == original_record.original_dimensions

    async def test_save_records_source_image_id(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """New record has source_image_id set to the original image_id."""
        service, image_id = registered_image
        result = await self._call_save(service, image_id)
        text_item = next(c for c in result.content if c.type == "text")
        new_id = json.loads(text_item.text)["image_id"]
        new_record = service.get_image(new_id)
        assert new_record.source_image_id == image_id

    async def test_save_invalid_crop_raises(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """_save_edited_image raises for a malformed crop dict."""
        service, image_id = registered_image

        with pytest.raises(ValueError, match="crop must have"):
            await self._call_save(
                service,
                image_id,
                # missing required keys
                crop={"x": 0, "y": 0},
            )
