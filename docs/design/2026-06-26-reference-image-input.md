# Epic: Reference-image input (image-to-image, composition, transform)

**Date:** 2026-06-26
**Status:** Design approved, awaiting spec review
**Type:** Epic (multiple issues / PRs across one milestone)

## Motivation

The server generates images well, but generation is **text-only**. The
`edit_image` tool only performs local crop/rotate/flip — it does not feed an
image back into a model. Every "power user" capability in the reference
projects ([Ibrahim-3d/nano-banana-claude-plugin](https://github.com/Ibrahim-3d/nano-banana-claude-plugin),
[kingbootoshi/nano-banana-2-skill](https://github.com/kingbootoshi/nano-banana-2-skill))
— background replacement, object removal, style transfer, character
consistency, iterative refinement — is downstream of one missing primitive:
**feeding images *into* generation**.

This epic adds that primitive across the existing provider abstraction.
Gemini's nano-banana models are purpose-built for it; OpenAI (`images.edit`)
and SD WebUI (`img2img`) support it too. The work is sequenced so the first
PR ships a working end-to-end image-to-image slice, and later PRs widen
provider and sub-feature coverage.

## Scope decisions (from brainstorming)

- **Input sources:** gallery `image_id` / `image://` URI **and** local file
  path. File-path input is gated behind a default-off config flag so
  HTTP/remote deployments (server does not share the user's filesystem)
  reject it cleanly instead of reading a server-side path.
- **Tool surface:** a **new dedicated tool** `transform_image`.
  `generate_image` stays text-only. (`edit_image` is already taken by the
  local crop/rotate editor.)
- **Providers:** all three — Gemini, OpenAI, SD WebUI — but sequenced across
  separate issues, Gemini first.
- **Edge sub-features** (multi-image composition, OpenAI inpainting masks, SD
  denoising strength): all deferred to their own follow-up issues, not the
  foundation PR.

## Core architecture

Four provider-agnostic pieces underpin every slice.

### 1. Image-reference resolution helper

New module `src/image_generation_mcp/_input_images.py`.

- `InputImage` value object: `data: bytes`, `content_type: str`,
  `source_id: str | None` (the gallery id when resolved from the store,
  else `None`).
- `resolve_reference(ref: str, *, allow_local_files: bool) -> InputImage`:
  - `image://…` URI or bare `image_id` → load full-resolution bytes from the
    existing image store (pre-transform original, not a thumbnail). Unknown
    id → typed `ImageReferenceNotFound`.
  - local file path → read from disk **only if `allow_local_files`**; else
    raise `LocalFileInputDisabled` with a message pointing at the config
    flag. Path is read as-is (no traversal sanitization needed beyond what
    the OS enforces — the flag is the trust boundary, documented as
    "enable only when the operator trusts callers with server FS access").
  - Validates decoded MIME is an image and byte size ≤ a configurable cap
    (`IMAGE_GENERATION_MCP_MAX_INPUT_IMAGE_BYTES`, sane default e.g. 20 MiB).
- This is the **only** module that knows about input sources. Adding base64
  or URL sources later is a localized change here plus a capability bump.

Config additions (in the `CONFIG-FIELDS` / `CONFIG-FROM-ENV` sentinels of
`config.py`, read via `env(_ENV_PREFIX, …)`):
- `allow_local_file_input: bool` — `IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT`, default `False`.
- `max_input_image_bytes: int` — `IMAGE_GENERATION_MCP_MAX_INPUT_IMAGE_BYTES`, default `20 * 1024 * 1024`.

### 2. Provider protocol extension

Extend the existing `ImageProvider.generate()` signature with an optional
`reference_images: Sequence[InputImage] | None = None` — **not** a parallel
`transform()` method. Rationale: the background-task runner, progress
callbacks, and result handling pass it straight through unchanged; the model
treats an edit/compose as the same generation call.

- A provider that does not support image input and receives a non-empty
  `reference_images` raises a typed `ImageInputUnsupported(provider, model)`.
- A provider that receives more references than it supports raises
  `TooManyInputImages(provider, model, max_input_images)`.
- `reference_images=None` or `[]` → existing text-to-image behavior, byte for
  byte unchanged. (Regression-tested.)

### 3. New MCP tool: `transform_image`

Mirrors `generate_image`'s background/task + `ResourceLink` pattern.

Parameters: `prompt`, `reference_images: list[str]` (gallery ids/URIs and/or
file paths, 1..N), `provider` ("auto"|…), `model`, `negative_prompt`,
`aspect_ratio`, `quality`, `background`.

Behavior:
- Resolves each reference via the helper **before** enqueuing the background
  task, so resolution errors surface synchronously to the caller (not as an
  opaque async failure).
- Validates the chosen provider/model advertises `supports_image_input` and
  enough `max_input_images`; otherwise returns a clear error naming a model
  that does (e.g. "use a Gemini model for multi-image composition").
- Records source id(s) into provenance so the gallery shows lineage.
- Tagged `tags={"write"}` like `generate_image`; hidden in read-only mode.
- The tool is **only registered** when ≥1 configured provider reports
  `supports_image_input` — no dead tool on a placeholder-only deployment.

### 4. Capability metadata

Add to `ProviderCapabilities` / `ModelCapabilities` (surfaced via
`list_providers` and `info://providers`):
- `supports_image_input: bool`
- `max_input_images: int` (0 when unsupported; 1 for single-image edit; >1
  for Gemini composition once implemented)

This is how the LLM routes: it can see that composition (≥2 inputs) requires
a Gemini model while single-image edits work on OpenAI/SD too.

### Provenance

The metadata sidecar currently has a singular `source_image_id`. Generalize
to `source_image_ids: list[str]` (resolved gallery ids only; file-path
sources contribute no id). Keep reading the legacy singular field for
backward compatibility on existing stored images.

## Issue sequencing

Six issues, one milestone (under the 10-issue epic cap). Each PR closes its
issue, passes all hard gates (CI, lint, mypy, ≥80% patch coverage, docs),
and follows TDD — failure modes enumerated and tested before implementation.

**Issue 1 — Foundation + Gemini single-image i2i (first PR, vertical slice).**
Delivers a working end-to-end edit. Includes: `_input_images.py` + config
flags; `generate()` protocol extension + `ImageInputUnsupported` /
`TooManyInputImages` / `ImageReferenceNotFound` / `LocalFileInputDisabled`
errors; capability fields; the `transform_image` tool; Gemini provider image
input (single reference; `max_input_images = 1` for this issue); provenance
`source_image_ids`; docs (README tool table, `docs/tools.md`,
`docs/configuration.md` for the two new env vars, `docs/providers/gemini`).
Rationale for bundling: a protocol extension with no consumer is not
independently shippable or meaningfully testable; the vertical slice is the
smallest coherent, releasable unit.

**Issue 2 — OpenAI gpt-image image editing.** Implement `reference_images`
for the OpenAI provider via the `images.edit` endpoint (single init image,
`max_input_images = 1`). Capability + docs (`docs/providers/openai`).

**Issue 3 — SD WebUI img2img + denoising strength.** Implement
`reference_images` for SD WebUI via the `img2img` endpoint. Add an optional
`strength: float` (0–1) param to `transform_image`, used only by SD (ignored
with a debug log by others). Document the param's provider scope. Capability
+ docs (`docs/providers/` SD page, `docs/tools.md` for the new param).

**Issue 4 — Gemini multi-image composition.** Raise Gemini's
`max_input_images` (>1, per current model docs) and exercise N-reference
composition (character consistency). Tests for the per-provider cap
enforcement (`TooManyInputImages` on OpenAI/SD when N>1). Docs: composition
workflow + character-consistency guidance in the Gemini provider page and
prompt guidance.

**Issue 5 — OpenAI inpainting masks.** Add an optional `mask` reference
(second image-input dimension) to `transform_image`, plumbed only to OpenAI
gpt-image models that advertise `supports_mask`. Capability already exists;
wire the mask through resolution + provider. Docs.

**Issue 6 — Documentation closeout + prompt guidance.** Cross-cutting docs
pass: `docs/design.md` architecture update for the image-input primitive, an
image-input workflows page (edit / style transfer / composition / masking),
and any `sd_prompt_guide` / provider-selection prompt updates that reference
the new capability. (Per-issue docs land with each PR; this issue catches
the cross-cutting site narrative.)

### Deferred to a future epic (explicitly out of scope here)

- **Iterative / conversational editing sessions** (persistent refine loop).
  Becomes natural once `transform_image` + gallery provenance exist (feed the
  output id back as the next input), but session state is its own design.
- **Additional input sources** (base64 inline, public URL) — localized to
  `_input_images.py` when wanted.
- Cost tracking, search-grounded generation, 512px tier, exact-dimension
  blank-reference trick (the non-image-input "quick wins" from the survey).

## Testing strategy (applies to every issue)

Per project TDD discipline, enumerate and test failure modes before
implementing. Known modes to cover:

- **Resolution:** unknown image_id; `image://` URI vs bare id; file path with
  flag off (rejected) vs on (read); oversized image (cap exceeded);
  non-image bytes; missing file.
- **Routing/capability:** provider/model without `supports_image_input`
  (`ImageInputUnsupported`); N references exceeding `max_input_images`
  (`TooManyInputImages`); `reference_images=[]`/`None` falls back to exact
  text-to-image behavior (regression).
- **Tool contract:** synchronous resolution errors surface before task
  enqueue; provenance `source_image_ids` recorded (gallery ids only,
  file-path sources omitted); tool absent when no provider supports input.
- **Lifecycle/ordering:** resolution happens before enqueue; background task
  receives already-resolved bytes (no late disk/store reads inside the task).
- **Per provider:** API request shape carries the reference bytes; provider
  error → user-facing error string (not an unhandled exception).

## Open items for the implementation plan

- Exact `transform_image` parameter JSON schema and description wording
  (descriptions are the primary LLM channel — see project memory on
  claude.ai not injecting MCP prompts).
- Whether `reference_images` accepts mixed gallery-id + file-path entries in
  one call (default: yes; the resolver handles each independently).
- Final default for `max_input_images` on Gemini in Issue 4 (verify against
  current Gemini image API docs at implementation time).
