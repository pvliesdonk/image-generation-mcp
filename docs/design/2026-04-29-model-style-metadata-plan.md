# Per-model style metadata implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface per-model narrative guidance (`style_hints`, `incompatible_styles`, good/bad examples, `lifecycle`) and structured deprecation warnings on `list_providers`, plus a generated docs/providers/model-catalog.md page with CI drift-guard.

**Architecture:** New `providers/model_styles.py` registry — exact-key dict for closed-list providers (OpenAI, Gemini, placeholder), regex-ordered tuple for SD WebUI checkpoints. Each provider's `discover_capabilities()` calls `resolve_style(provider, model_id)` and populates a new `style_profile` field on `ModelCapabilities`. The `list_providers` MCP tool surfaces the field (and a top-level `warnings` array auto-built from `lifecycle`) without any new tool / resource. A render script publishes the registry as a documentation page; a CI step fails if anyone edits the registry without regenerating.

**Tech Stack:** Python 3.11+, `re`, `dataclasses`, FastMCP, pytest, mkdocs-material, ruff, mypy.

**Spec:** `docs/design/2026-04-29-model-style-metadata.md`.
**Tracking issue:** [#203](https://github.com/pvliesdonk/image-generation-mcp/issues/203).
**Branch:** `feat/model-style-metadata` (already created).

---

## File structure

**Create:**
- `src/image_generation_mcp/providers/model_styles.py` — `StyleProfile` dataclass, `MODEL_STYLES` dict, `CHECKPOINT_PATTERNS` tuple, `resolve_style()` resolver. ~250 lines.
- `scripts/render_model_catalog.py` — imports the registry, writes `docs/providers/model-catalog.md`. ~120 lines.
- `docs/providers/model-catalog.md` — generated catalog page (committed; CI guards against drift).
- `docs/decisions/0009-model-style-metadata.md` — ADR for exact-key + regex-fallback choice.
- `tests/test_model_styles.py` — unit tests for `StyleProfile`, `resolve_style`, pattern-ordering invariants.
- `tests/test_render_model_catalog.py` — smoke test for the render script + drift-detection fixture.

**Modify:**
- `src/image_generation_mcp/providers/capabilities.py` — add `style_profile: StyleProfile | None = None` to `ModelCapabilities`; update `to_dict()`.
- `src/image_generation_mcp/providers/openai.py` — call `resolve_style` in `discover_capabilities` for each `model_caps.append(...)`.
- `src/image_generation_mcp/providers/gemini.py` — same.
- `src/image_generation_mcp/providers/sd_webui.py` — same; add `sd3` branch in `_detect_architecture` + `_SD3_PRESET`.
- `src/image_generation_mcp/providers/placeholder.py` — same.
- `src/image_generation_mcp/_server_tools.py` — extend `generate_image` docstring; build top-level `warnings` array in `list_providers`.
- `mkdocs.yml` — add `Model Catalog` to nav under Providers.
- `.github/workflows/docs.yml` — drift-guard step (run renderer, `git diff --exit-code`).
- `.pre-commit-config.yaml` — local hook that re-runs the renderer when the registry changes.
- `docs/tools.md` — document new `style_profile` field and `warnings` array on `list_providers`.
- `docs/resources.md` — same for `info://providers`.
- `docs/providers/index.md` — link to the catalog.
- `docs/guides/prompt-writing.md` — one-line pointer to the catalog.
- `tests/test_capabilities.py` — round-trip `to_dict()` for the new field.
- `tests/test_sd_webui_provider.py` — assert SD3 detection + style_profile populated.
- `tests/test_openai_discovery.py`, `tests/test_gemini_discovery.py` — assert `style_profile` populated.
- `tests/test_tools.py` — assert `warnings` array shape and content.

---

## Task 1: `StyleProfile` dataclass + `ModelCapabilities.style_profile` field

**Files:**
- Create: `src/image_generation_mcp/providers/model_styles.py`
- Modify: `src/image_generation_mcp/providers/capabilities.py`
- Test: `tests/test_model_styles.py`, `tests/test_capabilities.py`

- [ ] **Step 1: Write failing tests for `StyleProfile.to_dict`**

Create `tests/test_model_styles.py`:

```python
"""Tests for the model_styles registry — schema, resolver, ordering."""

from __future__ import annotations

import pytest

from image_generation_mcp.providers.model_styles import StyleProfile


def test_style_profile_to_dict_omits_deprecation_note_when_none():
    profile = StyleProfile(
        label="Test",
        style_hints="hints",
        incompatible_styles="bad",
        good_example="good",
        bad_example="bad",
    )
    result = profile.to_dict()
    assert "deprecation_note" not in result
    assert result["lifecycle"] == "current"
    assert result["label"] == "Test"


def test_style_profile_to_dict_includes_deprecation_note():
    profile = StyleProfile(
        label="Old",
        style_hints="h",
        incompatible_styles="b",
        good_example="g",
        bad_example="bx",
        lifecycle="deprecated",
        deprecation_note="API removal 2026-05-12.",
    )
    result = profile.to_dict()
    assert result["deprecation_note"] == "API removal 2026-05-12."
    assert result["lifecycle"] == "deprecated"


def test_style_profile_is_frozen():
    profile = StyleProfile(
        label="x", style_hints="x", incompatible_styles="x",
        good_example="x", bad_example="x",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        profile.label = "y"  # type: ignore[misc]
```

Append to `tests/test_capabilities.py`:

```python
from image_generation_mcp.providers.model_styles import StyleProfile


def test_model_capabilities_to_dict_omits_style_profile_when_none():
    caps = ModelCapabilities(model_id="x", display_name="X")
    result = caps.to_dict()
    assert "style_profile" not in result


def test_model_capabilities_to_dict_includes_style_profile_when_set():
    profile = StyleProfile(
        label="L", style_hints="s", incompatible_styles="i",
        good_example="g", bad_example="b",
    )
    caps = ModelCapabilities(
        model_id="x", display_name="X", style_profile=profile,
    )
    result = caps.to_dict()
    assert result["style_profile"]["label"] == "L"
    assert result["style_profile"]["lifecycle"] == "current"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_styles.py tests/test_capabilities.py -x -v
```

Expected: ImportError on `image_generation_mcp.providers.model_styles` — module does not exist yet.

- [ ] **Step 3: Create `model_styles.py` with `StyleProfile` only**

Create `src/image_generation_mcp/providers/model_styles.py`:

```python
"""Per-model narrative metadata (style hints, lifecycle, examples).

The registry pairs a `(provider, model_id)` tuple with a :class:`StyleProfile`
that the LLM reads when choosing between models. See
``docs/design/2026-04-29-model-style-metadata.md`` for design rationale and
ADR-0009 for the architectural decision.
"""

from __future__ import annotations

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
```

- [ ] **Step 4: Extend `ModelCapabilities` in `capabilities.py`**

Edit `src/image_generation_mcp/providers/capabilities.py`. At the top, add the import:

```python
from image_generation_mcp.providers.model_styles import StyleProfile
```

Add the new field at the end of the `ModelCapabilities` dataclass (after `prompt_style`):

```python
    style_profile: StyleProfile | None = None
```

Extend the docstring `Attributes:` section with:

```
    style_profile: Optional narrative metadata (label, hints,
        incompatibility notes, examples, lifecycle) read by LLMs when
        selecting a model. ``None`` when no profile is registered for
        this model.
```

In `to_dict()`, after the existing keys but before `return result`, add:

```python
        if self.style_profile is not None:
            result["style_profile"] = self.style_profile.to_dict()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_styles.py tests/test_capabilities.py -x -v
```

Expected: PASS for the five new tests + all existing capability tests still PASS.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run ruff format --check src tests && uv run mypy src/
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/image_generation_mcp/providers/model_styles.py \
        src/image_generation_mcp/providers/capabilities.py \
        tests/test_model_styles.py tests/test_capabilities.py
git commit -m "feat(providers): add StyleProfile dataclass + style_profile field on ModelCapabilities

Foundation for per-model narrative metadata. ModelCapabilities gains an
optional style_profile that serialises to a flat sub-dict via to_dict()
when set; absent from the JSON envelope when None.

Refs #203"
```

---

## Task 2: `resolve_style` + default-fallback CHECKPOINT_PATTERNS entry

**Files:**
- Modify: `src/image_generation_mcp/providers/model_styles.py`
- Test: `tests/test_model_styles.py`

- [ ] **Step 1: Write failing resolver tests**

Append to `tests/test_model_styles.py`:

```python
from image_generation_mcp.providers.model_styles import resolve_style


def test_resolve_style_returns_none_for_unknown_provider():
    assert resolve_style("future-provider", "any-model") is None


def test_resolve_style_returns_none_for_openai_unknown_model():
    assert resolve_style("openai", "definitely-not-a-real-model-id") is None


def test_resolve_style_sd_webui_falls_back_to_default():
    profile = resolve_style("sd_webui", "completely-unknown-checkpoint-xyz123.safetensors")
    assert profile is not None
    assert "Unknown checkpoint" in profile.label


def test_resolve_style_sd_webui_is_case_insensitive():
    profile = resolve_style("sd_webui", "TOTALLY-RANDOM-NAME")
    assert profile is not None  # default fallback always matches
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: ImportError on `resolve_style`.

- [ ] **Step 3: Add `MODEL_STYLES`, `CHECKPOINT_PATTERNS`, `resolve_style` to `model_styles.py`**

Append to `src/image_generation_mcp/providers/model_styles.py`:

```python
import re

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/providers/model_styles.py tests/test_model_styles.py
git commit -m "feat(providers): add resolve_style with default-fallback CHECKPOINT_PATTERNS

Resolver: exact-key lookup against MODEL_STYLES (closed-list providers),
falls back to regex-ordered CHECKPOINT_PATTERNS for sd_webui. The empty-
pattern fallback entry guarantees a non-None return for any SD checkpoint
name.

Refs #203"
```

---

## Task 3: Populate `MODEL_STYLES` for OpenAI / Gemini / placeholder

**Files:**
- Modify: `src/image_generation_mcp/providers/model_styles.py`
- Test: `tests/test_model_styles.py`

- [ ] **Step 1: Write failing tests for the populated registry**

Append to `tests/test_model_styles.py`:

```python
import pytest

from image_generation_mcp.providers.model_styles import MODEL_STYLES


def test_all_model_styles_have_non_empty_prose():
    """Every registered profile must carry usable narrative content."""
    assert MODEL_STYLES, "MODEL_STYLES must not be empty"
    for key, profile in MODEL_STYLES.items():
        assert profile.label, f"{key}: empty label"
        assert profile.style_hints.strip(), f"{key}: empty style_hints"
        assert profile.incompatible_styles.strip(), (
            f"{key}: empty incompatible_styles"
        )
        assert profile.good_example.strip(), f"{key}: empty good_example"
        assert profile.bad_example.strip(), f"{key}: empty bad_example"
        if profile.lifecycle != "current":
            assert profile.deprecation_note, (
                f"{key}: lifecycle={profile.lifecycle} requires deprecation_note"
            )


@pytest.mark.parametrize(
    "key,expected_lifecycle",
    [
        ("openai:gpt-image-1.5",  "current"),
        ("openai:gpt-image-1",    "legacy"),
        ("openai:gpt-image-1-mini", "current"),
        ("openai:dall-e-3",       "deprecated"),
        ("openai:dall-e-2",       "legacy"),
        ("gemini:gemini-2.5-flash-image",         "current"),
        ("gemini:gemini-3.1-flash-image-preview", "current"),
        ("gemini:gemini-3-pro-image-preview",     "current"),
        ("placeholder:placeholder", "current"),
    ],
)
def test_known_model_lifecycle(key: str, expected_lifecycle: str):
    assert key in MODEL_STYLES
    assert MODEL_STYLES[key].lifecycle == expected_lifecycle


def test_dall_e_3_has_removal_date():
    profile = MODEL_STYLES["openai:dall-e-3"]
    assert profile.deprecation_note is not None
    assert "2026-05-12" in profile.deprecation_note


def test_resolve_style_picks_up_openai():
    profile = resolve_style("openai", "gpt-image-1.5")
    assert profile is not None
    assert profile.lifecycle == "current"


def test_resolve_style_picks_up_gemini():
    profile = resolve_style("gemini", "gemini-2.5-flash-image")
    assert profile is not None
    assert "Nano Banana" in profile.label


def test_resolve_style_picks_up_placeholder():
    profile = resolve_style("placeholder", "placeholder")
    assert profile is not None
    assert profile.lifecycle == "current"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: nine FAIL assertions on missing keys.

- [ ] **Step 3: Replace empty `MODEL_STYLES` with the populated dict**

In `src/image_generation_mcp/providers/model_styles.py`, replace `MODEL_STYLES: dict[str, StyleProfile] = {}` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: PASS for all 18 tests in this file.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/providers/model_styles.py tests/test_model_styles.py
git commit -m "feat(providers): populate MODEL_STYLES for OpenAI / Gemini / placeholder

Adds nine StyleProfile entries covering every model_id that the OpenAI,
Gemini, and placeholder providers expose today. Lifecycle flags:
- openai:gpt-image-1.5, gpt-image-1-mini → current
- openai:gpt-image-1, dall-e-2 → legacy
- openai:dall-e-3 → deprecated (API removal 2026-05-12)
- gemini:* → current (3.x variants flagged as preview)
- placeholder → current

Prose sourced from the brainstorming research report (2026-04-29).

Refs #203"
```

---

## Task 4: Populate `CHECKPOINT_PATTERNS` (SD WebUI)

**Files:**
- Modify: `src/image_generation_mcp/providers/model_styles.py`
- Test: `tests/test_model_styles.py`

- [ ] **Step 1: Write failing pattern-ordering tests**

Append to `tests/test_model_styles.py`:

```python
@pytest.mark.parametrize(
    "model_id,expected_label_substring",
    [
        # FLUX.2 must beat generic flux
        ("flux2_dev_nf4.safetensors", "FLUX.2"),
        # Schnell must beat generic flux
        ("flux1_schnell_nf4.safetensors", "Schnell"),
        # Generic flux1 dev still routes to Flux 1 entry
        ("flux1_dev_nf4.safetensors", "Flux 1"),
        # Pony tag system
        ("ponyDiffusionV6XL.safetensors", "Pony"),
        ("autismMix_confetti.safetensors", "Pony"),
        # Illustrious / NoobAI must beat animagine for Illustrious-Animagine fine-tunes
        ("illustriousJuggernaut_v3.safetensors", "Illustrious"),
        ("noobAI_xl_vpred.safetensors", "Illustrious"),
        # Animagine still wins on plain Animagine names
        ("animagineXL_v3.safetensors", "Animagine"),
        # Coloring book
        ("coloringBook_v1.ckpt", "Coloring"),
        # Juggernaut on its own routes to photorealistic, but Illustrious-prefixed routes elsewhere
        ("juggernautXL_v9.safetensors", "Juggernaut"),
        # DreamShaper Lightning specificity
        ("dreamshaperXL_v21Lightning.safetensors", "Lightning"),
        ("dreamshaperXL_v2.safetensors", "DreamShaperXL"),
        ("dreamshaper_8.safetensors", "DreamShaper"),
        # SD3 / SD3.5
        ("sd3_5_large.safetensors", "SD 3"),
        ("sd_3_medium.safetensors", "SD 3"),
        # SDXL base
        ("sd_xl_base_1.0.safetensors", "SDXL Base"),
        # RealVisXL
        ("realvisxl_v4.safetensors", "RealVisXL"),
        # SD 1.5 base
        ("v1-5-pruned-emaonly.safetensors", "SD 1.5"),
        ("sd_1_5_base.safetensors", "SD 1.5"),
        # Default fallback
        ("xyzUnknownCheckpoint.safetensors", "Unknown"),
    ],
)
def test_checkpoint_pattern_routing(model_id: str, expected_label_substring: str):
    profile = resolve_style("sd_webui", model_id)
    assert profile is not None
    assert expected_label_substring in profile.label, (
        f"{model_id} routed to {profile.label!r}, expected substring "
        f"{expected_label_substring!r}"
    )


def test_default_fallback_is_last_pattern():
    """Empty-pattern entry must be the final tuple element."""
    from image_generation_mcp.providers.model_styles import CHECKPOINT_PATTERNS

    last_pattern, _ = CHECKPOINT_PATTERNS[-1]
    assert last_pattern.pattern == ""
    # Sanity: every other pattern is non-empty
    for pattern, _ in CHECKPOINT_PATTERNS[:-1]:
        assert pattern.pattern, "non-default fallback patterns must be non-empty"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: FAIL on every parametrized case except the last (Unknown — already passes via the fallback).

- [ ] **Step 3: Replace the single-entry CHECKPOINT_PATTERNS with the full table**

In `src/image_generation_mcp/providers/model_styles.py`, replace the entire `CHECKPOINT_PATTERNS = (...)` block with:

```python
CHECKPOINT_PATTERNS: tuple[tuple[re.Pattern[str], StyleProfile], ...] = (
    # ----- FLUX.2 (must precede generic flux) -----
    (
        re.compile(r"flux.?2|flux2"),
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
        re.compile(r"flux.*schnell|schnell"),
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
                "photograph\" (Schnell sacrifices fine detail for speed)"
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
                'score_9, score_8_up, score_7_up, score_6_up, '
                'source_anime, rating_safe, 1girl, school uniform, '
                'cherry blossoms, soft lighting'
            ),
            bad_example=(
                "1girl, anime, cherry blossoms (missing score_* prefix — "
                "output collapses)"
            ),
        ),
    ),
    # ----- Illustrious / NoobAI (must precede animagine) -----
    (
        re.compile(r"illustrious|noobai|noob.?ai"),
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
                'style="bold ink linework", medium="black-and-white outline '
                'drawing"'
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
                'style="painterly fantasy illustration", medium="digital '
                'concept art"'
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
            good_example=(
                'style="watercolor portraiture", medium="ink illustration"'
            ),
            bad_example=(
                'style="hyperrealistic skin at 1024px", medium="macro '
                'studio photograph" (SD 1.5 native latent is 512²; '
                "use SDXL or run hires-fix)"
            ),
        ),
    ),
    # ----- Default fallback — must remain last -----
    (
        re.compile(r""),
        StyleProfile(
            label="Unknown checkpoint (SD general-purpose defaults)",
            style_hints=(
                "Stable Diffusion generally excels at stylised imagery, "
                "fantasy environments, and character portraiture. Use "
                "explicit style tokens (e.g. 'watercolor painting', "
                "'cinematic photograph') for best results."
            ),
            incompatible_styles=(
                "Coherent embedded text and photographic product catalogs "
                "without specialised fine-tuning."
            ),
            good_example=(
                'style="painterly fantasy illustration with explicit style '
                'tokens", medium="digital concept art"'
            ),
            bad_example=(
                'style="coherent embedded text", medium="document scan '
                'with readable signage" (Stable Diffusion generally cannot '
                "render legible text)"
            ),
        ),
    ),
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_model_styles.py -x -v
```

Expected: PASS for all parametrized routing tests + the structural test.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/providers/model_styles.py tests/test_model_styles.py
git commit -m "feat(providers): populate CHECKPOINT_PATTERNS for SD WebUI

Adapts the questfoundry checkpoint_styles.py table with audit-driven fixes
and additions:

Audit fixes:
- Flux entry split: FLUX.2 + Schnell now have dedicated entries above the
  generic Flux 1 dev/pro pattern. Negative-prompt note reframed from
  'weak' to 'unsupported (CFG=1 distilled)'.
- Juggernaut regex tightened to exclude Illustrious-Juggernaut anime-base
  fine-tunes that were being mis-classified as photorealistic.
- DreamShaperXL Lightning step recommendation corrected to 3-6 (was 4-8).
- SDXL base 'use refiner' advice removed — community abandoned the
  refiner ~mid-2024.
- SD 1.5 '768px ceiling' softened to reflect hires-fix / upscaler workflows.

New entries:
- FLUX.2 (current photorealistic flagship)
- Flux Schnell (1-4 step distilled)
- Pony Diffusion XL family (mandatory score_* tag prefix)
- Illustrious-XL / NoobAI-XL (modern anime SDXL bases)
- SD 3 / 3.5 (triple-encoder; natural-language prose)
- RealVisXL (current SDXL photoreal favourite)

Pattern ordering invariants pinned by parametrized tests.

Refs #203"
```

