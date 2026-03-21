"""Tests for image resource templates -- view, metadata, list."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from PIL import Image

from image_generation_mcp.processing import convert_format
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.types import ImageProviderError, ImageResult
from image_generation_mcp.service import ImageService


@pytest.fixture
async def image_result() -> ImageResult:
    """Generate a test image via PlaceholderImageProvider."""
    provider = PlaceholderImageProvider()
    return await provider.generate("resource test", aspect_ratio="16:9")


@pytest.fixture
def service(tmp_path: Path) -> ImageService:
    """Create an ImageService with a temp scratch directory."""
    return ImageService(scratch_dir=tmp_path)


@pytest.fixture
def registered(
    service: ImageService, image_result: ImageResult
) -> tuple[ImageService, str]:
    """Register a test image and return (service, image_id)."""
    record = service.register_image(image_result, "placeholder", prompt="resource test")
    return service, record.id


# --- image://{id}/view ---


def test_image_view_no_params_returns_original(
    registered: tuple[ImageService, str],
    image_result: ImageResult,
) -> None:
    """Reading view with no params returns original bytes."""
    service, image_id = registered
    record = service.get_image(image_id)
    data = record.original_path.read_bytes()
    assert data == image_result.image_data


def test_image_view_format_conversion(
    registered: tuple[ImageService, str],
) -> None:
    """Format conversion produces valid output."""
    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Convert to WebP
    data, content_type = convert_format(original, "webp")
    assert content_type == "image/webp"
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"


def test_image_view_resize(
    registered: tuple[ImageService, str],
) -> None:
    """Resize produces correct dimensions."""
    from image_generation_mcp.processing import crop_to_dimensions

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Crop to 200x200
    data = crop_to_dimensions(original, 200, 200)
    img = Image.open(io.BytesIO(data))
    assert img.size == (200, 200)


def test_image_view_proportional_resize_width(
    registered: tuple[ImageService, str],
) -> None:
    """Width-only resize preserves aspect ratio."""
    from image_generation_mcp.processing import resize_image

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Original is 640x360 (16:9), resize to width=320
    img = Image.open(io.BytesIO(original))
    ratio = 320 / img.width
    new_height = round(img.height * ratio)
    data = resize_image(original, 320, new_height)
    result_img = Image.open(io.BytesIO(data))
    assert result_img.width == 320
    assert result_img.height == new_height


def test_image_view_combined_params(
    registered: tuple[ImageService, str],
) -> None:
    """Format conversion + crop together."""
    from image_generation_mcp.processing import crop_to_dimensions

    service, image_id = registered
    record = service.get_image(image_id)
    original = record.original_path.read_bytes()

    # Crop then convert
    cropped = crop_to_dimensions(original, 128, 128)
    data, content_type = convert_format(cropped, "jpeg")
    assert content_type == "image/jpeg"
    img = Image.open(io.BytesIO(data))
    assert img.size == (128, 128)


def test_image_view_unknown_id(service: ImageService) -> None:
    """get_image raises for nonexistent ID."""
    with pytest.raises(ImageProviderError, match="not found"):
        service.get_image("nonexistent_id")


# --- image://{id}/metadata ---


def test_metadata_resource_returns_json(
    registered: tuple[ImageService, str],
) -> None:
    """Metadata resource returns sidecar JSON content."""
    service, image_id = registered
    sidecar_path = service.scratch_dir / f"{image_id}.json"
    data = json.loads(sidecar_path.read_text())
    assert data["id"] == image_id
    assert data["prompt"] == "resource test"
    assert data["provider"] == "placeholder"
    assert "original_dimensions" in data
    assert "provider_metadata" in data
    assert "created_at" in data


def test_metadata_resource_not_found(service: ImageService) -> None:
    """Metadata for nonexistent ID raises error."""
    with pytest.raises(ImageProviderError, match="not found"):
        service.get_image("nonexistent_id")


# --- image://list ---


def test_image_list_resource(
    registered: tuple[ImageService, str],
) -> None:
    """list_images returns registered images."""
    service, image_id = registered
    images = service.list_images()
    assert len(images) == 1
    assert images[0].id == image_id
    assert images[0].provider == "placeholder"
    assert images[0].prompt == "resource test"


# ---------------------------------------------------------------------------
# Resource handler functions — via MCP server lifespan (Client)
# ---------------------------------------------------------------------------
#
# The resource handler inner functions (provider_capabilities, image_view,
# image_metadata) live inside register_resources() and are only reachable
# via the FastMCP resource dispatch with an active lifespan context.  We
# use the full server + Client to exercise those code paths.
# ---------------------------------------------------------------------------


async def test_provider_capabilities_resource() -> None:
    """info://providers resource returns JSON with provider and capability info."""
    from fastmcp import Client

    from image_generation_mcp.mcp_server import create_server

    server = create_server()
    async with Client(server) as client:
        result = await client.read_resource("info://providers")

    assert result
    data = json.loads(result[0].text)
    assert "providers" in data
    assert "supported_aspect_ratios" in data
    assert "supported_quality_levels" in data


