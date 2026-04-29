# Per-model style metadata for `list_providers`

**Status:** approved (brainstorming) — pending implementation plan.
**Date:** 2026-04-29.
**Owner:** Peter van Liesdonk.

## Problem

`list_providers` exposes per-model technical knobs (resolution, steps, cfg,
`prompt_style: "clip" | "natural_language"`) but no narrative guidance on what
each model is good or bad at. The 2026-03-20 live test showed the symptom: when
SD WebUI returns a list of opaque checkpoint names (`juggernautXL_v9`,
`animagineXL_v3`, `flux1_dev_nf4`, ...), the LLM picks blind. The same gap
applies, in milder form, across providers — `gpt-image-1`, `dall-e-3`, and
`gemini-2.5-flash-image` are all currently presented as roughly interchangeable
even though they have meaningfully different strengths and lifecycle status.

Per session memory, MCP prompts are not auto-injected by Claude.ai;
**tool descriptions and `list_providers` JSON are the only reliable LLM
channels** for steering model selection.

This spec adopts (and extends) the `checkpoint_styles.py` pattern from
[`pvliesdonk/questfoundry`][qf] that has worked in practice for SD-checkpoint
selection. It generalises that pattern to all providers.

[qf]: https://github.com/pvliesdonk/questfoundry/blob/main/src/questfoundry/providers/checkpoint_styles.py

## Goals

- Surface per-model narrative guidance (`style_hints`, `incompatible_styles`,
  good/bad prompt examples, `lifecycle`) inside `list_providers` JSON.
- Steer the LLM to read it via the `generate_image` tool docstring (the
  reliable channel, per memory).
- Warn the LLM when a configured model is legacy or being deprecated, with a
  structured `warnings` array on the `list_providers` envelope.
- Publish the registry as a generated documentation page so humans can
  cross-reference it in the public docs site, with CI drift-guard.
- Keep the registry editable as flat data (Python literals) so non-Python
  contributors can update it without tracing across modules.

## Non-goals