---

## Task 5: SD3 architecture detection fix

**Files:**
- Modify: `src/image_generation_mcp/providers/sd_webui.py`
- Test: `tests/test_sd_webui_provider.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_sd_webui_provider.py`:

```python
def test_detect_architecture_sd3():
    from image_generation_mcp.providers.sd_webui import _detect_architecture

    assert _detect_architecture("sd3_5_large.safetensors") == "sd3"
    assert _detect_architecture("sd_3_medium.safetensors") == "sd3"
    assert _detect_architecture("stable_diffusion_3_5_large_turbo.safetensors") == "sd3"


def test_sd3_preset_uses_natural_language_prompt_style():
    from image_generation_mcp.providers.sd_webui import _resolve_preset

    preset = _resolve_preset("sd3_5_large.safetensors")
    assert preset.prompt_style == "natural_language"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_sd_webui_provider.py -x -v -k "sd3"
```

Expected: FAIL — `_detect_architecture("sd3_5_large.safetensors")` currently returns `"sd15"`.

- [ ] **Step 3: Add SD3 branch to `_detect_architecture` + `_SD3_PRESET`**

Edit `src/image_generation_mcp/providers/sd_webui.py`:

Add the SD3 tag tuple near the existing tag definitions (around `_FLUX_TAGS`):

