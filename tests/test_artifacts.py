"""Tests for the ArtifactStore, create_download_link tool, and artifact endpoint.

Covers:
- ArtifactStore: create, consume, expire, double-consume
- create_download_link tool: valid URI, invalid image ID, missing BASE_URL
- Artifact HTTP handler: serve bytes, one-time use, expired 404
- Tool not registered on stdio transport
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient

from image_generation_mcp._server_tools import register_tools
from image_generation_mcp.artifacts import ArtifactStore, TokenRecord
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> ArtifactStore:
    """Fresh ArtifactStore for each test."""
    return ArtifactStore()


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
        PlaceholderImageProvider().generate("artifact test", aspect_ratio="1:1")
    )
    record = service.register_image(result, "placeholder", prompt="artifact test")
    return service, record.id


# ---------------------------------------------------------------------------
# ArtifactStore: create and consume
# ---------------------------------------------------------------------------


class TestArtifactStoreCreateConsume:
    """ArtifactStore basic create/consume contract."""

    def test_create_returns_hex_string(self, store: ArtifactStore) -> None:
        token = store.create_token("image://abc/view")
        assert isinstance(token, str)
        assert len(token) == 32  # uuid4().hex is 32 hex chars
        int(token, 16)  # raises if not valid hex

    def test_consume_returns_record(self, store: ArtifactStore) -> None:
        token = store.create_token("image://abc/view", ttl_seconds=60)
        record = store.consume_token(token)
        assert record is not None
        assert record.uri == "image://abc/view"
        assert record.ttl_seconds == 60

    def test_consume_removes_token(self, store: ArtifactStore) -> None:
        """Consuming a token makes it unavailable for a second attempt."""
        token = store.create_token("image://abc/view")
        store.consume_token(token)
        second = store.consume_token(token)
        assert second is None

    def test_unknown_token_returns_none(self, store: ArtifactStore) -> None:
        result = store.consume_token("deadbeef" * 4)
        assert result is None

    def test_create_stores_correct_uri(self, store: ArtifactStore) -> None:
        uri = "image://xyz123/view?format=webp&width=512"
        token = store.create_token(uri)
        record = store.consume_token(token)
        assert record is not None
        assert record.uri == uri


# ---------------------------------------------------------------------------
# ArtifactStore: expiry
# ---------------------------------------------------------------------------


class TestArtifactStoreExpiry:
    """Expired tokens return None from consume_token."""

    def test_expired_token_returns_none(self, store: ArtifactStore) -> None:
        token = store.create_token("image://abc/view", ttl_seconds=1)
        # Manually backdate the created_at to simulate expiry
        record = store._tokens[token]
        store._tokens[token] = TokenRecord(
            uri=record.uri,
            created_at=record.created_at - 10,  # 10 seconds in the past
            ttl_seconds=1,
        )
        result = store.consume_token(token)
        assert result is None

    def test_expired_token_is_removed_from_store(self, store: ArtifactStore) -> None:
        """consume_token removes the token even when expired."""
        token = store.create_token("image://abc/view", ttl_seconds=1)
        record = store._tokens[token]
        store._tokens[token] = TokenRecord(
            uri=record.uri,
            created_at=record.created_at - 10,
            ttl_seconds=1,
        )
        store.consume_token(token)
        # Token is gone from the store
        assert token not in store._tokens

    def test_cleanup_expired_on_create(self, store: ArtifactStore) -> None:
        """Creating a token cleans up already-expired tokens."""
        token = store.create_token("image://abc/view", ttl_seconds=1)
        # Expire it manually without consuming
        record = store._tokens[token]
        store._tokens[token] = TokenRecord(
            uri=record.uri,
            created_at=record.created_at - 10,
            ttl_seconds=1,
        )
        # Creating a new token triggers cleanup
        store.create_token("image://def/view")
        assert token not in store._tokens


# ---------------------------------------------------------------------------
# create_download_link tool: registration
# ---------------------------------------------------------------------------


class TestCreateDownloadLinkRegistration:
    """create_download_link is only registered for non-stdio transports."""

    async def test_not_registered_on_stdio(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp, transport="stdio")
        tool = await mcp.get_tool("create_download_link")
        assert tool is None

    async def test_registered_on_http(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

    async def test_registered_on_sse(self) -> None:
        mcp = FastMCP("test")
        register_tools(mcp, transport="sse")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None


# ---------------------------------------------------------------------------
# create_download_link tool: functional
# ---------------------------------------------------------------------------


class TestCreateDownloadLinkTool:
    """Functional tests for the create_download_link tool."""

    async def _call_tool(
        self,
        service: ImageService,
        image_id: str,
        uri_suffix: str = "",
        ttl_seconds: int = 300,
        base_url: str = "https://mcp.example.com",
    ) -> str:
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.artifacts import ArtifactStore, set_artifact_store
        from image_generation_mcp.config import ProjectConfig

        set_artifact_store(ArtifactStore())

        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

        config = ProjectConfig(server=ServerConfig(base_url=base_url))
        return await tool.fn(
            uri=f"image://{image_id}/view{uri_suffix}",
            ttl_seconds=ttl_seconds,
            service=service,
            config=config,
        )

    async def test_returns_json_with_download_url(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_tool(service, image_id)
        data = json.loads(result)
        assert "download_url" in data
        assert "expires_in_seconds" in data
        assert "uri" in data

    async def test_download_url_contains_base_url_and_token(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_tool(
            service, image_id, base_url="https://mcp.example.com"
        )
        data = json.loads(result)
        assert data["download_url"].startswith("https://mcp.example.com/artifacts/")

    async def test_expires_in_seconds_matches_ttl(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        result = await self._call_tool(service, image_id, ttl_seconds=120)
        data = json.loads(result)
        assert data["expires_in_seconds"] == 120

    async def test_uri_echoed_in_result(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        uri = f"image://{image_id}/view?format=webp"
        result = await self._call_tool(service, image_id, uri_suffix="?format=webp")
        data = json.loads(result)
        assert data["uri"] == uri

    async def test_raises_on_missing_base_url(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.artifacts import ArtifactStore, set_artifact_store
        from image_generation_mcp.config import ProjectConfig

        set_artifact_store(ArtifactStore())
        service, image_id = registered_image
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

        config = ProjectConfig(server=ServerConfig(base_url=None))
        with pytest.raises(ValueError, match="IMAGE_GENERATION_MCP_BASE_URL"):
            await tool.fn(
                uri=f"image://{image_id}/view",
                service=service,
                config=config,
            )

    async def test_raises_on_unknown_image_id(self, service: ImageService) -> None:
        """Tool must raise when the image_id is not in the registry."""
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.artifacts import ArtifactStore, set_artifact_store
        from image_generation_mcp.config import ProjectConfig

        set_artifact_store(ArtifactStore())
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

        from image_generation_mcp.providers.types import ImageProviderError

        config = ProjectConfig(server=ServerConfig(base_url="https://mcp.example.com"))
        with pytest.raises(ImageProviderError):
            await tool.fn(
                uri="image://nonexistent123/view",
                service=service,
                config=config,
            )

    async def test_raises_on_invalid_uri(self, service: ImageService) -> None:
        """Tool raises on a URI with no image_id."""
        from fastmcp_pvl_core import ServerConfig

        from image_generation_mcp.artifacts import ArtifactStore, set_artifact_store
        from image_generation_mcp.config import ProjectConfig

        set_artifact_store(ArtifactStore())
        mcp = FastMCP("test")
        register_tools(mcp, transport="http")
        tool = await mcp.get_tool("create_download_link")
        assert tool is not None

        config = ProjectConfig(server=ServerConfig(base_url="https://mcp.example.com"))
        with pytest.raises(ValueError, match="Invalid image URI"):
            await tool.fn(
                uri="notanuri",
                service=service,
                config=config,
            )


# ---------------------------------------------------------------------------
# Artifact HTTP endpoint handler
# ---------------------------------------------------------------------------


class TestArtifactHandler:
    """Tests for the GET /artifacts/{token} Starlette handler."""

    def _make_app_with_service(self, service: ImageService) -> TestClient:
        """Build a minimal Starlette app with the artifact endpoint."""
        from starlette.applications import Starlette
        from starlette.routing import Route

        # Patch module-level service store
        import image_generation_mcp._server_deps as deps_mod
        from image_generation_mcp.artifacts import (
            ArtifactStore,
            make_artifact_handler,
            set_artifact_store,
        )

        store = ArtifactStore()
        set_artifact_store(store)
        original_service = deps_mod._service_store
        deps_mod._service_store = service

        handler = make_artifact_handler()

        app = Starlette(
            routes=[Route("/artifacts/{token}", endpoint=handler, methods=["GET"])]
        )
        client = TestClient(app, raise_server_exceptions=False)

        # Store references for cleanup / token creation
        client._artifact_store = store  # type: ignore[attr-defined]
        client._original_service = original_service  # type: ignore[attr-defined]
        client._deps_mod = deps_mod  # type: ignore[attr-defined]
        return client

    def test_serves_image_bytes(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        token = store.create_token(f"image://{image_id}/view")
        response = client.get(f"/artifacts/{token}")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")
        assert len(response.content) > 0

    def test_one_time_use(self, registered_image: tuple[ImageService, str]) -> None:
        """Second request with same token returns 404."""
        service, image_id = registered_image
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        token = store.create_token(f"image://{image_id}/view")
        first = client.get(f"/artifacts/{token}")
        second = client.get(f"/artifacts/{token}")

        assert first.status_code == 200
        assert second.status_code == 404

    def test_unknown_token_returns_404(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, _image_id = registered_image
        client = self._make_app_with_service(service)

        response = client.get("/artifacts/deadbeef" * 2)
        assert response.status_code == 404

    def test_expired_token_returns_404(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        token = store.create_token(f"image://{image_id}/view", ttl_seconds=1)
        # Backdate the token to simulate expiry
        record = store._tokens[token]
        store._tokens[token] = TokenRecord(
            uri=record.uri,
            created_at=record.created_at - 10,
            ttl_seconds=1,
        )

        response = client.get(f"/artifacts/{token}")
        assert response.status_code == 404

    def test_content_type_matches_image_format(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        service, image_id = registered_image
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        # Placeholder generates PNG
        token = store.create_token(f"image://{image_id}/view")
        response = client.get(f"/artifacts/{token}")

        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]

    def test_image_not_in_registry_returns_404(self, service: ImageService) -> None:
        """Token for a non-existent image_id returns 404 via ImageProviderError."""
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        token = store.create_token("image://nonexistent999/view")
        response = client.get(f"/artifacts/{token}")

        assert response.status_code == 404

    def test_missing_image_file_returns_404(
        self, registered_image: tuple[ImageService, str]
    ) -> None:
        """Token valid but original file deleted from disk returns 404."""
        service, image_id = registered_image
        client = self._make_app_with_service(service)
        store: ArtifactStore = client._artifact_store  # type: ignore[attr-defined]

        # Delete the actual image file to trigger OSError
        record = service.get_image(image_id)
        record.original_path.unlink()

        token = store.create_token(f"image://{image_id}/view")
        response = client.get(f"/artifacts/{token}")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# make_server: artifact route mounted on HTTP but not stdio
# ---------------------------------------------------------------------------


class TestCreateServerArtifactRoute:
    """make_server mounts the artifact route for HTTP transport only."""

    def test_artifact_route_not_registered_for_stdio(self) -> None:
        from image_generation_mcp.server import make_server

        server = make_server(transport="stdio")
        routes = server._additional_http_routes
        paths = [getattr(r, "path", "") for r in routes]
        assert not any("/artifacts/" in p for p in paths)

    def test_artifact_route_registered_for_http(self) -> None:
        from image_generation_mcp.server import make_server

        server = make_server(transport="http")
        routes = server._additional_http_routes
        paths = [getattr(r, "path", "") for r in routes]
        assert any("/artifacts/" in p for p in paths)
