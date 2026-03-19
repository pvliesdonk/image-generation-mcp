"""Tests for MCP prompt registrations."""

from __future__ import annotations

from image_generation_mcp._server_prompts import (
    _SD_PROMPT_GUIDE,
    _SELECT_PROVIDER_PROMPT,
)


class TestPromptContent:
    """Verify prompt strings contain expected guidance."""

    def test_select_provider_mentions_all_providers(self) -> None:
        for provider in ("OpenAI", "A1111", "Placeholder"):
            assert provider in _SELECT_PROVIDER_PROMPT

    def test_select_provider_mentions_auto(self) -> None:
        assert "auto" in _SELECT_PROVIDER_PROMPT

    def test_sd_prompt_guide_mentions_clip(self) -> None:
        assert "CLIP" in _SD_PROMPT_GUIDE

    def test_sd_prompt_guide_mentions_break(self) -> None:
        assert "BREAK" in _SD_PROMPT_GUIDE

    def test_sd_prompt_guide_mentions_negative_prompt(self) -> None:
        assert "negative prompt" in _SD_PROMPT_GUIDE.lower()

    def test_sd_prompt_guide_mentions_aspect_ratios(self) -> None:
        for ratio in ("1:1", "16:9", "9:16"):
            assert ratio in _SD_PROMPT_GUIDE
