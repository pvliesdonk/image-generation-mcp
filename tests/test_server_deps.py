"""Tests for _server_deps.py — provider initialization, lifespan, DI helpers.

Covers:
- _get_service_from_store() raises when service not initialised
- get_service() raises when lifespan context missing
- get_config() raises when lifespan context missing
- make_service_lifespan registers OpenAI provider when openai_api_key is set
- make_service_lifespan registers A1111 provider when a1111_host is set
- make_service_lifespan registers placeholder always
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

import image_generation_mcp._server_deps as deps_mod
from image_generation_mcp._server_deps import (
    _get_service_from_store,
    get_config,
    get_service,
    make_service_lifespan,
)
from image_generation_mcp.config import ServerConfig
from image_generation_mcp.service import ImageService

# ---------------------------------------------------------------------------
# _get_service_from_store
# ---------------------------------------------------------------------------


class TestGetServiceFromStore:
    """Tests for _get_service_from_store() module-level accessor."""

    def test_raises_when_not_initialised(self) -> None:
        """Raises RuntimeError if lifespan has not run."""
        # Ensure the store is None
        original = deps_mod._service_store
        deps_mod._service_store = None
        try:
            with pytest.raises(RuntimeError, match="lifespan has not run"):
                _get_service_from_store()
        finally:
            deps_mod._service_store = original

    def test_returns_service_when_set(self, tmp_path: Path) -> None:
        """Returns the stored service when set."""
        svc = ImageService(scratch_dir=tmp_path)
        original = deps_mod._service_store
        deps_mod._service_store = svc
        try:
            result = _get_service_from_store()
            assert result is svc
        finally:
            deps_mod._service_store = original


# ---------------------------------------------------------------------------
# get_service and get_config (DI helpers)
# ---------------------------------------------------------------------------


class TestGetService:
    """Tests for get_service() context resolver."""

    def test_raises_when_service_not_in_context(self) -> None:
        """Raises RuntimeError when lifespan context has no valid service."""
        ctx = MagicMock()
        ctx.lifespan_context = {}  # no "service" key
        with pytest.raises(RuntimeError, match="lifespan has not run"):
            get_service(ctx)

    def test_raises_when_service_wrong_type(self) -> None:
        """Raises RuntimeError when context has wrong type for 'service'."""
        ctx = MagicMock()
        ctx.lifespan_context = {"service": "not-a-service"}
        with pytest.raises(RuntimeError, match="lifespan has not run"):
            get_service(ctx)

    def test_returns_service_from_context(self, tmp_path: Path) -> None:
        """Returns service from lifespan context."""
        svc = ImageService(scratch_dir=tmp_path)
        ctx = MagicMock()
        ctx.lifespan_context = {"service": svc}
        result = get_service(ctx)
        assert result is svc


class TestGetConfig:
    """Tests for get_config() context resolver."""

    def test_raises_when_config_not_in_context(self) -> None:
        """Raises RuntimeError when lifespan context has no valid config."""
        ctx = MagicMock()
        ctx.lifespan_context = {}
        with pytest.raises(RuntimeError, match="lifespan has not run"):
            get_config(ctx)

    def test_raises_when_config_wrong_type(self) -> None:
        """Raises RuntimeError when context has wrong type for 'config'."""
        ctx = MagicMock()
        ctx.lifespan_context = {"config": "not-a-config"}
        with pytest.raises(RuntimeError, match="lifespan has not run"):
            get_config(ctx)

    def test_returns_config_from_context(self) -> None:
        """Returns config from lifespan context."""
        cfg = ServerConfig()
        ctx = MagicMock()
        ctx.lifespan_context = {"config": cfg}
        result = get_config(ctx)
        assert result is cfg


# ---------------------------------------------------------------------------
# make_service_lifespan — provider registration
# ---------------------------------------------------------------------------


class TestMakeServiceLifespan:
    """Tests for make_service_lifespan() provider initialization logic."""

    async def _run_lifespan(self, config: ServerConfig) -> ImageService:
        """Run lifespan as async context manager and return the service from context."""
        from fastmcp import FastMCP

        server = FastMCP("test-lifespan")
        lifespan_fn = make_service_lifespan(config)

        async with lifespan_fn(server) as ctx:
            return ctx["service"]

    async def test_placeholder_always_registered(self, tmp_path: Path) -> None:
        """Placeholder provider is always registered."""
        config = ServerConfig(scratch_dir=tmp_path)
        service = await self._run_lifespan(config)
        assert service is not None
        assert "placeholder" in service.providers

    async def test_openai_not_registered_without_key(self, tmp_path: Path) -> None:
        """OpenAI provider is NOT registered when openai_api_key is None."""
        config = ServerConfig(scratch_dir=tmp_path, openai_api_key=None)
        service = await self._run_lifespan(config)
        assert "openai" not in service.providers

    async def test_a1111_not_registered_without_host(self, tmp_path: Path) -> None:
        """A1111 provider is NOT registered when a1111_host is None."""
        config = ServerConfig(scratch_dir=tmp_path, a1111_host=None)
        service = await self._run_lifespan(config)
        assert "a1111" not in service.providers

    async def test_service_store_cleared_after_lifespan(self, tmp_path: Path) -> None:
        """Module-level _service_store is cleared to None after lifespan exits."""
        from fastmcp import FastMCP

        config = ServerConfig(scratch_dir=tmp_path)
        server = FastMCP("test-cleanup")
        lifespan_fn = make_service_lifespan(config)

        async with lifespan_fn(server):
            # Store should be set now
            assert deps_mod._service_store is not None

        # Store should be cleared after context exits
        assert deps_mod._service_store is None


def _make_mock_provider() -> MagicMock:
    """Build a mock provider compatible with ImageService.aclose()."""
    mock_provider = MagicMock()
    mock_provider.discover_capabilities = AsyncMock(
        return_value=MagicMock(models=[], degraded=False)
    )
    # aclose must be an AsyncMock so service.aclose() can await it
    mock_provider.aclose = AsyncMock()
    return mock_provider


class TestMakeServiceLifespanOpenAIRegistration:
    """Tests that OpenAI provider registration path is exercised."""

    async def test_openai_provider_registered(self, tmp_path: Path) -> None:
        """When openai_api_key is set, 'openai' appears in service.providers."""
        from fastmcp import FastMCP

        config = ServerConfig(scratch_dir=tmp_path, openai_api_key="sk-fake-key")
        server = FastMCP("test-openai")
        lifespan_fn = make_service_lifespan(config)

        # OpenAIImageProvider is imported locally inside the lifespan function —
        # patch it where it lives in the openai module.
        mock_provider = _make_mock_provider()

        with patch(
            "image_generation_mcp.providers.openai.OpenAIImageProvider",
            return_value=mock_provider,
        ):
            async with lifespan_fn(server) as ctx:
                service = ctx["service"]
                assert "openai" in service.providers


class TestMakeServiceLifespanA1111Registration:
    """Tests that A1111 provider registration path is exercised."""

    async def test_a1111_provider_registered(self, tmp_path: Path) -> None:
        """When a1111_host is set, 'a1111' appears in service.providers."""
        from fastmcp import FastMCP

        config = ServerConfig(
            scratch_dir=tmp_path,
            a1111_host="http://localhost:7860",
            a1111_model="dreamshaper",
        )
        server = FastMCP("test-a1111")
        lifespan_fn = make_service_lifespan(config)

        # A1111ImageProvider is imported locally inside the lifespan function —
        # patch it where it lives in the a1111 module.
        mock_provider = _make_mock_provider()

        with patch(
            "image_generation_mcp.providers.a1111.A1111ImageProvider",
            return_value=mock_provider,
        ):
            async with lifespan_fn(server) as ctx:
                service = ctx["service"]
                assert "a1111" in service.providers
