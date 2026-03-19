"""Tests for surfacing provider capabilities in MCP tools, resources, and selector."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
)
from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.providers.selector import select_provider
from image_generation_mcp.service import ImageService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def scratch_dir(tmp_path: Path) -> Path:
    return tmp_path / "scratch"


def _make_caps(
    name: str,
    *,
    supports_background: bool = False,
    supports_negative_prompt: bool = False,
    degraded: bool = False,
) -> ProviderCapabilities:
    """Helper to create ProviderCapabilities with minimal boilerplate."""
    models = ()
    if not degraded:
        models = (
            ModelCapabilities(
                model_id=f"{name}-model",
                display_name=f"{name} Model",
                supports_background=supports_background,
                supports_negative_prompt=supports_negative_prompt,
            ),
        )
    return ProviderCapabilities(
        provider_name=name,
        models=models,
        supports_background=supports_background,
        supports_negative_prompt=supports_negative_prompt,
        discovered_at=1000.0,
        degraded=degraded,
    )


# -- list_providers tool: full capabilities ----------------------------------


class TestListProvidersFullCapabilities:
    """Verify enriched list_providers response with model details."""

    async def test_includes_model_details(self, scratch_dir: Path) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        svc.register_provider("placeholder", PlaceholderImageProvider())
        await svc.discover_all_capabilities()

        providers = svc.list_providers()
        caps = providers["placeholder"]["capabilities"]
        assert len(caps["models"]) == 1
        model = caps["models"][0]
        assert model["model_id"] == "placeholder"
        assert model["can_generate"] is True
        assert "1:1" in model["supported_aspect_ratios"]

    async def test_degraded_provider_marked(self, scratch_dir: Path) -> None:
        svc = ImageService(scratch_dir=scratch_dir)

        mock = AsyncMock()
        mock.discover_capabilities.side_effect = RuntimeError("API down")
        mock.generate = AsyncMock()
        svc.register_provider("broken", mock)
        await svc.discover_all_capabilities()

        providers = svc.list_providers()
        caps = providers["broken"]["capabilities"]
        assert caps["degraded"] is True
        assert caps["models"] == []


# -- info://providers resource: capability data -------------------------------


class TestInfoProvidersResource:
    """Verify JSON includes per-model capabilities."""

    async def test_resource_includes_capabilities(self, scratch_dir: Path) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        svc.register_provider("placeholder", PlaceholderImageProvider())
        await svc.discover_all_capabilities()

        providers = svc.list_providers()
        data = {
            "providers": providers,
            "supported_aspect_ratios": ("1:1", "16:9", "9:16", "3:2", "2:3"),
            "supported_quality_levels": ("standard", "hd"),
            "supported_backgrounds": ("opaque", "transparent"),
        }
        payload = json.loads(json.dumps(data))
        prov = payload["providers"]["placeholder"]
        assert "capabilities" in prov
        assert prov["capabilities"]["provider_name"] == "placeholder"
        assert len(prov["capabilities"]["models"]) == 1

    async def test_resource_includes_backgrounds(self) -> None:
        # Verify supported_backgrounds is part of the response shape
        from image_generation_mcp.providers.types import SUPPORTED_BACKGROUNDS

        assert "transparent" in SUPPORTED_BACKGROUNDS
        assert "opaque" in SUPPORTED_BACKGROUNDS


# -- Selector: capability-aware filtering ------------------------------------


class TestSelectorCapabilityFiltering:
    """Verify selector deprioritizes providers without required capability."""

    def test_deprioritizes_no_background(self) -> None:
        """Provider with supports_background=True preferred for transparent."""
        caps = {
            "openai": _make_caps("openai", supports_background=True),
            "a1111": _make_caps("a1111", supports_background=False),
        }
        # Default chain would pick openai anyway — test with a prompt
        # that normally prefers a1111 (photorealism)
        result = select_provider(
            "realistic photo portrait",
            {"openai", "a1111"},
            capabilities=caps,
            background="transparent",
        )
        assert result == "openai"

    def test_falls_back_when_no_capable_provider(self) -> None:
        """Falls back to keyword-based selection when no provider has capability."""
        caps = {
            "a1111": _make_caps("a1111", supports_background=False),
        }
        result = select_provider(
            "realistic photo",
            {"a1111"},
            capabilities=caps,
            background="transparent",
        )
        assert result == "a1111"  # only option, still selected

    def test_without_capabilities_unchanged(self) -> None:
        """Keyword heuristics work when capabilities=None."""
        result = select_provider(
            "a professional logo",
            {"openai", "a1111", "placeholder"},
            capabilities=None,
        )
        assert result == "openai"

    def test_opaque_background_no_filtering(self) -> None:
        """No capability filtering for opaque background (default)."""
        caps = {
            "openai": _make_caps("openai", supports_background=True),
            "a1111": _make_caps("a1111", supports_background=False),
        }
        # "realistic photo" normally prefers a1111
        result = select_provider(
            "realistic photo portrait",
            {"openai", "a1111"},
            capabilities=caps,
            background="opaque",
        )
        assert result == "a1111"


# -- Degraded provider warning on generate -----------------------------------


class TestDegradedProviderWarning:
    """Verify degraded provider logs warning during generation."""

    async def test_degraded_logs_warning(
        self, scratch_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        svc.register_provider("placeholder", PlaceholderImageProvider())

        # Manually set degraded capabilities
        from image_generation_mcp.providers.capabilities import make_degraded

        svc._capabilities["placeholder"] = make_degraded("placeholder", 1000.0)

        with caplog.at_level(logging.WARNING):
            await svc.generate("test", provider="placeholder")

        assert any("degraded" in r.message.lower() for r in caplog.records)

    async def test_non_degraded_no_warning(
        self, scratch_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        svc = ImageService(scratch_dir=scratch_dir)
        svc.register_provider("placeholder", PlaceholderImageProvider())
        await svc.discover_all_capabilities()

        with caplog.at_level(logging.WARNING):
            await svc.generate("test", provider="placeholder")

        assert not any("degraded" in r.message.lower() for r in caplog.records)
