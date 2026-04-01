"""Keyword-based provider selection with fallback chain.

Analyzes prompts to select the best image generation provider,
inspired by the claude-skills provider selector but simplified
for the current provider set (Gemini, OpenAI, SD WebUI, Placeholder).

Capabilities (when available) act as a secondary filter — providers
without a required capability are deprioritized but not excluded.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from image_generation_mcp.providers.types import ImageProviderError

if TYPE_CHECKING:
    from image_generation_mcp.providers.capabilities import ProviderCapabilities

logger = logging.getLogger(__name__)

# Keyword → preferred provider order
_SELECTION_RULES: list[tuple[list[str], list[str]]] = [
    # Photorealism — SD excels at this; Gemini as second cloud option
    (
        [
            "realistic",
            "photo",
            "photography",
            "headshot",
            "portrait photo",
            "product shot",
        ],
        ["sd_webui", "gemini", "openai"],
    ),
    # Text rendering / logos — OpenAI is best; Gemini as fallback
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
        ["openai", "gemini"],
    ),
    # Quick drafts / iteration — Gemini standard is fast and free
    (
        ["draft", "iterate", "iteration"],
        ["gemini", "openai"],
    ),
    # Explicit test / placeholder requests
    (
        ["quick", "test", "placeholder", "mock"],
        ["placeholder"],
    ),
    # Artistic / illustration — SD has great models; Gemini as second cloud
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
        ["sd_webui", "gemini", "openai"],
    ),
    # Anime / manga
    (
        ["anime", "manga", "kawaii", "chibi"],
        ["sd_webui", "gemini", "openai"],
    ),
]

# Default fallback chain — Gemini first (free tier), then OpenAI, then SD WebUI
_DEFAULT_CHAIN = ["gemini", "openai", "sd_webui", "placeholder"]


def select_provider(
    prompt: str,
    available_providers: set[str],
    *,
    capabilities: dict[str, ProviderCapabilities] | None = None,
    background: str = "opaque",
) -> str:
    """Select the best provider for a prompt based on keyword analysis.

    Keyword heuristics are the primary selection mechanism. When
    *capabilities* are available, they act as a secondary filter —
    providers without a required capability are deprioritized in the
    candidate list but not excluded entirely.

    Args:
        prompt: The image generation prompt.
        available_providers: Set of currently registered provider names.
        capabilities: Discovered capabilities per provider, if available.
        background: Requested background mode (used for capability filtering).

    Returns:
        Name of the selected provider.

    Raises:
        ImageProviderError: If no providers are available.
    """
    if not available_providers:
        raise ImageProviderError("auto", "No providers available")

    # Build a capability-filtered view: capable providers first, then the rest
    capable = available_providers
    if capabilities and background == "transparent":
        has_bg = {
            name
            for name in available_providers
            if name in capabilities and capabilities[name].supports_background
        }
        if has_bg:
            capable = has_bg
            logger.debug(
                "Capability filter: background=transparent → preferred providers: %s",
                capable,
            )

    prompt_lower = prompt.lower()

    # Check each rule — first match wins (prefer capable providers)
    for keywords, preferred in _SELECTION_RULES:
        if _matches_any(prompt_lower, keywords):
            # Try capable providers first, then fall back to all available
            for candidate_set in (capable, available_providers):
                for provider in preferred:
                    if provider in candidate_set:
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

    # No keyword matched — use default fallback chain (prefer capable)
    for candidate_set in (capable, available_providers):
        for provider in _DEFAULT_CHAIN:
            if provider in candidate_set:
                logger.debug("Provider selected by fallback chain: %s", provider)
                return provider

    # Last resort — return any available provider
    result = next(iter(available_providers))
    logger.debug("Provider selected as last resort: %s", result)
    return result


def _matches_any(text: str, keywords: list[str]) -> bool:
    """Check if text contains any of the keywords as whole words."""
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)
