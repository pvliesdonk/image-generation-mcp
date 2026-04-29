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
    "openai:gpt-image-2": StyleProfile(
        label="OpenAI GPT Image 2",
        style_hints=(
            "Current OpenAI flagship image model. Highest-fidelity "
            "instruction following in the family — best for demanding "
            "production work, dense in-image typography, complex multi-"
            "element compositions, and prompts that require strict "
            "adherence to layout / brand / scene direction. Same descriptive-"
            "paragraph prompt grammar as gpt-image-1.5; same three aspect "
            "ratios. Drops transparent-background support — use gpt-image-1.5 "
            "if you need transparency."
        ),
        incompatible_styles=(
            "Transparent backgrounds are not supported — pick gpt-image-1.5 "
            "for icons / stickers / logos that need alpha. Avoid CLIP-style "
            "tag dumps and `--no` negative-prompt syntax. Real-named-people "
            "likenesses are filtered. Cost per image is materially higher "
            "than gpt-image-1.5 / mini — pick those for drafts."
        ),
        good_example=(
            "Magazine cover layout with the headline 'Urban Foragers' set "
            "in a bold geometric serif, subhead 'A Field Guide to City "
            "Edibles', central full-bleed photo of a moss-covered tree "
            "stump in dappled afternoon light. 3:4."
        ),
        bad_example=(
            "magazine, foragers, bold serif (single-line keyword set — "
            "gpt-image-2 shines on richly described prompts; underprompting "
            "wastes the cost premium)"
        ),
    ),
    "openai:gpt-image-1.5": StyleProfile(
        label="OpenAI GPT Image 1.5",
        style_hints=(
            "Previous-generation OpenAI flagship; still the right pick when "
            "the work needs transparent backgrounds (gpt-image-2 dropped "
            "alpha support). Strong instruction following for photorealistic "
            "shots, illustrations, product mockups, infographics, and "
            "marketing assets where layout and typography matter. Excels "
            "with descriptive paragraphs ordered scene → subject → details "
            "→ constraints, and with text in image given in quotes with "
            "explicit typography hints. Supports 1024x1024 / 1024x1536 / "
            "1536x1024."
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
    # ----- FLUX.2 (must precede generic flux) -----
    (
        re.compile(r"flux[._-]?2"),
        StyleProfile(
            label="FLUX.2 (current photorealistic flagship)",
            style_hints=(
                "Newest BFL Flux generation. Photorealistic imagery with "
                "extreme fine detail; coherent in-scene text; strong "
                "architectural and product photography. Natural-language "
                "prose prompts; T5 encoder."
            ),
            incompatible_styles=(
                "FLUX.2 does not support negative prompts (CFG=1 distilled). "
                "Anime / cel-shaded / low-detail illustration styles fight "
                "the model. Don't use SD-style weighted parens or BREAK."
            ),
            good_example=(
                'style="cinematic urban photography", medium="digital '
                'photograph with shallow DOF"'
            ),
            bad_example=(
                'style="watercolor wash", medium="hand-painted ink" '
                "(FLUX.2 is tuned for photorealism; painterly media will "
                "fight the model)"
            ),
        ),
    ),
    # ----- Flux Schnell (must precede generic flux) -----
    (
        re.compile(r"flux.*schnell|schnell.*flux"),
        StyleProfile(
            label="Flux Schnell (1-4 step distilled)",
            style_hints=(
                "Distilled Flux variant for very fast drafts (1-4 steps, "
                "CFG=1). Same natural-language prompt style as Flux dev. "
                "Best for ideation passes where iteration speed dominates."
            ),
            incompatible_styles=(
                "No negative prompts (CFG=1, fully distilled). Quality "
                "below Flux dev / FLUX.2; don't use for final-grade "
                "output. Highly detailed textures suffer at 1-4 step "
                "counts."
            ),
            good_example=(
                'style="cinematic environment concept", medium="painterly '
                'digital art, broad strokes" (4 steps)'
            ),
            bad_example=(
                'style="hyperreal skin pores at 4K", medium="macro '
                'photograph" (Schnell sacrifices fine detail for speed)'
            ),
        ),
    ),
    # ----- Flux 1 dev/pro (NF4 quants share identity) -----
    (
        re.compile(r"flux"),
        StyleProfile(
            label="Flux 1 dev/pro (photorealistic / highly-detailed)",
            style_hints=(
                "Photorealistic imagery, extreme fine detail, architectural "
                "photography, natural lighting, product shots, documentary "
                "portraiture, coherent text in scene. Natural-language "
                "prose; T5 encoder; CFG=1 distilled."
            ),
            incompatible_styles=(
                "Negative prompts are unsupported (CFG=1 distilled). "
                "Anime / cel-shading / heavy painterly textures fight "
                "the model. Don't use SD-style weighted parens or BREAK."
            ),
            good_example=(
                'style="cinematic urban photography", medium="digital '
                'photograph with shallow DOF"'
            ),
            bad_example=(
                'style="watercolor wash", medium="hand-painted ink" '
                "(Flux is tuned for photorealism; painterly media will "
                "fight the model)"
            ),
        ),
    ),
    # ----- Pony Diffusion XL family -----
    (
        re.compile(r"pony|score_9|autismmix"),
        StyleProfile(
            label="Pony Diffusion XL (mandatory score_* tag prefix)",
            style_hints=(
                "Highly versatile SDXL fine-tune. Excellent for stylised "
                "character art, anime, and varied art styles when prompted "
                "with the mandatory leading tag block: 'score_9, "
                "score_8_up, score_7_up, score_6_up, score_5_up, "
                "score_4_up, source_anime, rating_safe' (or "
                "source_pony/source_furry, rating_questionable, etc.). "
                "Without the score_* prefix, output quality collapses."
            ),
            incompatible_styles=(
                "Bare prompts without the score_* prefix produce visibly "
                "degraded results. Photorealistic catalog work — Pony is "
                "stylised by design. Natural-language prose underperforms "
                "vs Booru-style tag grammar."
            ),
            good_example=(
                "score_9, score_8_up, score_7_up, score_6_up, "
                "source_anime, rating_safe, 1girl, school uniform, "
                "cherry blossoms, soft lighting"
            ),
            bad_example=(
                "1girl, anime, cherry blossoms (missing score_* prefix — "
                "output collapses)"
            ),
        ),
    ),
    # ----- Illustrious / NoobAI (must precede animagine) -----
    (
        re.compile(r"illustrious|noob.?ai"),
        StyleProfile(
            label="Illustrious-XL / NoobAI-XL (modern anime SDXL bases)",
            style_hints=(
                "Current-generation anime SDXL bases that have largely "
                "supplanted Animagine in 2025-26. Danbooru-style tag "
                "grammar (artist tags, character tags, e6/Danbooru-style). "
                "Much larger character/style dataset than Animagine 3.x. "
                "Strong cel-shading and expressive character art."
            ),
            incompatible_styles=(
                "Photorealism — anime-specialised. NoobAI v-prediction "
                "variants need the v-prediction sampler config; wrong "
                "sampler produces noise. Natural-language prose "
                "underperforms vs tag grammar."
            ),
            good_example=(
                "1girl, long hair, blue eyes, school uniform, cherry "
                "blossoms, masterpiece, best quality, very aesthetic"
            ),
            bad_example=(
                'style="documentary photograph", medium="35mm film" '
                "(Illustrious/NoobAI are anime-specialised; photographic "
                "styles produce off-distribution outputs)"
            ),
        ),
    ),
    # ----- Animagine XL -----
    (
        re.compile(r"animagine"),
        StyleProfile(
            label="Animagine XL (anime SDXL)",
            style_hints=(
                "Anime illustration base. Danbooru-style tag vocabulary, "
                "clean cel shading, expressive character art, vivid "
                "saturated palette, manga panel compositions. Animagine "
                "4.x recommends '1girl/1boy, character (series), rating, "
                "..., masterpiece, high score, great score, absurdres'."
            ),
            incompatible_styles=(
                "Photorealism, photography-style lighting, gritty texture, "
                "oil painting, detailed backgrounds without anime "
                "stylisation. For broader character/style coverage, "
                "consider Illustrious-XL or NoobAI-XL."
            ),
            good_example=(
                "1girl, long hair, school uniform, cherry blossoms, "
                "masterpiece, high score, absurdres"
            ),
            bad_example=(
                'style="documentary photograph", medium="35mm film" '
                "(Animagine is anime-specialised; photographic styles "
                "produce off-distribution outputs)"
            ),
        ),
    ),
    # ----- Coloring-book fine-tune (SD1.5 line-art) -----
    (
        re.compile(r"coloring.?book"),
        StyleProfile(
            label="Coloring Book (line-art SD1.5)",
            style_hints=(
                "Clean outlines on white background, no fill colors, "
                "strong linework, simple shapes, children's-book-friendly "
                "compositions, decorative borders."
            ),
            incompatible_styles=(
                "Photorealism, color renders, painterly textures, complex "
                "shading, dark backgrounds, photographic lighting."
            ),
            good_example=(
                'style="bold ink linework", medium="black-and-white outline drawing"'
            ),
            bad_example=(
                'style="photorealistic portrait", medium="oil paint with '
                'rich color" (this checkpoint is fine-tuned for line-art '
                "only; color renders will fail)"
            ),
        ),
    ),
    # ----- Juggernaut XL (tightened to exclude Illustrious-Juggernaut) -----
    (
        re.compile(r"juggernaut(?!.*illustrious)"),
        StyleProfile(
            label="Juggernaut XL (photorealistic SDXL)",
            style_hints=(
                "Photorealistic portraits, cinematic lighting, sharp "
                "textural detail, skin pores, fabric weave, dramatic rim "
                "lighting, environmental storytelling. Recent Juggernaut "
                "X / XI handle some stylised work too."
            ),
            incompatible_styles=(
                "Anime, cartoon, flat illustration. Watercolor and "
                "comic-ink styles are weaker than dedicated stylised "
                "checkpoints — usable but not the model's strength."
            ),
            good_example=(
                'style="gritty photorealistic urban", medium="digital photo"'
            ),
            bad_example=(
                'style="watercolor wash", medium="traditional ink" '
                "(Juggernaut is tuned for photorealism; stylised media "
                "will underperform)"
            ),
        ),
    ),
    # ----- DreamShaperXL Lightning / Alpha (must precede generic dreamshaperxl) -----
    (
        re.compile(r"dreamshaperxl.*lightning|dreamshaperxl.*alpha"),
        StyleProfile(
            label="DreamShaperXL Lightning / Alpha (fast fantasy SDXL)",
            style_hints=(
                "Fantasy concept art, painterly illustration, vibrant "
                "color, dramatic character portraits. Run at 3-6 steps "
                "with CFG ~2 and DPM++ SDE Karras (per Civitai). Fast "
                "ideation pass for stylised work."
            ),
            incompatible_styles=(
                "Photorealism (stylised by design), highly detailed "
                "textures at very low step counts, strict architectural "
                "accuracy."
            ),
            good_example=(
                'style="dramatic fantasy concept art", medium="painterly '
                'digital illustration"'
            ),
            bad_example=(
                'style="hyperrealistic skin detail at 4K", medium="macro '
                'photograph" (Lightning checkpoints sacrifice fine detail '
                "for speed)"
            ),
        ),
    ),
    # ----- DreamShaperXL standard -----
    (
        re.compile(r"dreamshaperxl|dreamshaper.*xl"),
        StyleProfile(
            label="DreamShaperXL (versatile fantasy SDXL)",
            style_hints=(
                "Fantasy illustration, painterly portraits, concept-art "
                "style, stylised environments, strong use of negative "
                "space."
            ),
            incompatible_styles=(
                "Strict photorealism, clinical document photography, "
                "flat-color infographic styles."
            ),
            good_example=(
                'style="painterly fantasy illustration", medium="digital concept art"'
            ),
            bad_example=(
                'style="clinical product photography", medium="catalog '
                'studio shot" (DreamShaperXL is stylised by design; '
                "strict photo-real fights the model)"
            ),
        ),
    ),
    # ----- DreamShaper SD1.5 (generic, must come after XL variants) -----
    (
        re.compile(r"dreamshaper"),
        StyleProfile(
            label="DreamShaper (versatile SD1.5)",
            style_hints=(
                "General-purpose stylised illustration, fantasy character "
                "art, soft painterly lighting, portrait and environmental "
                "compositions; notably versatile — adapt style tags rather "
                "than leaning on a single category."
            ),
            incompatible_styles=(
                "Extreme photorealism (slightly stylised by design), "
                "Danbooru/anime tag grammar (use natural descriptors)."
            ),
            good_example=(
                'style="painterly fantasy character portrait", medium="soft '
                'digital illustration"'
            ),
            bad_example=(
                'style="Danbooru anime tags", medium="cel-shading" '
                "(DreamShaper SD1.5 expects natural descriptors, not "
                "anime tag grammar)"
            ),
        ),
    ),
    # ----- SD 3 / 3.5 (T5-encoder; natural-language prose) -----
    (
        re.compile(r"sd3|sd_3|sd3_5|sd3\.5"),
        StyleProfile(
            label="SD 3 / 3.5 (triple-encoder; natural-language)",
            style_hints=(
                "Triple-encoder architecture (CLIP-L + OpenCLIP-bigG + "
                "T5-XXL). Benefits from natural-language prose for the T5 "
                "stream — same prose-friendly profile as Flux. Supports "
                "negative prompts (unlike Flux). 3.5 Large Turbo is 4-step "
                "distilled."
            ),
            incompatible_styles=(
                "CLIP tag-soup underperforms vs descriptive prose. "
                "Architecturally distinct from SDXL — don't expect SDXL "
                "fine-tune behaviour to carry over."
            ),
            good_example=(
                "A weathered fishing boat moored at a stone harbour at "
                "dawn, gulls circling overhead, soft cool light, painterly "
                "yet photoreal, 16:9 cinematic framing."
            ),
            bad_example=(
                "fishing boat, harbour, dawn, masterpiece, 8k, ((highly "
                "detailed)) (tag-soup with weighted parens — SD3 wants "
                "prose, parens are SDXL/SD1.5 syntax)"
            ),
        ),
    ),
    # ----- SDXL base -----
    (
        re.compile(r"sd_xl_base|sdxl_base|sdxl-base"),
        StyleProfile(
            label="SDXL Base (general-purpose SDXL)",
            style_hints=(
                "Broad style range, photography, illustration, concept art. "
                "Responds well to explicit style tokens. Works at 25-30+ "
                "steps for coherence."
            ),
            incompatible_styles=(
                "Anime-specific Danbooru vocabulary without style priming. "
                "Very low step counts (needs 25-30+ for coherence). The "
                "SDXL refiner is rarely used in 2026 workflows; modern "
                "fine-tunes drop it in favour of hires-fix / upscalers."
            ),
            good_example=(
                'style="cinematic illustration with explicit style tokens", '
                'medium="digital art"'
            ),
            bad_example=(
                'style="anime without style priming", medium="bare Danbooru '
                'tags" (SDXL base needs explicit style direction; bare '
                "anime grammar underperforms)"
            ),
        ),
    ),
    # ----- RealVisXL (current SDXL photoreal favourite) -----
    (
        re.compile(r"realvisxl|realvis"),
        StyleProfile(
            label="RealVisXL (photorealistic SDXL)",
            style_hints=(
                "Current-generation SDXL photorealism fine-tune. Sharp "
                "textural detail, skin/fabric/material fidelity, cinematic "
                "lighting. Has eclipsed Juggernaut share in 2026 SDXL "
                "photoreal work."
            ),
            incompatible_styles=(
                "Anime, cel-shading, watercolor, comic-ink. Painterly "
                "stylisation fights the photorealistic tuning."
            ),
            good_example=(
                'style="documentary photorealism", medium="digital photo, '
                'sharp focus, natural light"'
            ),
            bad_example=(
                'style="cel-shaded anime", medium="flat colour" (RealVisXL '
                "is photoreal-tuned; stylised media underperforms)"
            ),
        ),
    ),
    # ----- SD 1.5 base / pruned -----
    (
        re.compile(r"v1[-_]5|sd[-_]?1[-._]?5"),
        StyleProfile(
            label="SD 1.5 (general-purpose base)",
            style_hints=(
                "Broad style range. Native latent at 512px; commonly used "
                "at 512x768 / 768x512 before hires-fix. With hires-fix or "
                "upscaler chains routinely produces 1024x1536+. "
                "Well-supported by community LoRAs."
            ),
            incompatible_styles=(
                "Photorealistic skin detail at high resolution without "
                "hires-fix; SDXL-native aspect ratios. Don't expect "
                "SDXL-tier coherence at SDXL resolutions without "
                "upscaling."
            ),
            good_example='style="watercolor portraiture", medium="ink illustration"',
            bad_example=(
                'style="hyperrealistic skin at 1024px", medium="macro '
                'studio photograph" (SD 1.5 native latent is 512²; '
                "use SDXL or run hires-fix)"
            ),
        ),
    ),
    # ----- Default fallback — must remain last -----
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