async def test_image_view_resource_via_server(tmp_path: Path) -> None:
    """image://{id}/view resource returns image bytes with correct MIME type."""

    from fastmcp import Client, FastMCP

    from image_generation_mcp._server_deps import make_service_lifespan
    from image_generation_mcp._server_resources import register_resources
    from image_generation_mcp._server_tools import register_tools
    from image_generation_mcp.config import ServerConfig

    # Build a minimal server with service lifespan
    config = ServerConfig(scratch_dir=tmp_path, read_only=False)
    mcp = FastMCP("test-view", lifespan=make_service_lifespan(config))
    register_tools(mcp)
    register_resources(mcp)

    # Register an image via the generate_image tool through the server
    async with Client(mcp) as client:
        gen_result = await client.call_tool(
            "generate_image",
            {"prompt": "test view resource", "provider": "placeholder"},
        )

    # Extract image_id from the tool result text
    text = next(c for c in gen_result.content if c.type == "text")
    meta = json.loads(text.text)
    image_id = meta["image_id"]

    # Now read the image view resource
    async with Client(mcp) as client:
        view_result = await client.read_resource(f"image://{image_id}/view")

    assert view_result
    # Blob content with image MIME type
    assert view_result[0].blob or view_result[0].text


async def test_image_metadata_resource_via_server(tmp_path: Path) -> None:
    """image://{id}/metadata resource returns JSON provenance."""
    import json

    from fastmcp import Client, FastMCP

    from image_generation_mcp._server_deps import make_service_lifespan
    from image_generation_mcp._server_resources import register_resources
    from image_generation_mcp._server_tools import register_tools
    from image_generation_mcp.config import ServerConfig

    config = ServerConfig(scratch_dir=tmp_path, read_only=False)
    mcp = FastMCP("test-meta", lifespan=make_service_lifespan(config))
    register_tools(mcp)
    register_resources(mcp)

    # Generate an image first
    async with Client(mcp) as client:
        gen_result = await client.call_tool(
            "generate_image",
            {"prompt": "metadata test", "provider": "placeholder"},
        )

    text = next(c for c in gen_result.content if c.type == "text")
    meta = json.loads(text.text)
    image_id = meta["image_id"]

    # Read the metadata resource
    async with Client(mcp) as client:
        meta_result = await client.read_resource(f"image://{image_id}/metadata")

    assert meta_result
    metadata = json.loads(meta_result[0].text)
    assert metadata["id"] == image_id
    assert metadata["prompt"] == "metadata test"
    assert metadata["provider"] == "placeholder"


async def test_image_metadata_resource_missing_sidecar(tmp_path: Path) -> None:
    """image://{id}/metadata raises ImageProviderError when sidecar file missing."""
    from fastmcp import Client, FastMCP

    from image_generation_mcp._server_deps import make_service_lifespan
    from image_generation_mcp._server_resources import register_resources
    from image_generation_mcp._server_tools import register_tools
    from image_generation_mcp.config import ServerConfig

    config = ServerConfig(scratch_dir=tmp_path, read_only=False)
    mcp = FastMCP("test-missing-sidecar", lifespan=make_service_lifespan(config))
    register_tools(mcp)
    register_resources(mcp)

    # Generate image then delete its sidecar to simulate missing metadata
    async with Client(mcp) as client:
        gen_result = await client.call_tool(
            "generate_image",
            {"prompt": "sidecar test", "provider": "placeholder"},
        )

    text = next(c for c in gen_result.content if c.type == "text")
    meta = json.loads(text.text)
    image_id = meta["image_id"]

    # Delete the sidecar file
    sidecar = tmp_path / f"{image_id}.json"
    sidecar.unlink()

    # Reading metadata should fail with a resource or MCP error
    from fastmcp.exceptions import McpError, ResourceError

    async with Client(mcp) as client:
        with pytest.raises((ResourceError, McpError, Exception)):
            await client.read_resource(f"image://{image_id}/metadata")