```python
_SD3_TAGS = ("sd3", "sd_3", "stable_diffusion_3", "stable-diffusion-3")
```

Add a new preset constant near the existing presets (after `_FLUX_SCHNELL_PRESET`):

```python
_SD3_PRESET = _SdWebuiPreset(
    sizes=_SDXL_SIZES,
    steps=28,
    sampler="DPM++ 2M",
    scheduler="Karras",
    cfg_scale=4.5,
    quality_tier="high",
    supports_negative_prompt=True,
    prompt_style="natural_language",
)
```

In `_detect_architecture`, add an SD3 check before the Flux check (and add `"sd3"` as a returned value in the docstring):

```python
def _detect_architecture(model_name: str) -> str:
    """Detect SD architecture from a checkpoint name.

    Detection order:
    1. SD 3 / 3.5 — returns ``"sd3"``
    2. Flux schnell — returns ``"flux_schnell"``
    3. Flux dev — returns ``"flux_dev"``
    4. Lightning/Turbo SDXL — returns ``"sdxl_lightning"``
    5. Standard SDXL — returns ``"sdxl"``
    6. SD 1.5 fallback — returns ``"sd15"``

    Args:
        model_name: Checkpoint name or title string (case-insensitive).

    Returns:
        One of ``"sd15"``, ``"sdxl"``, ``"sdxl_lightning"``, ``"flux_dev"``,
        ``"flux_schnell"``, or ``"sd3"``.
    """
    lower = model_name.lower()
    if any(tag in lower for tag in _SD3_TAGS):
        return "sd3"
    is_flux = any(tag in lower for tag in _FLUX_TAGS)
    if is_flux:
        if "schnell" in lower:
            return "flux_schnell"
        return "flux_dev"
    is_xl = any(tag in lower for tag in _XL_TAGS)
    is_lightning = any(tag in lower for tag in _LIGHTNING_TAGS)
    if is_xl and is_lightning:
        return "sdxl_lightning"
    if is_xl:
        return "sdxl"
    return "sd15"
```

