# ADR-0009: Per-model style metadata via exact-key lookup with regex fallback

## Status

Accepted

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

## Considered Alternatives

**Per-provider local style tables.** Each provider holds its own static
metadata inline. Rejected: three small tables drift apart; regex matching
code would be duplicated; adding a new provider is more work; cross-
provider semantic consistency (`lifecycle` enum) becomes fragile.

**Pure regex matching for everything.** All providers use the regex
table. Rejected: regex over `gpt-image-1` is theatre -- those are exact
strings; regex adds ordering pitfalls and obscures intent. The mechanism
should match the data shape.

**Static markdown blob per model.** Hand-write one markdown file per
model and serve it from a separate resource. Rejected: not visible in
`list_providers` JSON, which is the LLM channel that actually matters;
duplicates the data; harder to keep in sync with code.

## Consequences

### Positive

- Single source of truth for narrative metadata
- Closed-list providers get O(1) lookup
- SD WebUI keeps the proven pattern from questfoundry (with audit fixes)
- The generated docs page makes drift visible in PR diffs
- Lifecycle field gives a structured channel for deprecation warnings
  without polluting the schema with one-off bool fields

### Negative

- Hand-curated metadata for fast-moving fine-tunes goes stale.
  Mitigation: empty-pattern fallback always matches; the docs page makes
  drift visible; updates are encouraged when a checkpoint is actually
  being used (not chasing every Civitai release).

### Schema axis is now richer

The capability schema now has both `prompt_style` (grammar -- clip vs
natural_language) and `style_profile.style_hints` (purpose). These are
orthogonal; the narrative `style_hints` is the natural place to call out
grammar quirks that don't fit the binary axis (e.g. Pony's mandatory
`score_*` prefix).

## Disambiguation: ADR-0008 (style library) vs this ADR

ADR-0008's "style library" is **user-facing creative briefs** -- saved
markdown files with tags / aspect-ratio / quality fields that the user
applies to a generation request. This ADR's `StyleProfile` is **per-model
metadata** -- what each model is good for. The two never interact:
`StyleProfile` describes the model; the style library describes a brief.
Both happen to use the word "style" in their everyday English sense.

## References

- Spec: `docs/design/2026-04-29-model-style-metadata.md`
- Plan: `docs/design/2026-04-29-model-style-metadata-plan.md`
- Source pattern: `pvliesdonk/questfoundry`/`src/questfoundry/providers/checkpoint_styles.py`
- Tracking issue: #203
