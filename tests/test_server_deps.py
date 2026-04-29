"""Tests for _server_deps.py — provider initialization, lifespan, DI helpers.

Covers:
- get_service() raises when lifespan context missing
- get_config() raises when lifespan context missing
- make_service_lifespan registers OpenAI provider when openai_api_key is set
- make_service_lifespan registers SD WebUI provider when sd_webui_host is set
- make_service_lifespan registers placeholder always
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from image_generation_mcp._server_deps import (
    get_config,
    get_service,
    make_service_lifespan,
)
from image_generation_mcp.config import ProjectConfig
from image_generation_mcp.service import ImageService

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
        cfg = ProjectConfig()
        ctx = MagicMock()
        ctx.lifespan_context = {"config": cfg}
        result = get_config(ctx)
        assert result is cfg


# ---------------------------------------------------------------------------
# make_service_lifespan — provider registration
# ---------------------------------------------------------------------------


class TestMakeServiceLifespan:
    """Tests for make_service_lifespan() provider initialization logic."""

    async def _run_lifespan(self, config: ProjectConfig) -> ImageService:
        """Run lifespan as async context manager and return the service from context."""
        from fastmcp import FastMCP

        server = FastMCP("test-lifespan")
        lifespan_fn = make_service_lifespan(config)

        async with lifespan_fn(server) as ctx:
            return ctx["service"]

    async def test_placeholder_always_registered(self, tmp_path: Path) -> None:
        """Placeholder provider is always registered."""
        config = ProjectConfig(scratch_dir=tmp_path)
        service = await self._run_lifespan(config)
        assert service is not None
        assert "placeholder" in service.providers

    async def test_openai_not_registered_without_key(self, tmp_path: Path) -> None:
        """OpenAI provider is NOT registered when openai_api_key is None."""
        config = ProjectConfig(scratch_dir=tmp_path, openai_api_key=None)
        service = await self._run_lifespan(config)
        assert "openai" not in service.providers

    async def test_sd_webui_not_registered_without_host(self, tmp_path: Path) -> None:
        """SD WebUI provider is NOT registered when sd_webui_host is None."""
        config = ProjectConfig(scratch_dir=tmp_path, sd_webui_host=None)
        service = await self._run_lifespan(config)
        assert "sd_webui" not in service.providers


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

        config = ProjectConfig(scratch_dir=tmp_path, openai_api_key="sk-fake-key")
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


class TestMakeServiceLifespanSdWebuiRegistration:
    """Tests that SD WebUI provider registration path is exercised."""

    async def test_sd_webui_provider_registered(self, tmp_path: Path) -> None:
        """When sd_webui_host is set, 'sd_webui' appears in service.providers."""
        from fastmcp import FastMCP

        config = ProjectConfig(
            scratch_dir=tmp_path,
            sd_webui_host="http://localhost:7860",
            sd_webui_model="dreamshaper",
        )
        server = FastMCP("test-sd-webui")
        lifespan_fn = make_service_lifespan(config)

        # SdWebuiImageProvider is imported locally inside the lifespan function —
        # patch it where it lives in the sd_webui module.
        mock_provider = _make_mock_provider()

        with patch(
            "image_generation_mcp.providers.sd_webui.SdWebuiImageProvider",
            return_value=mock_provider,
        ):
            async with lifespan_fn(server) as ctx:
                service = ctx["service"]
                assert "sd_webui" in service.providers


class TestMakeServiceLifespanGeminiRegistration:
    """Tests that Gemini provider registration path is exercised."""

    async def test_gemini_provider_registered(self, tmp_path: Path) -> None:
        """When google_api_key is set, 'gemini' appears in service.providers."""
        from fastmcp import FastMCP

        config = ProjectConfig(scratch_dir=tmp_path, google_api_key="AIza-fake-key")
        server = FastMCP("test-gemini")
        lifespan_fn = make_service_lifespan(config)

        mock_provider = _make_mock_provider()

        with patch(
            "image_generation_mcp.providers.gemini.GeminiImageProvider",
            return_value=mock_provider,
        ):
            async with lifespan_fn(server) as ctx:
                service = ctx["service"]
                assert "gemini" in service.providers