Add the SD3 preset to `_ARCH_PRESETS`:

```python
_ARCH_PRESETS: dict[str, _SdWebuiPreset] = {
    "sd3": _SD3_PRESET,
    "flux_schnell": _FLUX_SCHNELL_PRESET,
    "flux_dev": _FLUX_DEV_PRESET,
    "sdxl_lightning": _SDXL_LIGHTNING_PRESET,
    "sdxl": _SDXL_PRESET,
}
```

In `discover_capabilities()`, the existing `max_resolution` calculation needs to include `"sd3"` in the high-res arch tuple:

```python
            max_resolution = (
                1024
                if arch in ("sdxl", "sdxl_lightning", "flux_dev", "flux_schnell", "sd3")
                else 768
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_sd_webui_provider.py -x -v
```

Expected: PASS for the new SD3 tests + all existing tests still PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/providers/sd_webui.py tests/test_sd_webui_provider.py
git commit -m "fix(sd_webui): detect SD3/3.5 checkpoints; tag prompt_style=natural_language

Before: sd3_5_large.safetensors silently fell through to the SD1.5
fallback in _detect_architecture, which set prompt_style='clip'. SD3
uses a triple-encoder including T5-XXL and benefits from natural-
language prose, so the previous tagging was actively misleading to
LLMs reading list_providers.

After: a new _SD3_PRESET with prompt_style='natural_language',
supports_negative_prompt=True (unlike Flux), CFG=4.5, 28 steps. Detection
runs before the Flux check.

Surfaced by the 2026-04-29 checkpoint-style audit.

Refs #203"
```

---

## Task 6: Wire all four providers' `discover_capabilities` to call `resolve_style`

**Files:**
- Modify: `src/image_generation_mcp/providers/openai.py`, `gemini.py`, `sd_webui.py`, `placeholder.py`
- Test: `tests/test_openai_discovery.py`, `tests/test_gemini_discovery.py`, `tests/test_sd_webui_discovery.py`, `tests/test_placeholder.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_openai_discovery.py`:

```python
async def test_discover_capabilities_populates_style_profile_for_known_models(
    monkeypatch,
):
    """Each ModelCapabilities entry for a known OpenAI model_id carries a profile."""
    # Use the existing fixture pattern in this file. The discovery call
    # should return ModelCapabilities entries with style_profile populated
    # for every model_id that is also a key in MODEL_STYLES.
    from image_generation_mcp.providers.model_styles import MODEL_STYLES

    # ... call provider.discover_capabilities() with the existing fake/mock
    # client setup for this test file. Assert:
    caps = await _discover()  # use whatever helper this file already defines
    for model_caps in caps.models:
        key = f"openai:{model_caps.model_id}"
        if key in MODEL_STYLES:
            assert model_caps.style_profile is not None, (
                f"expected style_profile for {key}"
            )
            assert model_caps.style_profile.label
```

(If `tests/test_openai_discovery.py` already has a discovery helper / fixture, reuse it. Otherwise, follow the established mock pattern in the same file. Do not invent a new mocking approach.)

Add equivalent tests to `tests/test_gemini_discovery.py`, `tests/test_sd_webui_discovery.py`, and `tests/test_placeholder.py`. For SD WebUI, also assert that an unknown checkpoint name routes to the default-fallback profile (label contains "Unknown") rather than `None`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_openai_discovery.py tests/test_gemini_discovery.py \
              tests/test_sd_webui_discovery.py tests/test_placeholder.py -x -v
```

Expected: FAIL on `style_profile is None`.

- [ ] **Step 3: Wire OpenAI**

Edit `src/image_generation_mcp/providers/openai.py`. At the top, add:

```python
from image_generation_mcp.providers.model_styles import resolve_style
```

In `discover_capabilities()`, every `model_caps.append(ModelCapabilities(...))` call needs `style_profile=resolve_style("openai", "<model_id>")` added to its kwargs. Five call sites: `gpt-image-1`, the loop covering `gpt-image-1-mini` + `gpt-image-1.5`, `dall-e-3`, `dall-e-2`. Example for the `gpt-image-1` block:

```python
            model_caps.append(
                ModelCapabilities(
                    model_id="gpt-image-1",
                    display_name="GPT Image 1",
                    can_generate=True,
                    can_edit=True,
                    supports_mask=True,
                    supports_background=True,
                    supports_negative_prompt=False,
                    supported_aspect_ratios=tuple(_GPT_IMAGE_SIZES),
                    supported_formats=("png", "jpeg", "webp"),
                    supported_qualities=("standard", "hd"),
                    max_resolution=1536,
                    style_profile=resolve_style("openai", "gpt-image-1"),
                )
            )
```

Apply the same pattern to the mini/1.5 loop (using `mini_model_id` as the key) and to the `dall-e-3` / `dall-e-2` blocks.

- [ ] **Step 4: Wire Gemini**

Edit `src/image_generation_mcp/providers/gemini.py`. Add `from image_generation_mcp.providers.model_styles import resolve_style` to imports.

Locate the loop in `discover_capabilities()` that appends a `ModelCapabilities` per `(model_id, display_name)` in `_KNOWN_IMAGE_MODELS`. Add `style_profile=resolve_style("gemini", model_id)` to its kwargs.

- [ ] **Step 5: Wire SD WebUI**

Edit `src/image_generation_mcp/providers/sd_webui.py`. Add the import. In `discover_capabilities()`, inside the per-checkpoint loop, add `style_profile=resolve_style("sd_webui", title)` to the `ModelCapabilities(...)` kwargs.

- [ ] **Step 6: Wire placeholder**

Edit `src/image_generation_mcp/providers/placeholder.py`. Add the import. In `discover_capabilities()`, add `style_profile=resolve_style("placeholder", "placeholder")` to the single `ModelCapabilities(...)` kwargs.

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_openai_discovery.py tests/test_gemini_discovery.py \
              tests/test_sd_webui_discovery.py tests/test_placeholder.py -x -v
```

Expected: PASS.

- [ ] **Step 8: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 9: Commit**

```bash
git add src/image_generation_mcp/providers/openai.py \
        src/image_generation_mcp/providers/gemini.py \
        src/image_generation_mcp/providers/sd_webui.py \
        src/image_generation_mcp/providers/placeholder.py \
        tests/test_openai_discovery.py tests/test_gemini_discovery.py \
        tests/test_sd_webui_discovery.py tests/test_placeholder.py
git commit -m "feat(providers): populate style_profile in discover_capabilities

All four providers now call resolve_style(provider, model_id) per model
and pass the result into ModelCapabilities(..., style_profile=...). The
field flows into list_providers JSON automatically via the existing
to_dict() chain. SD WebUI checkpoints get a profile for every name (the
empty-pattern fallback in CHECKPOINT_PATTERNS guarantees a non-None
return).

