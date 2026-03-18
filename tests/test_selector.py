"""Tests for keyword-based provider selection."""

from __future__ import annotations

import pytest

from image_gen_mcp.providers.selector import select_provider
from image_gen_mcp.providers.types import ImageProviderError


class TestSelectProvider:
    """Tests for select_provider()."""

    def test_no_providers_raises(self) -> None:
        with pytest.raises(ImageProviderError, match="No providers available"):
            select_provider("a cat", set())

    # -- Keyword matching --------------------------------------------------

    def test_photorealism_prefers_a1111(self) -> None:
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "a1111"

    def test_photorealism_falls_back_to_openai(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "openai"

    def test_text_rendering_selects_openai(self) -> None:
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("logo with typography", available) == "openai"

    def test_placeholder_keywords(self) -> None:
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("quick test image", available) == "placeholder"

    def test_artistic_prefers_a1111(self) -> None:
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("watercolor painting of a sunset", available) == "a1111"

    def test_anime_prefers_a1111(self) -> None:
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("anime girl with sword", available) == "a1111"

    def test_anime_falls_back_to_openai(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("anime girl with sword", available) == "openai"

    # -- Default fallback chain --------------------------------------------

    def test_default_fallback_openai(self) -> None:
        """No keyword match → default chain starts with openai."""
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("a purple dinosaur", available) == "openai"

    def test_default_fallback_a1111(self) -> None:
        """No keyword match, no openai → fall back to a1111."""
        available = {"a1111", "placeholder"}
        assert select_provider("a purple dinosaur", available) == "a1111"

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
        available = {"openai", "a1111"}
        assert select_provider("REALISTIC PHOTO of a car", available) == "a1111"

    # -- Regression tests ----------------------------------------------------

    def test_professional_logo_selects_openai(self) -> None:
        """'professional' should not route logo prompts to a1111."""
        available = {"openai", "a1111", "placeholder"}
        assert select_provider("professional logo design", available) == "openai"

    def test_sign_no_false_positive(self) -> None:
        """'sign' (generic) should not match; 'signage' should."""
        available = {"openai", "a1111", "placeholder"}
        # "give me a sign" should fall to default chain
        assert select_provider("give me a sign", available) == "openai"
        # "signage" should match text-rendering rule
        assert select_provider("neon signage on brick wall", available) == "openai"

    # -- Word boundary matching --------------------------------------------

    def test_word_boundary_no_false_positive(self) -> None:
        """'art' should not match 'start' or 'party'."""
        available = {"openai", "a1111", "placeholder"}
        # "start the party" contains "art" substring but not as a word
        result = select_provider("start the party", available)
        # Should fall through to default chain, not match "art" rule
        assert result == "openai"
