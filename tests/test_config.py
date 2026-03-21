"""Tests for ServerConfig — env var loading and defaults."""

from __future__ import annotations

import pytest

from image_generation_mcp.config import load_config


class TestServerConfig:
    def test_config_loads_cache_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config loads TRANSFORM_CACHE_SIZE from env."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE", "128")
        config = load_config()
        assert config.transform_cache_size == 128

    def test_config_default_cache_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config defaults to 64 when env not set."""
        monkeypatch.delenv("IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE", raising=False)
        config = load_config()
        assert config.transform_cache_size == 64

    def test_paid_providers_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default paid_providers includes openai."""
        monkeypatch.delenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", raising=False)
        config = load_config()
        assert config.paid_providers == frozenset({"openai"})

    def test_paid_providers_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PAID_PROVIDERS env var overrides default."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", "openai,a1111")
        config = load_config()
        assert config.paid_providers == frozenset({"openai", "a1111"})

    def test_paid_providers_empty_disables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty PAID_PROVIDERS disables confirmation."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", "")
        config = load_config()
        assert config.paid_providers == frozenset()