Refs #203"
```

---

## Task 7: `list_providers` top-level `warnings` array

**Files:**
- Modify: `src/image_generation_mcp/_server_tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tools.py`:

```python
async def test_list_providers_includes_warnings_array_for_deprecated_models(
    fastmcp_client_with_openai_dalle3,  # existing fixture or create one
):
    """When a deprecated model is configured, list_providers warns."""
    response = await fastmcp_client_with_openai_dalle3.call_tool(
        "list_providers", {"force_refresh": False}
    )
    payload = json.loads(response.content[0].text)
    assert "warnings" in payload
    assert any("dall-e-3" in w and "2026-05-12" in w for w in payload["warnings"])


async def test_list_providers_warnings_is_empty_when_no_deprecated_models(
    fastmcp_client_only_placeholder,
):
    response = await fastmcp_client_only_placeholder.call_tool(
        "list_providers", {"force_refresh": False}
    )
    payload = json.loads(response.content[0].text)
    assert payload["warnings"] == []
```

(Reuse / extend the existing FastMCP test client setup in this file. If a fixture for "openai with dall-e-3 only" doesn't exist, build one following the same pattern as other fixtures in `tests/_helpers.py`.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_tools.py -x -v -k warnings
```

Expected: FAIL — `warnings` key not in JSON.

- [ ] **Step 3: Build the warnings array in `list_providers`**

Edit `src/image_generation_mcp/_server_tools.py`. Locate `list_providers` (around line 885). Replace its body:

```python
        if force_refresh:
            await service.discover_all_capabilities()
        providers = service.list_providers()
        warnings = _build_lifecycle_warnings(providers)
        result = {
            "refreshed_at": datetime.now(UTC).isoformat(),
            "providers": providers,
            "warnings": warnings,
        }
        return json.dumps(result, indent=2)
```

Add the helper near the top of the module (just below the existing imports / before `_register_tools`):

```python
def _build_lifecycle_warnings(providers: list[dict[str, Any]]) -> list[str]:
    """Return human-readable warning strings for legacy/deprecated models.

    Each warning is keyed by ``"{provider}:{model_id}"`` and includes the
    deprecation note from the StyleProfile. Returns an empty list when no
    configured model is on a non-current lifecycle.
    """
    warnings: list[str] = []
    for provider in providers:
        provider_name = provider.get("name") or provider.get("provider_name")
        for model in provider.get("models", []):
            profile = model.get("style_profile")
            if not profile:
                continue
            lifecycle = profile.get("lifecycle", "current")
            if lifecycle == "current":
                continue
            note = profile.get("deprecation_note", "")
            warnings.append(
                f"{provider_name}:{model.get('model_id')} — "
                f"{lifecycle}. {note}".strip()
            )
    return warnings
```

