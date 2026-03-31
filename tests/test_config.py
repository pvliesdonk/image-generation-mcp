"""Tests for config.py — env var loading edge cases.

Covers:
- load_config() with various env var combinations
- scratch dir default and custom path
- openai_api_key, sd_webui_host, sd_webui_model, default_provider branches
- TRANSFORM_CACHE_SIZE invalid value logs warning and uses default
- paid_providers comma-separated parsing
- read_only env var branch
- deprecated A1111_HOST / A1111_MODEL env var fallback
- deprecated DEFAULT_PROVIDER="a1111" alias mapping
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from image_generation_mcp.config import (
    _DEFAULT_SCRATCH_DIR,
    _parse_bool,
    load_config,
)


class TestParseBool:
    """Tests for _parse_bool helper."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "YES"])
    def test_truthy_values(self, value: str) -> None:
        assert _parse_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "", "anything"])
    def test_falsy_values(self, value: str) -> None:
        assert _parse_bool(value) is False


class TestLoadConfigDefaults:
    """load_config() with no env vars uses ServerConfig defaults."""

    def test_read_only_default(self) -> None:
        config = load_config()
        assert config.read_only is True

    def test_scratch_dir_default(self) -> None:
        config = load_config()
        assert config.scratch_dir == _DEFAULT_SCRATCH_DIR

    def test_openai_api_key_default_none(self) -> None:
        config = load_config()
        assert config.openai_api_key is None

    def test_sd_webui_host_default_none(self) -> None:
        config = load_config()
        assert config.sd_webui_host is None

    def test_default_provider_default_auto(self) -> None:
        config = load_config()
        assert config.default_provider == "auto"

    def test_transform_cache_size_default(self) -> None:
        config = load_config()
        assert config.transform_cache_size == 64

    def test_paid_providers_default(self) -> None:
        config = load_config()
        assert config.paid_providers == frozenset({"openai"})


class TestLoadConfigEnvVars:
    """load_config() reads env vars correctly."""

    def test_read_only_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        config = load_config()
        assert config.read_only is False

    def test_scratch_dir_custom(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SCRATCH_DIR", str(tmp_path))
        config = load_config()
        assert config.scratch_dir == tmp_path

    def test_openai_api_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_OPENAI_API_KEY", "sk-test-key")
        config = load_config()
        assert config.openai_api_key == "sk-test-key"

    def test_google_api_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_GOOGLE_API_KEY", "AIza-test")
        config = load_config()
        assert config.google_api_key == "AIza-test"

    def test_google_api_key_unset(self) -> None:
        config = load_config()
        assert config.google_api_key is None

    def test_sd_webui_host_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "IMAGE_GENERATION_MCP_SD_WEBUI_HOST", "http://localhost:7860"
        )
        config = load_config()
        assert config.sd_webui_host == "http://localhost:7860"

    def test_sd_webui_model_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SD_WEBUI_MODEL", "dreamshaper_xl")
        config = load_config()
        assert config.sd_webui_model == "dreamshaper_xl"

    def test_default_provider_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_DEFAULT_PROVIDER", "placeholder")
        config = load_config()
        assert config.default_provider == "placeholder"

    def test_transform_cache_size_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE", "128")
        config = load_config()
        assert config.transform_cache_size == 128

    def test_transform_cache_size_invalid_uses_default(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE", "not-a-number")
        with caplog.at_level(logging.WARNING):
            config = load_config()
        assert config.transform_cache_size == 64
        assert "Invalid TRANSFORM_CACHE_SIZE" in caplog.text

    def test_base_url_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_BASE_URL", "https://mcp.example.com/")
        config = load_config()
        # trailing slash is stripped
        assert config.base_url == "https://mcp.example.com"

    def test_paid_providers_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", "openai,sd_webui")
        config = load_config()
        assert config.paid_providers == frozenset({"openai", "sd_webui"})

    def test_paid_providers_empty_clears(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", "")
        config = load_config()
        assert config.paid_providers == frozenset()

    def test_paid_providers_with_spaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IMAGE_GENERATION_MCP_PAID_PROVIDERS", " openai , sd_webui ")
        config = load_config()
        assert "openai" in config.paid_providers
        assert "sd_webui" in config.paid_providers

    def test_all_vars_together(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """All env vars set together produce correct config."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SCRATCH_DIR", str(tmp_path))
        monkeypatch.setenv("IMAGE_GENERATION_MCP_OPENAI_API_KEY", "sk-key")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SD_WEBUI_HOST", "http://sdwebui:7860")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SD_WEBUI_MODEL", "checkpoint_v1")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_DEFAULT_PROVIDER", "openai")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE", "32")
        config = load_config()
        assert config.read_only is False
        assert config.scratch_dir == tmp_path
        assert config.openai_api_key == "sk-key"
        assert config.sd_webui_host == "http://sdwebui:7860"
        assert config.sd_webui_model == "checkpoint_v1"
        assert config.default_provider == "openai"
        assert config.transform_cache_size == 32


class TestLoadConfigDeprecatedEnvVars:
    """load_config() accepts deprecated A1111_* env vars with a warning."""

    def test_a1111_host_sets_sd_webui_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deprecated IMAGE_GENERATION_MCP_A1111_HOST maps to sd_webui_host."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_HOST", "http://host:7860")
        config = load_config()
        assert config.sd_webui_host == "http://host:7860"

    def test_a1111_host_deprecated_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Setting A1111_HOST logs a deprecation warning."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_HOST", "http://host:7860")
        with caplog.at_level(logging.WARNING):
            load_config()
        assert "A1111_HOST" in caplog.text
        assert "deprecated" in caplog.text.lower()

    def test_sd_webui_host_takes_precedence_over_a1111_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both SD_WEBUI_HOST and A1111_HOST are set, new name wins."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SD_WEBUI_HOST", "http://new-host:7860")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_HOST", "http://old-host:7860")
        config = load_config()
        assert config.sd_webui_host == "http://new-host:7860"

    def test_a1111_model_sets_sd_webui_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deprecated IMAGE_GENERATION_MCP_A1111_MODEL maps to sd_webui_model."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_MODEL", "dreamshaper_8")
        config = load_config()
        assert config.sd_webui_model == "dreamshaper_8"

    def test_a1111_model_deprecated_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Setting A1111_MODEL logs a deprecation warning."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_MODEL", "dreamshaper_8")
        with caplog.at_level(logging.WARNING):
            load_config()
        assert "A1111_MODEL" in caplog.text
        assert "deprecated" in caplog.text.lower()

    def test_sd_webui_model_takes_precedence_over_a1111_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both SD_WEBUI_MODEL and A1111_MODEL are set, new name wins."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_SD_WEBUI_MODEL", "new_model")
        monkeypatch.setenv("IMAGE_GENERATION_MCP_A1111_MODEL", "old_model")
        config = load_config()
        assert config.sd_webui_model == "new_model"

    def test_default_provider_a1111_maps_to_sd_webui(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deprecated DEFAULT_PROVIDER="a1111" is remapped to "sd_webui"."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_DEFAULT_PROVIDER", "a1111")
        config = load_config()
        assert config.default_provider == "sd_webui"

    def test_default_provider_a1111_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Setting DEFAULT_PROVIDER=a1111 logs a deprecation warning."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_DEFAULT_PROVIDER", "a1111")
        with caplog.at_level(logging.WARNING):
            load_config()
        assert "deprecated" in caplog.text.lower()