- Rewriting `_SELECT_PROVIDER_PROMPT` or `_PROMPT_GUIDE`. Those are stale and
  will be refreshed in a separate follow-up PR (see [Out of scope](#out-of-scope)).
- Adding new provider model IDs (`gpt-image-1.5`, `gpt-image-2`,
  `gemini-3-pro-image-preview`) to provider configuration. The registry will
  carry profiles for them so they're ready when added, but provider config
  changes are a separate PR.
- Adding a SynthID-watermark capability surface for Gemini. Tracked separately.

## Schema

A new module `src/image_generation_mcp/providers/model_styles.py` exports two
frozen dataclasses and two registry tables.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class StyleProfile:
    """Narrative metadata describing a model's strengths and prompt grammar.

    All free-text fields are written as plain prose addressed to an LLM that
    is choosing between models. Examples are short prompt fragments, not full
    prompts.
    """

    label: str
    style_hints: str
    incompatible_styles: str
    good_example: str
    bad_example: str
    lifecycle: Literal["current", "legacy", "deprecated"] = "current"
    deprecation_note: str | None = None
```

`ModelCapabilities` (in `providers/capabilities.py`) gains exactly one new
field, default `None`:

```python
style_profile: StyleProfile | None = None
```

`ModelCapabilities.to_dict()` serialises the profile as a flat sub-dict so JSON
consumers can read e.g. `models[i].style_profile.style_hints` directly. When
`style_profile is None`, the key is omitted (not `null`).

The existing `prompt_style: "clip" | "natural_language"` field keeps its
current meaning. `style_profile` is additive, never a replacement; the two are
orthogonal axes (grammar vs purpose).

## Data layout

### Closed-list providers — exact-key dict

```python
MODEL_STYLES: dict[str, StyleProfile] = {
    # Keys are "{provider_name}:{model_id}". One entry per model_id that the
    # provider actually returns from discover_capabilities() today.
    "openai:gpt-image-1.5":  StyleProfile(label="GPT Image 1.5", ...),                  # current flagship
    "openai:gpt-image-1":    StyleProfile(label="GPT Image 1", ..., lifecycle="legacy"),
    "openai:gpt-image-1-mini": StyleProfile(label="GPT Image 1 Mini", ...),             # cheaper variant
    "openai:dall-e-3":       StyleProfile(..., lifecycle="deprecated",
                                           deprecation_note="OpenAI API removal scheduled 2026-05-12."),
    "openai:dall-e-2":       StyleProfile(..., lifecycle="legacy"),
    "gemini:gemini-2.5-flash-image":         StyleProfile(label="Gemini 2.5 Flash Image (Nano Banana)", ...),
    "gemini:gemini-3.1-flash-image-preview": StyleProfile(label="Gemini 3.1 Flash Image (preview)", ...),
    "gemini:gemini-3-pro-image-preview":     StyleProfile(label="Gemini 3 Pro Image (preview)", ...),
    "placeholder:placeholder":               StyleProfile(label="Solid-color placeholder", ...),
}
```

Source content for the profile prose comes from the brainstorming research
report (cited in commit message). All hosted-API models in this set tag
`prompt_style="natural_language"`. New OpenAI model IDs (e.g. `gpt-image-2`)
join the registry alongside the provider-config change that exposes them.

### SD WebUI checkpoints — ordered regex table

Adapted from questfoundry's `checkpoint_styles.py` with audit fixes (see
[Audit corrections](#audit-corrections-from-questfoundry)):

```python
import re

CHECKPOINT_PATTERNS: tuple[tuple[re.Pattern[str], StyleProfile], ...] = (
    # Specific-before-generic. Empty-pattern fallback is always last.
    (re.compile(r"flux.?2|flux2"),                 StyleProfile(...)),  # NEW: FLUX.2
    (re.compile(r"flux.*schnell|.*schnell"),       StyleProfile(...)),  # NEW: split from generic flux
    (re.compile(r"flux"),                          StyleProfile(...)),  # Flux 1 dev/pro
    (re.compile(r"pony|score_9|autismmix"),        StyleProfile(...)),  # NEW: mandatory score_* prefix
    (re.compile(r"illustrious|noobai|noob.?ai"),   StyleProfile(...)),  # NEW: precedes animagine
    (re.compile(r"animagine"),                     StyleProfile(...)),
    (re.compile(r"coloring.?book"),                StyleProfile(...)),
    (re.compile(r"juggernaut(?!.*illustrious)"),   StyleProfile(...)),  # tightened
    (re.compile(r"dreamshaperxl.*lightning|dreamshaperxl.*alpha"),
                                                   StyleProfile(...)),
    (re.compile(r"dreamshaperxl|dreamshaper.*xl"), StyleProfile(...)),
    (re.compile(r"dreamshaper"),                   StyleProfile(...)),
    (re.compile(r"sd3|sd_3|sd3_5|sd3\.5"),         StyleProfile(...)),  # NEW: SD3/3.5 (T5)
    (re.compile(r"sd_xl_base|sdxl_base|sdxl-base"),StyleProfile(...)),
    (re.compile(r"realvisxl|realvis"),             StyleProfile(...)),  # NEW
    (re.compile(r"v1[-_]5|sd[-_]?1[-._]?5"),       StyleProfile(...)),
    (re.compile(r""),                              StyleProfile(...)),  # default fallback
)
```

### Resolver

```python
def resolve_style(provider: str, model_id: str) -> StyleProfile | None:
    """Return the StyleProfile for a (provider, model_id) pair, or None.

    Closed-list providers (openai, gemini, placeholder) use exact-key lookup.
    SD WebUI falls back to the regex table; first match wins. Other unknown
    providers return None — they keep working with empty narrative metadata.
    """
    if (hit := MODEL_STYLES.get(f"{provider}:{model_id}")) is not None:
        return hit
    if provider == "sd_webui":
        for pattern, profile in CHECKPOINT_PATTERNS:
            if pattern.search(model_id.lower()):
                return profile
    return None
```

### Audit corrections from questfoundry

The questfoundry table has been in production but a 2026-04-29 audit surfaced
six items that need fixing in our copy:

| Entry | Correction |
|-------|-----------|
| `flux` | Generic regex now incorrectly catches FLUX.2. Add a more-specific FLUX.2 entry above it. Reframe the negative-prompt note from "weak" to "unsupported (CFG=1 distilled)". |
| `flux` | Schnell deserves its own entry — 1-4 step distilled, distinct cost/quality profile. |
| `juggernaut` | Tighten regex to exclude `illustriousJuggernaut*` (anime-base fine-tune that gets mis-classified as photorealistic). |
| `dreamshaperxl.*lightning` | Recommended steps were "4-8"; correct value is "3-6 steps at CFG 2" per Civitai. |
| `sd_xl_base` | Drop "use refiner pass" advice — community abandoned the SDXL refiner ~mid-2024. |
| `v1[-_]5` | Soften "768px ceiling" — SD 1.5 is trained at 512² and routinely upscales beyond 768 with hires-fix. |

New entries added (not in questfoundry):

- `flux.?2|flux2` — FLUX.2 generation.
- `flux.*schnell|.*schnell` — Flux Schnell (split out).
- `pony|score_9|autismmix` — Pony Diffusion XL family. Mandatory leading
  `score_9, score_8_up, ...` token block; without it, output collapses.
- `illustrious|noobai|noob.?ai` — Illustrious-XL / NoobAI-XL anime SDXL bases.
  Have largely supplanted Animagine in 2025-26. Placed before `animagine` so
  fine-tunes route correctly.
- `sd3|sd_3|sd3_5|sd3\.5` — SD 3 / 3.5. Triple-encoder (CLIP + T5); benefits
  from natural-language prose; supports negative prompts (unlike Flux).
- `realvisxl|realvis` — RealVisXL has eclipsed Juggernaut in 2026 SDXL
  photorealism share.

### Architecture-detector fix (folded in)

`sd_webui._detect_architecture()` currently returns `"sd15"` for any
checkpoint not matching SDXL/Lightning/Flux tags. This silently mis-buckets
SD 3 / 3.5 checkpoints as `sd15` and tags them `prompt_style="clip"`, which is
wrong — SD3 uses T5 and prefers `natural_language`. Add an `sd3` branch to
the detector that returns `"sd3"`, with a corresponding preset and
`prompt_style="natural_language"`. Surfaced by the audit; folding into this
PR because it's a one-line fix in code adjacent to the registry change.

## Wiring

Each provider's `discover_capabilities()` calls
`resolve_style(self.provider_name, model_id)` and assigns the result (or
`None`) to the new `style_profile` field on each `ModelCapabilities` it
returns. No other code changes — the new field flows into `list_providers`
JSON automatically via existing `to_dict()` chains.

## MCP surface

### `list_providers` JSON envelope

Two additions:

- **Per-model:** `models[i].style_profile`, omitted when `None`. Otherwise a
  flat object with `label`, `style_hints`, `incompatible_styles`,
  `good_example`, `bad_example`, `lifecycle`, and (when set)
  `deprecation_note`.
- **Top-level:** `warnings: list[str]`, auto-built from any model where
  `lifecycle in {"legacy", "deprecated"}`. Each warning is a single
  human-readable sentence keyed by `"{provider}:{model_id}"`. Empty list when
  no warnings apply (always present, never absent — stable schema).

Example deprecation entry:

```text
"openai:dall-e-3 — deprecated, OpenAI API removal 2026-05-12. Migrate to gpt-image-1.5 or later for new work."
```

### `generate_image` tool docstring

A new paragraph (≈40 words) is added next to the existing `prompt_style`
pointer:

> When picking `model`, consult `list_providers` — each model carries
> `style_profile.style_hints` (what it's good for) and
> `style_profile.incompatible_styles` (what fights it), plus a `lifecycle`
> flag. Top-level `warnings` lists deprecated models to avoid for new work.

This is the reliable LLM channel per session memory; the equivalent text is
not added to the `select_provider` MCP prompt because that prompt is not
auto-injected by all clients.

## Generated docs page

A new `scripts/render_model_catalog.py` mirrors the existing
`scripts/bump_manifests.py` pattern:

- **Imports** `MODEL_STYLES` and `CHECKPOINT_PATTERNS` from the registry.
- **Writes** `docs/providers/model-catalog.md`.
- **Page structure:**
  - Preamble describing how matching works (exact-key for closed providers,
    regex-ordered for SD WebUI).
  - Per-provider section (OpenAI, Gemini, placeholder): summary table —
    `model_id | label | lifecycle | prompt_style | supports_negative_prompt | supports_background` —
    followed by per-model collapsible details (`<details>` blocks) with
    hints, incompatibility notes, and good/bad examples.
  - SD WebUI section: pattern catalog in match order, showing the regex,
    label, and the same fields. Documents the "specific-before-generic" and
    "empty-pattern-last" invariants.

**CI drift-guard:** `docs.yml` gains a step that runs the script and `git
diff --exit-code docs/providers/model-catalog.md`. Fails the build if anyone
edits the registry without regenerating. Same discipline as
`bump_manifests.py`.

**Pre-commit hook:** add an entry that re-runs the renderer when
`model_styles.py` or `render_model_catalog.py` changes.

**mkdocs `nav`:** add `"Model Catalog": providers/model-catalog.md` under
Providers, before "Placeholder".

## Documentation impact (per CLAUDE.md)

| File | Change |
|------|--------|
| `docs/providers/model-catalog.md` | New, generated from registry |
| `docs/tools.md` | Document new `style_profile` field and `warnings` array on `list_providers` |
| `docs/resources.md` | Same for `info://providers` |
| `docs/providers/index.md` | Link to the catalog page |
| `docs/guides/prompt-writing.md` | One-line pointer to the catalog (don't duplicate per-model detail) |
| `docs/decisions/0009-model-style-metadata.md` | New ADR — captures exact-lookup-with-regex-fallback rationale, lifecycle field, audit-driven changes |
| `CHANGELOG.md` | Picked up automatically by semantic-release from `feat:` commit |

## Testing

New `tests/test_model_styles.py`:

- Each `MODEL_STYLES` key resolves to non-`None` with non-empty `style_hints`
  and `incompatible_styles`.
- Empty-pattern fallback always matches an arbitrary string
  (`resolve_style("sd_webui", "completely-unknown-checkpoint-name")` returns a
  profile, never `None`).
- Pattern-ordering invariants:
  - `flux2_dev_nf4` → FLUX.2 entry, not generic Flux.
  - `flux1_schnell_nf4` → Schnell entry, not generic Flux or FLUX.2.
  - `dreamshaperxl_v2_lightning` → Lightning entry, not generic DreamShaperXL.
  - `illustriousJuggernaut_xl` → Illustrious entry, not Juggernaut.
  - `pony_v6_xl` → Pony entry.
  - `sd3_5_large` → SD3 entry.
- Resolver returns `None` for unknown providers
  (`resolve_style("future-provider", "any-model")`).

Extensions to existing tests:

- `tests/test_capabilities.py`: round-trip `to_dict()` for the new nested
  shape (key omitted when `None`, flat sub-dict when present).
- `tests/test_sd_webui_provider.py` (or `_discovery`): assert
  `discover_capabilities()` populates `style_profile` for at least one
  checkpoint.
- `tests/test_openai_discovery.py`, `tests/test_gemini_discovery.py`: same
  assertion for those providers.
- `tests/test_tools.py`: `list_providers` JSON contains `style_profile` for
  configured models and a populated `warnings` list when a deprecated model is
  configured (use `dall-e-3` as the fixture).
- `tests/test_sd_webui_provider.py`: assert `_detect_architecture("sd3_5_large")`
  returns `"sd3"` and the corresponding preset has
  `prompt_style="natural_language"`.

## Out of scope

Filed as separate issues in the same session (per CLAUDE.md "PR workflow"):

1. **Refresh `_SELECT_PROVIDER_PROMPT` and `_PROMPT_GUIDE`** with the current
   2026 model lineup. The static prompt text overlaps with the new metadata;
   refactoring it to consume the registry (or to be hand-edited in sync) is a
   focused follow-up PR.
2. **Add `gpt-image-2` to OpenAI provider config** when OpenAI ships it. The
   provider already supports `gpt-image-1`, `gpt-image-1-mini`,
   `gpt-image-1.5`, `dall-e-3`, and `dall-e-2`; this PR's registry covers all
   of those plus the three Gemini variants already in `_KNOWN_IMAGE_MODELS`.
3. **Surface the SynthID watermark** as a `watermark: "synthid"` capability
   field on `gemini-2.5-flash-image`. Distinct addition to the capability
   schema.

## Risks / open considerations

- **Registry drift.** Hand-curated metadata for fast-moving fine-tunes goes
  stale. Mitigation: empty-pattern fallback always matches; the docs page
  makes drift visible in PR diffs; encourage updates as new fine-tunes get
  used (rather than chasing every Civitai release).
- **Tool-description bloat.** ≈40 extra words on `generate_image` is small but
  not free. Acceptable cost given the memory-confirmed reliability advantage
  over MCP prompts.
- **Pattern-ordering bugs.** The regex table is order-sensitive. Tests pin the
  most fragile orderings; the audit table documents the invariants
  ("specific-before-generic"); the ADR records the discipline.
- **`prompt_style` axis is coarse.** Conflates "tag grammar" with "supports
  negative prompts" in some readers' intuitions. Not changed in this PR (the
  capability schema already has a separate `supports_negative_prompt` field).
  The new `style_profile.style_hints` text is the natural place to call out
  grammar quirks like Pony's score-prefix mandate.

## References

- Source pattern: [`pvliesdonk/questfoundry`/`checkpoint_styles.py`][qf]
- Repo memory `project_live_test_findings_2026_03_20.md` — gap that motivated this work
- Repo memory `feedback_mcp_prompts_not_injected.md` — channel-reliability constraint
- ADR-0007 (provider capability model) — what `ModelCapabilities` is for
- ADR-0008 (style library) — different concept ("user-saved creative briefs"); cross-referenced in ADR-0009 to disambiguate naming