(Adjust the `provider.get("name") or provider.get("provider_name")` line if `service.list_providers()` returns a different shape — check the existing key names there and keep one consistent name.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tools.py -x -v -k warnings
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/_server_tools.py tests/test_tools.py
git commit -m "feat(tools): add warnings array to list_providers

Top-level warnings[] auto-built from any model with lifecycle in
{legacy, deprecated}. Each entry is a human-readable sentence keyed
by 'provider:model_id' that includes the deprecation_note from the
StyleProfile. Always present (empty list when no warnings apply) so
the schema is stable for consumers.

Refs #203"
```

---

## Task 8: `generate_image` tool docstring update

**Files:**
- Modify: `src/image_generation_mcp/_server_tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tools.py`:

```python
def test_generate_image_docstring_mentions_style_profile_and_warnings(mcp_server):
    """Docstring must point the LLM at style_profile + warnings."""
    tools = mcp_server.list_tools_sync()  # or whatever the existing helper is
    generate_image = next(t for t in tools if t.name == "generate_image")
    assert "style_profile" in generate_image.description
    assert "warnings" in generate_image.description
```

(Adapt the tool-introspection call to match this repo's existing pattern in `tests/test_tools.py`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tools.py -x -v -k docstring_mentions_style
```

Expected: FAIL — neither `style_profile` nor `warnings` in `generate_image` docstring.

- [ ] **Step 3: Update the docstring**

Edit `src/image_generation_mcp/_server_tools.py`. Find the `generate_image` tool function (around line 120-160) and locate the existing paragraph that reads:

> Call list_providers first to see available providers and model IDs. Check each model's ``prompt_style`` in list_providers to choose the right prompt format ...

Append immediately after that paragraph:

> When picking ``model``, also consult each entry's ``style_profile``: ``style_hints`` describes what the model is good for; ``incompatible_styles`` describes what fights it; ``good_example`` and ``bad_example`` show the prompt grammar. The top-level ``warnings`` array lists deprecated models to avoid for new long-lived workflows.

(Keep the existing prose intact; just append the new paragraph.)

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tools.py -x -v -k docstring_mentions_style
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src/
```

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/_server_tools.py tests/test_tools.py
git commit -m "docs(tools): point generate_image at style_profile + warnings

Tool docstrings are the only reliable LLM channel per session memory
(MCP prompts are not auto-injected by all clients). Adds a 40-word
paragraph to generate_image telling the LLM to consult style_profile
fields and the top-level warnings array when picking a model.

Refs #203"
```

---

## Task 9: `scripts/render_model_catalog.py` + initial generated page

**Files:**
- Create: `scripts/render_model_catalog.py`
- Create: `docs/providers/model-catalog.md`
- Test: `tests/test_render_model_catalog.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_render_model_catalog.py`:

```python
"""Tests for scripts/render_model_catalog.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_model_catalog.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_model_catalog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_model_catalog"] = module
    spec.loader.exec_module(module)
    return module


def test_render_model_catalog_returns_markdown_with_all_provider_sections():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    assert "# Model Catalog" in output
    assert "## OpenAI" in output
    assert "## Gemini" in output
    assert "## Placeholder" in output
    assert "## SD WebUI" in output


def test_render_model_catalog_lists_each_known_model():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    for model_id in (
        "gpt-image-1.5",
        "gpt-image-1",
        "dall-e-3",
        "gemini-2.5-flash-image",
        "placeholder",
    ):
        assert model_id in output


def test_render_model_catalog_lists_all_sd_pattern_labels():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    for label_substring in (
        "FLUX.2", "Flux Schnell", "Flux 1", "Pony", "Illustrious",
        "Animagine", "Coloring Book", "Juggernaut", "DreamShaperXL",
        "DreamShaper (versatile SD1.5)", "SD 3", "SDXL Base",
        "RealVisXL", "SD 1.5", "Unknown checkpoint",
    ):
        assert label_substring in output


def test_render_writes_to_target_path(tmp_path):
    renderer = _load_renderer()
    target = tmp_path / "model-catalog.md"
    renderer.write_catalog(target)
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "# Model Catalog" in text


def test_committed_catalog_matches_renderer_output():
    """Drift guard — fails CI when registry is edited without regenerating."""
    renderer = _load_renderer()
    expected = renderer.render_catalog()
    committed = (ROOT / "docs" / "providers" / "model-catalog.md").read_text(
        encoding="utf-8"
    )
    assert committed == expected, (
        "docs/providers/model-catalog.md is out of date. "
        "Run `uv run python scripts/render_model_catalog.py` to regenerate."
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_render_model_catalog.py -x -v
```

Expected: FAIL — script does not exist.

- [ ] **Step 3: Create the renderer**

Create `scripts/render_model_catalog.py`:

```python
#!/usr/bin/env python3
"""Render docs/providers/model-catalog.md from the model_styles registry.

Mirrors the scripts/bump_manifests.py pattern: imports the registry, writes
the page, and is run by a CI step that diffs against the committed file to
guard against drift.

Usage:
    uv run python scripts/render_model_catalog.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running the script without `uv run` having added src/ to sys.path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from image_generation_mcp.providers.model_styles import (  # noqa: E402
    CHECKPOINT_PATTERNS,
    MODEL_STYLES,
    StyleProfile,
)

DEFAULT_TARGET = ROOT / "docs" / "providers" / "model-catalog.md"

PROVIDERS_IN_ORDER: tuple[tuple[str, str], ...] = (
    ("openai", "OpenAI"),
    ("gemini", "Gemini"),
    ("placeholder", "Placeholder"),
)


def _profile_block(profile: StyleProfile) -> str:
    lifecycle_marker = (
        ""
        if profile.lifecycle == "current"
        else f" — **{profile.lifecycle}**"
    )
    note_line = (
        f"\n> {profile.deprecation_note}\n"
        if profile.deprecation_note
        else ""
    )
    return (
        f"### {profile.label}{lifecycle_marker}\n"
        f"{note_line}"
        f"\n**Best for:** {profile.style_hints}\n"
        f"\n**Avoid:** {profile.incompatible_styles}\n"
        f"\n**Good prompt:** `{profile.good_example}`\n"
        f"\n**Bad prompt:** `{profile.bad_example}`\n"
    )


def _render_provider_section(
    provider_key: str, provider_label: str
) -> str:
    entries = sorted(
        (key, profile)
        for key, profile in MODEL_STYLES.items()
        if key.startswith(f"{provider_key}:")
    )
    if not entries:
        return ""

    lines = [f"## {provider_label}\n"]
    lines.append(
        f"Models exposed by the `{provider_key}` provider. Each model "
        f"resolves via exact-key lookup against the registry.\n"
    )
    lines.append("| Model ID | Label | Lifecycle |")
    lines.append("|----------|-------|-----------|")
    for key, profile in entries:
        model_id = key.split(":", 1)[1]
        lines.append(
            f"| `{model_id}` | {profile.label} | {profile.lifecycle} |"
        )
    lines.append("")

    for _, profile in entries:
        lines.append(_profile_block(profile))

    return "\n".join(lines)


def _render_sd_section() -> str:
    lines = ["## SD WebUI\n"]
    lines.append(
        "SD WebUI checkpoints resolve via the regex-ordered "
        "`CHECKPOINT_PATTERNS` table. **First match wins** — patterns are "
        "ordered specific-before-generic, with an empty-pattern fallback "
        "as the final entry to guarantee a non-None match for every "
        "checkpoint name.\n"
    )

    lines.append("### Pattern catalog (in match order)\n")
    lines.append("| # | Pattern | Label |")
    lines.append("|---|---------|-------|")
    for idx, (pattern, profile) in enumerate(CHECKPOINT_PATTERNS, start=1):
        regex_display = (
            f"`{pattern.pattern}`"
            if pattern.pattern
            else "_(default fallback)_"
        )
        lines.append(f"| {idx} | {regex_display} | {profile.label} |")
    lines.append("")

    for pattern, profile in CHECKPOINT_PATTERNS:
        regex_display = (
            f"`{pattern.pattern}`"
            if pattern.pattern
            else "_(default fallback — empty pattern)_"
        )
        lines.append(f"#### Pattern: {regex_display}\n")
        lines.append(_profile_block(profile))

    return "\n".join(lines)


def render_catalog() -> str:
    """Return the full model catalog markdown."""
    parts = [
        "<!-- Generated by scripts/render_model_catalog.py — do not edit. -->\n",
        "# Model Catalog\n",
        (
            "Per-model narrative metadata read by LLMs when choosing "
            "between providers and models. Closed-list providers "
            "(`openai`, `gemini`, `placeholder`) use exact-key lookup "
            "against `MODEL_STYLES`. SD WebUI uses the regex-ordered "
            "`CHECKPOINT_PATTERNS` table.\n"
        ),
        (
            "Source: "
            "`src/image_generation_mcp/providers/model_styles.py`. "
            "Regenerate with "
            "`uv run python scripts/render_model_catalog.py`.\n"
        ),
    ]
    for key, label in PROVIDERS_IN_ORDER:
        parts.append(_render_provider_section(key, label))
    parts.append(_render_sd_section())
    return "\n".join(parts).rstrip() + "\n"


def write_catalog(target: Path = DEFAULT_TARGET) -> None:
    """Render the catalog and write it to *target*."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_catalog(), encoding="utf-8")


if __name__ == "__main__":
    write_catalog()
    print(f"Wrote {DEFAULT_TARGET}")
```

- [ ] **Step 4: Generate the initial catalog**

```bash
uv run python scripts/render_model_catalog.py
```

Expected: prints `Wrote docs/providers/model-catalog.md`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_render_model_catalog.py -x -v
```

Expected: PASS for all five tests, including the drift-guard.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check --fix scripts tests && uv run ruff format scripts tests && uv run mypy src/
```

- [ ] **Step 7: Commit**

```bash
git add scripts/render_model_catalog.py docs/providers/model-catalog.md tests/test_render_model_catalog.py
git commit -m "feat(docs): generate model-catalog.md from the registry

New scripts/render_model_catalog.py mirrors the scripts/bump_manifests.py
pattern — imports the model_styles registry, renders a markdown catalog
page grouped by provider, and writes it to docs/providers/model-catalog.md.
The committed page is checked in so it shows in mkdocs serve and PR diffs;
a follow-up CI step (next task) guards against drift.

Refs #203"
```

---

## Task 10: CI drift-guard, mkdocs nav, pre-commit hook

**Files:**
- Modify: `.github/workflows/docs.yml`, `mkdocs.yml`, `.pre-commit-config.yaml`

- [ ] **Step 1: Add the drift-guard step to docs.yml**

Edit `.github/workflows/docs.yml`. In the `build` job, before any `mkdocs build` step, add:

```yaml
      - name: Verify model catalog is up to date
        run: |
          uv run python scripts/render_model_catalog.py
          git diff --exit-code docs/providers/model-catalog.md
```

(The exact placement depends on the current job structure — put it after the `uv` setup / dependency install step and before the `mkdocs build` step.)

- [ ] **Step 2: Add the catalog page to mkdocs nav**

Edit `mkdocs.yml`. In the `nav:` section, find the Providers block:

```yaml
  - Providers:
      - Overview: providers/index.md
      - Gemini: providers/gemini.md
      - OpenAI: providers/openai.md
      - SD WebUI (Stable Diffusion): providers/sd-webui.md
      - Placeholder: providers/placeholder.md
```

Add the catalog as the second-to-last entry:

```yaml
  - Providers:
      - Overview: providers/index.md
      - Gemini: providers/gemini.md
      - OpenAI: providers/openai.md
      - SD WebUI (Stable Diffusion): providers/sd-webui.md
      - Model Catalog: providers/model-catalog.md
      - Placeholder: providers/placeholder.md
```

Apply the same change to the `llmstxt:` plugin's `Providers:` section listing earlier in the file (so the catalog is included in `llms-full.txt`).

- [ ] **Step 3: Add pre-commit hook**

Edit `.pre-commit-config.yaml`. Append to the `repo: local` block:

```yaml
      - id: render-model-catalog
        name: render model catalog
        language: system
        entry: uv run python scripts/render_model_catalog.py
        files: '^(src/image_generation_mcp/providers/model_styles\.py|scripts/render_model_catalog\.py)$'
        pass_filenames: false
```

(The `files:` regex limits the hook to runs where the registry or renderer changed. The hook regenerates the catalog in place; combined with the trailing `git diff --exit-code` in CI, drift is impossible.)

- [ ] **Step 4: Verify mkdocs build succeeds locally**

```bash
uv run mkdocs build --strict
```

Expected: builds without warnings; `site/providers/model-catalog/index.html` exists.

- [ ] **Step 5: Run the pre-commit hook end-to-end**

```bash
uv run pre-commit run render-model-catalog --all-files
```

Expected: PASS — exits 0 with no diff.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/docs.yml mkdocs.yml .pre-commit-config.yaml
git commit -m "ci(docs): add model-catalog drift-guard + nav entry + pre-commit hook

CI step regenerates docs/providers/model-catalog.md and fails on drift.
Pre-commit hook regenerates locally when the registry or renderer
changes. Catalog page added to mkdocs nav and the llmstxt plugin's
Providers section.

Refs #203"
```

---

## Task 11: Update existing user-facing docs

**Files:**
- Modify: `docs/tools.md`, `docs/resources.md`, `docs/providers/index.md`, `docs/guides/prompt-writing.md`

- [ ] **Step 1: Update `docs/tools.md`**

Find the existing `list_providers` section. Append (or extend the existing fields list with):

> The JSON envelope contains a top-level `warnings` array (always present, may be empty) listing deprecated or legacy models that are configured. Each entry in `models` may carry a `style_profile` sub-object with `label`, `style_hints`, `incompatible_styles`, `good_example`, `bad_example`, `lifecycle`, and (when set) `deprecation_note`. See [Model Catalog](providers/model-catalog.md) for the full registry.

Find the existing `generate_image` section. Append:

> When picking `model`, consult each entry's `style_profile.style_hints` and `style_profile.incompatible_styles` from `list_providers`; check the top-level `warnings` array to avoid deprecated models for new work. The [Model Catalog](providers/model-catalog.md) lists all known models with their full profiles.

- [ ] **Step 2: Update `docs/resources.md`**

Find the `info://providers` section. Append the same `warnings` + `style_profile` description as above (cross-reference is fine; the resource and the tool return the same JSON shape now).

- [ ] **Step 3: Update `docs/providers/index.md`**

Add a sentence near the top, before any per-provider link list:

> See the [Model Catalog](model-catalog.md) for narrative guidance on every model — what each is best at, what fights it, prompt grammar examples, and lifecycle status.

- [ ] **Step 4: Update `docs/guides/prompt-writing.md`**

Add a one-line pointer near the top of the guide, after the existing intro paragraph:

> For per-model strengths, weaknesses, and prompt examples, see the [Model Catalog](../providers/model-catalog.md).

- [ ] **Step 5: Verify mkdocs build is clean**

```bash
uv run mkdocs build --strict
```

Expected: clean build, no broken links.

- [ ] **Step 6: Commit**

```bash
git add docs/tools.md docs/resources.md docs/providers/index.md docs/guides/prompt-writing.md
git commit -m "docs: cross-reference Model Catalog from tools / resources / guides

list_providers and info://providers now document the new style_profile
sub-object and warnings array. The Providers index and prompt-writing
guide link to the catalog. The catalog itself remains the single
source of truth for per-model narrative content.

Refs #203"
```

---

## Task 12: ADR-0009

**Files:**
- Create: `docs/decisions/0009-model-style-metadata.md`

- [ ] **Step 1: Write the ADR**

Create `docs/decisions/0009-model-style-metadata.md`:

```markdown
# ADR-0009: Per-model style metadata via exact-key lookup with regex fallback

**Status:** accepted (2026-04-29)
**Supersedes:** none.
**Related:** ADR-0007 (provider capability model), ADR-0008 (style library — disambiguation note below).

## Context

`list_providers` exposes per-model technical knobs (`prompt_style`,
resolution, steps, cfg) but no narrative guidance on what each model is
best or worst at. Live testing on 2026-03-20 confirmed the symptom: when
SD WebUI returns 14 opaque checkpoint names, the LLM picks blind.

Per session memory, MCP prompts are not reliably auto-injected by Claude
clients; tool descriptions and `list_providers` JSON are the only stable
LLM-visible channels. So the natural place for per-model narrative is
inside `list_providers` JSON, not inside an MCP prompt.

## Decision

Introduce a `StyleProfile` dataclass and a registry (`MODEL_STYLES` dict
plus `CHECKPOINT_PATTERNS` regex table) in
`src/image_generation_mcp/providers/model_styles.py`. Each provider's
`discover_capabilities()` resolves a profile and attaches it to the
`ModelCapabilities` it returns. The MCP layer surfaces the profile as a
nested sub-object on every model and adds a top-level `warnings` array
auto-built from any `lifecycle in {legacy, deprecated}`.

The resolver uses **exact-key lookup against `MODEL_STYLES`** for
closed-list providers (OpenAI, Gemini, placeholder) and **falls back to
regex-ordered `CHECKPOINT_PATTERNS`** only for SD WebUI. This matches the
shape of the data: closed-list providers expose a finite known set of
model IDs (O(1) dict lookup is the right tool); SD WebUI exposes
arbitrary user-supplied checkpoint filenames (regex pattern matching is
the right tool).

The pattern table follows questfoundry's `checkpoint_styles.py`
discipline: specific patterns precede generic ones, the empty-pattern
default-fallback entry is always last and guarantees a non-None match.

## Considered alternatives

**Per-provider local style tables.** Each provider holds its own static
metadata inline. Rejected: three small tables drift apart; regex matching
code would be duplicated; adding a new provider is more work; cross-
provider semantic consistency (`lifecycle` enum) becomes fragile.

**Pure regex matching for everything.** All providers use the regex
table. Rejected: regex over `gpt-image-1` is theatre — those are exact
strings; regex adds ordering pitfalls and obscures intent. The mechanism
should match the data shape.

**Static markdown blob per model.** Hand-write one markdown file per
model and serve it from a separate resource. Rejected: not visible in
`list_providers` JSON, which is the LLM channel that actually matters;
duplicates the data; harder to keep in sync with code.

## Consequences

**Positive.** Single source of truth for narrative metadata. Closed-list
providers get O(1) lookup. SD WebUI keeps the proven pattern from
questfoundry (with audit fixes). The generated docs page makes drift
visible in PR diffs. Lifecycle field gives a structured channel for
deprecation warnings without polluting the schema with one-off bool
fields.

**Negative.** Hand-curated metadata for fast-moving fine-tunes goes
stale. Mitigation: empty-pattern fallback always matches; the docs page
makes drift visible; updates are encouraged when a checkpoint is
actually being used (not chasing every Civitai release).

**Schema axis is now richer.** The capability schema now has both
`prompt_style` (grammar — clip vs natural_language) and
`style_profile.style_hints` (purpose). These are orthogonal; the
narrative `style_hints` is the natural place to call out grammar quirks
that don't fit the binary axis (e.g. Pony's mandatory `score_*` prefix).

## Disambiguation: ADR-0008 (style library) vs this ADR

ADR-0008's "style library" is **user-facing creative briefs** — saved
markdown files with tags / aspect-ratio / quality fields that the user
applies to a generation request. This ADR's `StyleProfile` is **per-model
metadata** — what each model is good for. The two never interact:
`StyleProfile` describes the model; the style library describes a brief.
Both happen to use the word "style" in their everyday English sense.

## References

- Spec: `docs/design/2026-04-29-model-style-metadata.md`
- Plan: `docs/design/2026-04-29-model-style-metadata-plan.md`
- Source pattern: `pvliesdonk/questfoundry`/`src/questfoundry/providers/checkpoint_styles.py`
- Tracking issue: #203
```

- [ ] **Step 2: Verify mkdocs config still excludes decisions**

```bash
grep -A2 "exclude_docs:" mkdocs.yml
```

Expected output includes `decisions/**` — confirming the ADR is internal-only and not part of the published docs site.

- [ ] **Step 3: Commit**

```bash
git add docs/decisions/0009-model-style-metadata.md
git commit -m "docs(adr): ADR-0009 — per-model style metadata via exact-key + regex fallback

Captures the rationale for the registry shape (exact-key dict for
closed-list providers, regex-ordered tuple for SD WebUI), the
considered alternatives, and the disambiguation vs ADR-0008's style
library (user creative briefs, unrelated despite the shared 'style'
word).

Refs #203"
```

---

## Task 13: Final integration + PR-gate run

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -x -q
```

Expected: all green.

- [ ] **Step 2: Patch coverage check**

```bash
uv run pytest --cov=src/image_generation_mcp/providers/model_styles \
              --cov=src/image_generation_mcp/providers/openai \
              --cov=src/image_generation_mcp/providers/gemini \
              --cov=src/image_generation_mcp/providers/sd_webui \
              --cov=src/image_generation_mcp/providers/placeholder \
              --cov=src/image_generation_mcp/_server_tools \
              --cov-report=term-missing
```

Expected: ≥80% coverage on the changed modules. If below 80% on any module, add tests for the uncovered branches before pushing.

- [ ] **Step 3: Lint + type-check + format-check**

Run in this exact order (per CLAUDE.md hard PR gates):

```bash
uv run ruff check --fix .
uv run ruff format .
uv run ruff format --check .
uv run mypy src/
```

Expected: all clean.

- [ ] **Step 4: mkdocs strict build**

```bash
uv run mkdocs build --strict
```

Expected: clean build.

- [ ] **Step 5: End-to-end sanity — list_providers JSON shape**

Start the server in dry-run mode (or use whatever quick-introspection helper this repo provides) and call `list_providers`. Manually verify the JSON contains:

- Top-level `warnings: [...]` array (with at least one entry mentioning `dall-e-3` and `2026-05-12` if `dall-e-3` is configured).
- Per-model `style_profile.label`, `style_profile.style_hints`, etc.

If a quick CLI introspection isn't available, this can be a manual `pytest -k smoke` run that exercises the full path.

- [ ] **Step 6: File the three out-of-scope follow-up issues**

```bash
gh issue create --repo pvliesdonk/image-generation-mcp \
  --title "refactor: refresh _SELECT_PROVIDER_PROMPT and _PROMPT_GUIDE for 2026 model lineup" \
  --body "Follow-up to #203. The static prompt text in _server_prompts.py overlaps with the new model_styles registry. Refactor either to consume the registry directly or hand-edit in sync. Out of scope for #203 to keep that PR focused on the data layer." \
  --label enhancement

gh issue create --repo pvliesdonk/image-generation-mcp \
  --title "feat(openai): add gpt-image-2 to provider config when OpenAI ships it" \
  --body "Follow-up to #203. The model_styles registry is ready to receive a profile for gpt-image-2 once OpenAI ships it. Track here so we don't forget when the model lands." \
  --label enhancement

gh issue create --repo pvliesdonk/image-generation-mcp \
  --title "feat(gemini): surface SynthID watermark capability on gemini-2.5-flash-image" \
  --body "Follow-up to #203. All Gemini Flash Image outputs carry an invisible SynthID watermark. Add a structured \`watermark: \"synthid\"\` field on ModelCapabilities so consumers can warn users when bit-perfect originals are required." \
  --label enhancement
```

Capture the three issue URLs for the PR description.

- [ ] **Step 7: Push and open draft PR**

```bash
git push -u origin feat/model-style-metadata
gh pr create --draft --title "feat: per-model style metadata + warnings on list_providers" \
  --body "$(cat <<'EOF'
## Summary

- New StyleProfile registry (exact-key for closed providers, regex for SD WebUI)
- Per-model `style_profile` field on `list_providers` JSON
- Top-level `warnings` array auto-built from `lifecycle in {legacy, deprecated}`
- generate_image tool docstring points the LLM at the new fields
- Generated docs/providers/model-catalog.md with CI drift-guard
- Folded fix: SD3/3.5 checkpoints get prompt_style="natural_language"
- ADR-0009 captures the architectural choice

Closes #203.

## Out-of-scope follow-ups

- {issue URL #1: refresh _SELECT_PROVIDER_PROMPT}
- {issue URL #2: gpt-image-2 when shipped}
- {issue URL #3: SynthID watermark capability}

## Test plan

- [ ] `uv run pytest -x -q` passes
- [ ] `uv run mypy src/` clean
- [ ] `uv run ruff check --fix . && uv run ruff format --check .` clean
- [ ] Patch coverage ≥80% on changed modules
- [ ] `uv run mkdocs build --strict` clean
- [ ] `list_providers` JSON contains `warnings` + per-model `style_profile`
- [ ] Drift-guard step in docs.yml fails when registry is edited without regeneration

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Replace `{issue URL #N}` placeholders with the actual URLs from Step 6 before posting.

- [ ] **Step 8: Wait for bot review loop**

Per CLAUDE.md "PR workflow":
1. `claude-code-review` runs on every push — read the review body, not the check status. Search for "Still Open", "fix items", "needs to be fixed".
2. After all bot findings addressed and CI green, comment `/gemini review` to re-trigger Gemini on the latest commit.
3. After both bots LGTM and CI green, run `gh pr ready <N>`.

Iterate in draft until convergence. Address even soft-framed findings ("non-blocking", "low-priority follow-up") in-PR per CLAUDE.md "agent-loop trap".

---

## Self-review

**Spec coverage check.** Each spec section maps to a task:

- Schema (spec §"Schema") → Task 1 ✅
- Resolver (spec §"Data layout / Resolver") → Task 2 ✅
- MODEL_STYLES contents (spec §"Closed-list providers") → Task 3 ✅
- CHECKPOINT_PATTERNS contents + audit corrections (spec §"SD WebUI checkpoints" + §"Audit corrections") → Task 4 ✅
- SD3 detector fix (spec §"Architecture-detector fix") → Task 5 ✅
- Provider wiring (spec §"Wiring") → Task 6 ✅
- Top-level `warnings` (spec §"MCP surface / list_providers JSON envelope") → Task 7 ✅
- generate_image docstring (spec §"MCP surface / generate_image tool docstring") → Task 8 ✅
- Generated docs page (spec §"Generated docs page") → Task 9 ✅
- CI drift-guard, mkdocs nav, pre-commit (spec §"Generated docs page" subitems) → Task 10 ✅
- Cross-reference docs (spec §"Documentation impact") → Task 11 ✅
- ADR-0009 (spec §"Documentation impact") → Task 12 ✅
- Follow-up issues (spec §"Out of scope") → Task 13 Step 6 ✅
- PR gates (spec §"Goals" + CLAUDE.md "Hard PR Acceptance Gates") → Task 13 Steps 1-4 ✅

No gaps.

**Placeholder scan.** Searched for "TBD", "TODO", "fill in", "implement later", "similar to Task". The only `TODO`-shaped string is in commit messages where it's not a placeholder; no plan steps describe what to do without showing how. Two acceptable references in test code: `_discover()` (assumes the file already has a discovery helper — explicit comment tells the engineer to reuse) and `fastmcp_client_with_openai_dalle3` (existing fixture pattern — comment tells the engineer to follow `tests/_helpers.py`). Both are honest "use the established pattern in this file" instructions, not handwaves.

**Type consistency.** Names cross-checked: `StyleProfile`, `MODEL_STYLES`, `CHECKPOINT_PATTERNS`, `resolve_style`, `style_profile`, `lifecycle`, `deprecation_note`, `warnings`, `_SD3_PRESET`, `_SD3_TAGS`, `_detect_architecture`. All consistent across tasks.

Plan complete and saved to `docs/design/2026-04-29-model-style-metadata-plan.md`.
