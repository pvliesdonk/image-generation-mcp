"""Tests for keyword-based provider selection."""

from __future__ import annotations

import pytest

from image_generation_mcp.providers.selector import select_provider
from image_generation_mcp.providers.types import ImageProviderError


class TestSelectProvider:
    """Tests for select_provider()."""

    def test_no_providers_raises(self) -> None:
        with pytest.raises(ImageProviderError, match="No providers available"):
            select_provider("a cat", set())

    # -- Keyword matching --------------------------------------------------

    def test_photorealism_prefers_sd_webui(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "sd_webui"

    def test_photorealism_falls_back_to_openai(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "openai"

    def test_text_rendering_selects_openai(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("logo with typography", available) == "openai"

    def test_placeholder_keywords(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("quick test image", available) == "placeholder"

    def test_draft_routes_to_gemini(self) -> None:
        """'draft' prompts route to gemini for fast iteration, not placeholder."""
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("draft of a landscape", available) == "gemini"

    def test_draft_falls_back_to_openai(self) -> None:
        """When gemini unavailable, drafts fall back to openai."""
        available = {"openai", "placeholder"}
        assert select_provider("draft of a landscape", available) == "openai"

    def test_artistic_prefers_sd_webui(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert (
            select_provider("watercolor painting of a sunset", available) == "sd_webui"
        )

    def test_anime_prefers_sd_webui(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("anime girl with sword", available) == "sd_webui"

    def test_anime_falls_back_to_openai(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("anime girl with sword", available) == "openai"

    # -- Default fallback chain --------------------------------------------

    def test_default_fallback_openai(self) -> None:
        """No keyword match → default chain starts with openai."""
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("a purple dinosaur", available) == "openai"

    def test_default_fallback_sd_webui(self) -> None:
        """No keyword match, no openai → fall back to sd_webui."""
        available = {"sd_webui", "placeholder"}
        assert select_provider("a purple dinosaur", available) == "sd_webui"

    def test_default_fallback_placeholder(self) -> None:
        """No keyword match, only placeholder → use placeholder."""
        available = {"placeholder"}
        assert select_provider("a purple dinosaur", available) == "placeholder"

    def test_last_resort_unknown_provider(self) -> None:
        """Unknown provider not in fallback chain → still returned as last resort."""
        available = {"custom_provider"}
        result = select_provider("a purple dinosaur", available)
        assert result == "custom_provider"

    # -- Case insensitivity ------------------------------------------------

    def test_case_insensitive_keywords(self) -> None:
        available = {"openai", "sd_webui"}
        assert select_provider("REALISTIC PHOTO of a car", available) == "sd_webui"

    # -- Regression tests ----------------------------------------------------

    def test_professional_logo_selects_openai(self) -> None:
        """'professional' should not route logo prompts to sd_webui."""
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("professional logo design", available) == "openai"

    def test_sign_no_false_positive(self) -> None:
        """'sign' (generic) should not match; 'signage' should."""
        available = {"openai", "sd_webui", "placeholder"}
        # "give me a sign" should fall to default chain
        assert select_provider("give me a sign", available) == "openai"
        # "signage" should match text-rendering rule
        assert select_provider("neon signage on brick wall", available) == "openai"

    # -- Gemini in selection chains ----------------------------------------

    def test_default_fallback_prefers_gemini_when_available(self) -> None:
        """No keyword match → default chain starts with gemini."""
        available = {"gemini", "openai", "sd_webui", "placeholder"}
        assert select_provider("a purple dinosaur", available) == "gemini"

    def test_photorealism_falls_back_to_gemini_before_openai(self) -> None:
        """When sd_webui unavailable, photorealism falls back to gemini."""
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "gemini"

    def test_text_rendering_falls_back_to_gemini_when_no_openai(self) -> None:
        """When openai unavailable, text rendering falls back to gemini."""
        available = {"gemini", "sd_webui", "placeholder"}
        assert select_provider("logo with typography", available) == "gemini"

    def test_artistic_falls_back_to_gemini_before_openai(self) -> None:
        """When sd_webui unavailable, art falls back to gemini."""
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("watercolor painting of a sunset", available) == "gemini"

    def test_anime_falls_back_to_gemini_before_openai(self) -> None:
        """When sd_webui unavailable, anime falls back to gemini."""
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("anime girl with sword", available) == "gemini"

    # -- Word boundary matching --------------------------------------------

    def test_word_boundary_no_false_positive(self) -> None:
        """'art' should not match 'start' or 'party'."""
        available = {"openai", "sd_webui", "placeholder"}
        # "start the party" contains "art" substring but not as a word
        result = select_provider("start the party", available)
        # Should fall through to default chain, not match "art" rule
        assert result == "openai"
