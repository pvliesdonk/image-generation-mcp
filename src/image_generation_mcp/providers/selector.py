"""Keyword-based provider selection with fallback chain.

Analyzes prompts to select the best image generation provider,
inspired by the claude-skills provider selector but simplified
for the current provider set (OpenAI, A1111, Placeholder).
"""

from __future__ import annotations

import logging
import re

from image_generation_mcp.providers.types import ImageProviderError

logger = logging.getLogger(__name__)

# Keyword → preferred provider order
_SELECTION_RULES: list[tuple[list[str], list[str]]] = [
    # Photorealism — SD excels at this
    (
        [
            "realistic",
            "photo",
            "photography",
            "headshot",
            "portrait photo",
            "product shot",
        ],
        ["a1111", "openai"],
    ),
    # Text rendering / logos — OpenAI is best
    (
        [
            "text",
            "logo",
            "typography",
            "poster",
            "banner",
            "signage",
            "lettering",
            "font",
        ],
        ["openai"],
    ),
    # Quick draft / testing
    (
        ["quick", "draft", "test", "placeholder", "mock"],
        ["placeholder"],
    ),
    # Artistic / illustration — SD has great models for this
    (
        [
            "art",
            "painting",
            "illustration",
            "watercolor",
            "oil painting",
            "sketch",
            "drawing",
        ],
        ["a1111", "openai"],
    ),
    # Anime / manga
    (
        ["anime", "manga", "kawaii", "chibi"],
        ["a1111", "openai"],
    ),
]

# Default fallback chain when no keywords match
_DEFAULT_CHAIN = ["openai", "a1111", "placeholder"]


def select_provider(
    prompt: str,
    available_providers: set[str],
) -> str:
    """Select the best provider for a prompt based on keyword analysis.

    Args:
        prompt: The image generation prompt.
        available_providers: Set of currently registered provider names.

    Returns:
        Name of the selected provider.

    Raises:
        ImageProviderError: If no providers are available.
    """
    if not available_providers:
        raise ImageProviderError("auto", "No providers available")

    prompt_lower = prompt.lower()

    # Check each rule — first match wins
    for keywords, preferred in _SELECTION_RULES:
        if _matches_any(prompt_lower, keywords):
            for provider in preferred:
                if provider in available_providers:
                    matched_kw = next(
                        kw
                        for kw in keywords
                        if re.search(r"\b" + re.escape(kw) + r"\b", prompt_lower)
                    )
                    logger.debug(
                        "Provider selected by keyword: %s (matched: %s)",
                        provider,
                        matched_kw,
                    )
                    return provider

    # No keyword matched — use default fallback chain
    for provider in _DEFAULT_CHAIN:
        if provider in available_providers:
            logger.debug("Provider selected by fallback chain: %s", provider)
            return provider

    # Last resort — return any available provider
    result = next(iter(available_providers))
    logger.debug("Provider selected as last resort: %s", result)
    return result


def _matches_any(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords as whole words."""
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)
