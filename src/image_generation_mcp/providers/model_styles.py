"""Per-model narrative metadata (style hints, lifecycle, examples).

The registry pairs a `(provider, model_id)` tuple with a :class:`StyleProfile`
that the LLM reads when choosing between models. See
``docs/design/2026-04-29-model-style-metadata.md`` for design rationale and
ADR-0009 for the architectural decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class StyleProfile:
    """Narrative metadata describing a model's strengths and prompt grammar.

    Attributes:
        label: Human-readable model identity.
        style_hints: Prose describing what the model is good at.
        incompatible_styles: Prose describing what fights the model.
        good_example: Short prompt fragment that plays to the model's strengths.
        bad_example: Short prompt fragment showing an anti-pattern.
        lifecycle: One of ``"current"``, ``"legacy"``, ``"deprecated"``.
        deprecation_note: Sentence explaining the deprecation when
            ``lifecycle != "current"``; ``None`` for current models.
    """

    label: str
    style_hints: str
    incompatible_styles: str
    good_example: str
    bad_example: str
    lifecycle: Literal["current", "legacy", "deprecated"] = "current"
    deprecation_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        result: dict[str, Any] = {
            "label": self.label,
            "style_hints": self.style_hints,
            "incompatible_styles": self.incompatible_styles,
            "good_example": self.good_example,
            "bad_example": self.bad_example,
            "lifecycle": self.lifecycle,
        }
        if self.deprecation_note is not None:
            result["deprecation_note"] = self.deprecation_note
        return result


MODEL_STYLES: dict[str, StyleProfile] = {}

# Specific-before-generic. The empty-pattern entry MUST be last; it's the
# default fallback that guarantees resolve_style() returns non-None for any
# SD WebUI checkpoint.
CHECKPOINT_PATTERNS: tuple[tuple[re.Pattern[str], StyleProfile], ...] = (
    (
        re.compile(r""),
        StyleProfile(
            label="Unknown checkpoint (SD general-purpose defaults)",
            style_hints=(
                "Stable Diffusion generally excels at stylised imagery, fantasy "
                "environments, and character portraiture. Use explicit style "
                "tokens (e.g. 'watercolor painting', 'cinematic photograph') "
                "for best results."
            ),
            incompatible_styles=(
                "Coherent embedded text and photographic product catalogs "
                "without specialised fine-tuning."
            ),
            good_example=(
                'style="painterly fantasy illustration with explicit style tokens", '
                'medium="digital concept art"'
            ),
            bad_example=(
                'style="coherent embedded text", '
                'medium="document scan with readable signage" '
                "(Stable Diffusion generally cannot render legible text)"
            ),
        ),
    ),
)


def resolve_style(provider: str, model_id: str) -> StyleProfile | None:
    """Return the :class:`StyleProfile` for a (provider, model_id) pair.

    Closed-list providers (``openai``, ``gemini``, ``placeholder``) use exact
    ``"{provider}:{model_id}"`` lookup against :data:`MODEL_STYLES`. ``sd_webui``
    falls back to the regex-ordered :data:`CHECKPOINT_PATTERNS` table; first
    match wins. Any other provider returns ``None`` — provider code keeps
    working unchanged.

    Args:
        provider: Provider registry key (e.g. ``"openai"``, ``"sd_webui"``).
        model_id: Model identifier as the provider exposes it.

    Returns:
        Matching :class:`StyleProfile`, or ``None`` when nothing matches.
    """
    if (hit := MODEL_STYLES.get(f"{provider}:{model_id}")) is not None:
        return hit
    if provider == "sd_webui":
        lowered = model_id.lower()
        for pattern, profile in CHECKPOINT_PATTERNS:
            if pattern.search(lowered):
                return profile
    return None
