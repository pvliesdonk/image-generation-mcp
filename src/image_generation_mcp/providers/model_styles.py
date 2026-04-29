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
        """Serialize to a JSON-compatible dictionary.

        The ``deprecation_note`` key is omitted entirely when
        ``self.deprecation_note is None``. All other fields are always
        present.
        """
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


MODEL_STYLES: dict[str, StyleProfile] = {
    # ----- OpenAI -----
    "openai:gpt-image-1.5": StyleProfile(
        label="OpenAI GPT Image 1.5",
        style_hints=(
            "Current OpenAI flagship image model. Strong instruction "
            "following for photorealistic shots, illustrations, product "
            "mockups, infographics, and marketing assets where layout and "
            "typography matter. Excels with descriptive paragraphs ordered "
            "scene → subject → details → constraints, and with text in image "
            "given in quotes with explicit typography hints. Supports "
            "transparent backgrounds and 1024x1024 / 1024x1536 / 1536x1024."
        ),
        incompatible_styles=(
            "Avoid CLIP-style comma-separated tag dumps — they underperform "
            "vs descriptive sentences. Don't use --no negative-prompt "
            "syntax; describe exclusions positively. Long, multi-element "
            "scenes with strict spatial composition can drift. Real-named-"
            "people likenesses are filtered. No identity consistency across "
            "calls."
        ),
        good_example=(
            "Editorial product photo of a beige ceramic coffee mug on a "
            "worn oak table, shallow depth of field, soft window light from "
            "the left, warm muted palette. No text, no logos."
        ),
        bad_example=(
            "coffee mug, masterpiece, 8k, hyperdetailed, --no text "
            "(tag-soup + unsupported negative-prompt syntax — wastes tokens, "
            "mostly ignored)"
        ),
    ),
    "openai:gpt-image-1": StyleProfile(
        label="OpenAI GPT Image 1 (legacy)",
        style_hints=(
            "Earlier flagship; same descriptive-paragraph prompt grammar as "
            "gpt-image-1.5. Supports transparent backgrounds and the same "
            "three aspect ratios. Still capable for general work; newer "
            "siblings give better fidelity and instruction following."
        ),
        incompatible_styles=(
            "Avoid CLIP-style tag dumps. No --no negative-prompt syntax. "
            "Real-named-people likenesses are filtered. Prefer "
            "gpt-image-1.5 for new long-lived workflows."
        ),
        good_example=(
            "Studio portrait of a senior watchmaker examining a movement "
            "with a loupe, warm rim light from a window, shallow depth of "
            "field, no text in frame."
        ),
        bad_example=(
            "watchmaker, masterpiece, 8k, ultradetailed (tag-soup style — "
            "use descriptive sentences instead)"
        ),
        lifecycle="legacy",
        deprecation_note=(
            "Newer OpenAI image models (gpt-image-1.5) offer better fidelity. "
            "This model remains available for compatibility."
        ),
    ),
    "openai:gpt-image-1-mini": StyleProfile(
        label="OpenAI GPT Image 1 Mini",
        style_hints=(
            "Cheaper variant of gpt-image-1 with similar capabilities at a "
            "lower per-image cost. Same descriptive-paragraph grammar; same "
            "three aspect ratios. Good default for high-volume drafts and "
            "iteration where small quality differences vs the full model are "
            "acceptable."
        ),
        incompatible_styles=(
            "Avoid CLIP-style tag dumps. No --no negative-prompt syntax. "
            "Same content filters as the full model. For final-grade output "
            "where small quality differences matter, prefer gpt-image-1.5."
        ),
        good_example=(
            "Quick draft sketch: a fox curled up on a windowsill at dusk, "
            "soft watercolour palette, simple background."
        ),
        bad_example=(
            "fox, watercolour, ((masterpiece)), [blurry] (parenthetical "
            "weight syntax is SD-specific; gpt-image-* ignores it)"
        ),
    ),
    "openai:dall-e-3": StyleProfile(
        label="OpenAI DALL-E 3 (deprecated)",
        style_hints=(
            "Strong creative interpretation and excellent compliance with "
            "multi-clause prompts. Good for stylised illustrations, "
            "cinematic concept art, and `vivid`-style hero images where you "
            "want the model to embellish. The `natural` style produces "
            "flatter, more photoreal output suitable for stock-photo and "
            "logo work."
        ),
        incompatible_styles=(
            "Don't use for in-image text — text rendering is unreliable. "
            "No edits, no inpainting, no transparent background, no "
            "negative prompts, no aspect ratios beyond 1024x1024 / "
            "1024x1792 / 1792x1024. Cannot render named real people. Will "
            "silently rewrite short prompts — inspect `revised_prompt` to "
            "see what was actually used."
        ),
        good_example=(
            "A wide cinematic painting in the style of Thomas Cole's "
            '"Desolation" — overgrown classical ruins on a cliff at dusk, '
            "vines reclaiming marble columns, single shaft of warm light. "
            "Style: natural."
        ),
        bad_example=(
            'A birthday cake that says "HAPPY BIRTHDAY SARAH" in elegant '
            "script (DALL-E 3 will likely garble the text; route to "
            "gpt-image-1.5 for typography-critical work)"
        ),
        lifecycle="deprecated",
        deprecation_note=(
            "OpenAI API removal scheduled 2026-05-12. Migrate to "
            "gpt-image-1.5 for new long-lived workflows."
        ),
    ),
    "openai:dall-e-2": StyleProfile(
        label="OpenAI DALL-E 2 (legacy)",
        style_hints=(
            "Older OpenAI model retained mostly for inpainting / mask "
            "edits at low cost. Limited style fidelity vs current "
            "gpt-image-* family. 1024x1024 only. Useful for cheap edits "
            "where new code paths can't be added."
        ),
        incompatible_styles=(
            "Don't use for new generation work. No transparent backgrounds, "
            "no aspect ratios beyond 1:1, no in-image text, no negative "
            "prompts. Quality is well below current OpenAI models."
        ),
        good_example=(
            "Inpaint a missing hand on an existing 1024x1024 image (mask "
            "edit only — not for new-from-scratch generation)"
        ),
        bad_example=(
            "Detailed photoreal product shot for a marketing campaign "
            "(use gpt-image-1.5 instead — DALL-E 2 quality is well behind)"
        ),
        lifecycle="legacy",
        deprecation_note=(
            "Use only for inpainting on legacy flows. Prefer gpt-image-1.5 "
            "for any new generation work."
        ),
    ),
    # ----- Gemini -----
    "gemini:gemini-2.5-flash-image": StyleProfile(
        label="Gemini 2.5 Flash Image (Nano Banana)",
        style_hints=(
            "Fast, low-latency generation and conversational image editing "
            "— multi-turn refinement, multi-image compositing (up to 3 "
            "inputs), character consistency across iterations, in-image "
            "text, and natural-language local edits ('remove the stain', "
            "'change pose to running'). Strong photorealism with "
            "photographic vocabulary (lens, lighting, aspect ratio). "
            "Supports 10 aspect ratios from 21:9 cinematic to 9:16 "
            "vertical. Cheap (~$0.04/image) — good default for high-volume "
            "ideation."
        ),
        incompatible_styles=(
            "Avoid Stable-Diffusion-style comma-separated tag lists — "
            "performance drops vs descriptive sentences. No negative-"
            "prompt parameter; phrase exclusions positively. Do not rely "
            "on transparent backgrounds. All outputs carry an invisible "
            "SynthID watermark — unsuitable for workflows requiring "
            "unmarked pixels. Not the strongest pick for very dense "
            "professional typography. Limit reference inputs to 3 images."
        ),
        good_example=(
            "A worn leather-bound journal lying open on a rainy windowsill "
            "at dusk. Soft cyan rim-light from outside, warm tungsten lamp "
            'on the right. The left page reads, in handwritten script: "Day '
            '42 — still no signal." Shot on 50mm, shallow depth of field. '
            "16:9."
        ),
        bad_example=(
            "journal, rainy, moody, cinematic, 8k, masterpiece, --no people "
            "(tags + unsupported negative — Google docs explicitly call this "
            "the wrong pattern)"
        ),
    ),
    "gemini:gemini-3.1-flash-image-preview": StyleProfile(
        label="Gemini 3.1 Flash Image (preview)",
        style_hints=(
            "Successor to 2.5 Flash with reasoning ('thinking') support. "
            "Good for prompts that benefit from layout reasoning — "
            "infographics, structured layouts, multi-element compositions "
            "where spatial relationships matter. Same descriptive-prose "
            "grammar as 2.5 Flash; same 10 aspect ratios."
        ),
        incompatible_styles=(
            "Avoid tag-soup; same SynthID-watermark caveat as 2.5 Flash. "
            "Preview-tier model — schema may shift before GA, surface text "
            "may not be perfectly stable. Don't pin production workflows "
            "to it without a fallback."
        ),
        good_example=(
            "A clean infographic explaining the water cycle on a soft "
            "pastel background, four labelled stages arranged in a circle, "
            "minimalist line illustration with gentle shadows. 4:3."
        ),
        bad_example=(
            "water cycle, infographic, 8k, ultra-detailed (tag style — use "
            "descriptive sentences for Gemini)"
        ),
    ),
    "gemini:gemini-3-pro-image-preview": StyleProfile(
        label="Gemini 3 Pro Image (preview)",
        style_hints=(
            "Higher-fidelity Pro tier with reasoning, suited to demanding "
            "production-grade work where 2.5 Flash falls short. Better at "
            "dense typography and strict brand compliance. Same prompt "
            "grammar as the Flash variants; preview-tier so behaviour can "
            "change."
        ),
        incompatible_styles=(
            "Don't use for cheap drafts — cost per image is materially "
            "higher than Flash. Same SynthID-watermark caveat. Tag-soup "
            "still underperforms. Preview-tier — surface stability not "
            "guaranteed."
        ),
        good_example=(
            "Magazine cover layout for a quarterly architecture journal: "
            "headline 'Concrete Futures' in bold serif, subhead "
            "'Brutalism Reconsidered', central full-bleed photo of a "
            "weathered Le Corbusier facade at golden hour. 3:4."
        ),
        bad_example=(
            "magazine, architecture, brutalism (single-line keyword set — "
            "Gemini Pro shines on richly described prompts; underprompting "
            "wastes the cost premium)"
        ),
    ),
    # ----- Placeholder -----
    "placeholder:placeholder": StyleProfile(
        label="Solid-color placeholder",
        style_hints=(
            "Returns a deterministic solid-color PNG at the requested "
            "aspect ratio. Use for testing pipeline plumbing, mocking "
            "generation in unit tests, or zero-cost demos without invoking "
            "a real provider."
        ),
        incompatible_styles=(
            "Not a real image generator. Do not use for any task that "
            "requires actual image content."
        ),
        good_example=(
            "any prompt — placeholder ignores prompt content and emits a "
            "solid-color PNG at the requested size"
        ),
        bad_example=(
            "any prompt where the user actually wants a generated image "
            "(use openai, gemini, or sd_webui instead)"
        ),
    ),
}

# Specific-before-generic. The empty-pattern entry MUST be last; it's the
# default fallback that guarantees resolve_style() returns non-None for any
# SD WebUI checkpoint.
CHECKPOINT_PATTERNS: tuple[tuple[re.Pattern[str], StyleProfile], ...] = (
    # re.compile(r"") matches every string; this entry always fires,
    # making the loop's "no match" branch unreachable in practice.
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
