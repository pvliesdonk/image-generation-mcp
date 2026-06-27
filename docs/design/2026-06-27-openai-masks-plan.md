# OpenAI inpainting masks (Issue #261) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an optional `mask` reference to `transform_image`, plumbed only to OpenAI gpt-image models that advertise `supports_mask`; other providers reject a mask with a clear error.

**Architecture:** The foundation threads `reference_images` and `strength` through `ImageProvider.generate()` → `ImageService.generate()` → `_start_background_generation` → the `transform_image` tool. This adds a `mask` (a single resolved `InputImage`) along the same path, resolved via the existing resolver, and a `supports_mask` dimension to the tool's capability routing. OpenAI's `_edit` forwards the mask to `images.edit(mask=...)`. Gemini, SD WebUI, and placeholder reject a mask.

**Tech Stack:** Python 3.11+, the `openai` AsyncOpenAI SDK (`images.edit(mask=...)`), pytest, uv, ruff, mypy.

## Global Constraints

- Python 3.11+; full type hints; Google-style docstrings.
- `logging.getLogger(__name__)`; no f-strings in log calls (lazy `%s`, event-name-first); no bare `except`.
- Hard gates before push: `uv run pytest -x -q`; `uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .`; `uv run mypy src/ tests/`; patch coverage ≥ 80%; docs updated.
- TDD: failing test first → implement → pass → commit. Conventional commits with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **OpenAI mask API** (verified): `client.images.edit(model=, image=<file>, mask=<file>, prompt=...)`. The mask must be the same format and size as the image and carry an alpha channel; OpenAI enforces this and returns a 400 otherwise (surfaced as `ImageProviderError`). If multiple input images are supplied, the mask applies to the first. `mask` accepts a `(filename, bytes, content_type)` file tuple like `image`.
- **Capability facts:** the gpt-image family (gpt-image-2/1.5/1/1-mini) has `supports_mask=True` AND `supports_image_input=True`. dall-e-3 has neither relevant; dall-e-2 has `supports_mask=True` but `supports_image_input=False` (so it never routes for `transform_image`). Gemini/SD/placeholder have `supports_mask=False`.

## Scope decisions
- `mask` is a single reference (one image), resolved like a `reference_images` entry. It is only meaningful with `reference_images` (which `transform_image` already requires), so no separate "mask needs a base image" check is needed.
- Only providers/models advertising `supports_mask` accept a mask; the tool gates routing on it and other providers reject it defensively.
- No alpha-channel / size validation in this server (OpenAI enforces it; a mismatch surfaces as a provider error).

---

## File Structure

- **Modify** `src/image_generation_mcp/providers/types.py` — add `mask: InputImage | None = None` to the `ImageProvider.generate()` protocol signature + docstring.
- **Modify** `src/image_generation_mcp/service.py` — add `mask` to `ImageService.generate()`, pass through.
- **Modify** `src/image_generation_mcp/_server_tools.py` — add `mask: str | None = None` to `_start_background_generation` (pass-through) and the `transform_image` tool: resolve the mask reference, add `supports_mask` to the auto `eligible` and `capable` filters when a mask is supplied, and forward the resolved mask. Pass `mask` provenance (its `source_id`) into `source_image_ids` too if present (optional; see Task 1).
- **Modify** `src/image_generation_mcp/providers/openai.py` — `generate()` forwards `mask` to `_edit`; `_edit` accepts `mask: InputImage | None` and sends it to `images.edit(mask=...)` as a file tuple.
- **Modify** `src/image_generation_mcp/providers/gemini.py`, `providers/sd_webui.py`, `providers/placeholder.py` — accept `mask`; raise `ImageProviderError(<name>, "mask is not supported by this provider")` when a mask is supplied.
- **Tests:** `tests/test_tools.py`, `tests/test_openai_provider.py`, `tests/test_gemini_provider.py`, `tests/test_sd_webui_provider.py`, `tests/test_placeholder.py`, `tests/test_service.py`.
- **Docs:** `docs/providers/openai.md`, `docs/tools.md`.

---

## Task 1: Thread `mask` through the protocol, service, tool routing, and non-OpenAI providers

**Files:** `providers/types.py`, `service.py`, `_server_tools.py`, `providers/gemini.py`, `providers/sd_webui.py`, `providers/placeholder.py`; tests `tests/test_tools.py`, `tests/test_service.py`, `tests/test_gemini_provider.py`, `tests/test_sd_webui_provider.py`, `tests/test_placeholder.py`.

**Interfaces:**
- Produces: `mask: InputImage | None = None` on `ImageProvider.generate()`, `ImageService.generate()`, `_start_background_generation()`; a `mask: str | None = None` (reference string) on the `transform_image` tool. The tool resolves the mask, restricts routing to `supports_mask` models when a mask is given, and forwards the resolved `InputImage`. gemini/sd/placeholder raise `ImageProviderError` when a mask reaches them.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tools.py` `TestTransformImageTool` (use the existing image-input-capable harness):
- `test_transform_image_mask_requires_supports_mask`: register an image-input-capable provider whose model has `supports_mask=False` (e.g. a fake "gemini"-style model), register two gallery images (base + mask), call `transform_image(provider=<that>, reference_images=[base_id], mask=mask_id)` → `pytest.raises(ValueError, match="mask")`. (The model supports image input but not masks.)
- `test_transform_image_mask_unknown_reference`: image-input + mask-capable provider configured; pass `mask="deadbeef0000"` (unknown) → `ValueError` containing "not found".

In `tests/test_service.py`: `ImageService.generate(..., mask=<InputImage>)` forwards `mask=` to the provider (AsyncMock; assert `fake.generate.call_args.kwargs["mask"]` is the InputImage).

In `tests/test_gemini_provider.py`, `tests/test_sd_webui_provider.py`, `tests/test_placeholder.py`: passing a `mask` to the provider's `generate()` raises `ImageProviderError` matching "mask". Example (placeholder):
```python
async def test_placeholder_rejects_mask() -> None:
    from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
    from image_generation_mcp.providers.types import ImageProviderError, InputImage

    with pytest.raises(ImageProviderError, match="mask"):
        await PlaceholderImageProvider().generate(
            "x", mask=InputImage(data=b"m", content_type="image/png")
        )
```
For gemini/sd, construct as their existing tests do (`GeminiImageProvider(api_key="AIza-test")`, `SdWebuiImageProvider(host=...)`) and pass `mask=InputImage(...)` → `ImageProviderError` match "mask". (No HTTP/SDK mock needed; the guard raises first.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k mask tests/test_service.py -k mask tests/test_placeholder.py -k mask tests/test_gemini_provider.py -k mask tests/test_sd_webui_provider.py -k mask -v`
Expected: FAIL — `generate()`/tool don't accept `mask` yet.

- [ ] **Step 3: Implement the plumbing**

**`providers/types.py`** — add `mask: InputImage | None = None` (before `progress_callback`) to the `ImageProvider.generate()` protocol; document: "Optional mask image for inpainting. Only OpenAI gpt-image models support it; other providers raise `ImageProviderError`. Applies to the first reference image."

**`service.py`** — add `mask: InputImage | None = None` to `ImageService.generate()` (before `progress_callback`); pass `mask=mask` to `resolved_provider.generate(...)`; document.

**`_server_tools.py`**:
- Add `mask: InputImage | None = None` to `_start_background_generation(...)` and forward it in its `service.generate(...)` call.
- In the `transform_image` tool: add `mask: str | None = None` to the signature (after `strength`). After the references are resolved, resolve the mask when provided:
  ```python
        resolved_mask: InputImage | None = None
        if mask is not None:
            try:
                resolved_mask = (
                    await asyncio.to_thread(
                        resolve_references,
                        [mask],
                        loader=_loader,
                        allow_local_files=config.allow_local_file_input,
                        max_bytes=config.max_input_image_bytes,
                    )
                )[0]
            except (
                ImageReferenceNotFound,
                LocalFileInputDisabled,
                InputImageTooLarge,
                InvalidInputImage,
            ) as exc:
                raise ValueError(str(exc)) from exc
  ```
  (Reuse the existing `_loader`; it is defined before this point.)
- Add the `supports_mask` requirement to BOTH the auto `eligible` filter and the `capable` filter — only when a mask is supplied:
  ```python
  # in the eligible generator:
  if any(
      m.supports_image_input
      and m.max_input_images >= len(resolved)
      and (mask is None or m.supports_mask)
      for m in caps.models
  )
  # in the capable list comprehension:
  if m.supports_image_input
  and (model is None or m.model_id == model)
  and m.max_input_images >= len(resolved)
  and (mask is None or m.supports_mask)
  ```
- Update the `eligible`-empty and `capable`-empty error messages to mention masks when `mask is not None`, e.g. append " (a mask requires a mask-capable model)".
- Pass `mask=resolved_mask` into `_start_background_generation(...)`. Include the mask's `source_id` in `source_ids` provenance when present (`if resolved_mask and resolved_mask.source_id: source_ids.append(resolved_mask.source_id)`).
- Document the `mask` parameter in the tool docstring (single reference; inpainting; only mask-capable providers, currently OpenAI gpt-image; applies to the first reference image).

**`gemini.py`, `sd_webui.py`, `placeholder.py`** — add `mask: InputImage | None = None` to `generate()`; near the top (after the reference-image handling), add:
```python
        if mask is not None:
            raise ImageProviderError(
                "<provider>", "mask is not supported by this provider"
            )
```
Use the provider name string. (gemini/placeholder import `ImageProviderError` from `.types`; sd_webui already imports it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py tests/test_service.py tests/test_gemini_provider.py tests/test_sd_webui_provider.py tests/test_placeholder.py -q`
Expected: PASS.

- [ ] **Step 5: Full gates + commit**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
git add src/image_generation_mcp/ tests/
git commit -m "feat: thread mask param through transform_image; non-OpenAI providers reject it

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: OpenAI `_edit` consumes the mask

**Files:** `src/image_generation_mcp/providers/openai.py`; `tests/test_openai_provider.py`.

**Interfaces:**
- Consumes: `mask: InputImage | None` (Task 1), `_ext_for`.
- Produces: OpenAI `generate()` forwards `mask` to `_edit`; `_edit` sends `mask=(filename, bytes, content_type)` to `images.edit` when a mask is present.

- [ ] **Step 1: Write the failing tests** (in `tests/test_openai_provider.py` `TestOpenAIEdit`, mirror the existing edit tests)
- `test_edit_with_mask_sends_mask_file`: call `generate("inpaint", reference_images=[InputImage(b"img","image/png")], mask=InputImage(b"msk","image/png"))`; assert `images.edit` was awaited with a `mask` kwarg that is a `(filename, b"msk", "image/png")` tuple, and `image` is the references list.
- `test_edit_without_mask_omits_mask_kwarg`: call edit with no mask; assert `"mask" not in images.edit.call_args.kwargs`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_openai_provider.py -k mask -v`
Expected: FAIL — `_edit` doesn't accept/forward `mask`.

- [ ] **Step 3: Implement**

In `openai.py`:
- `generate()`: it already dispatches `if reference_images: return await self._edit(...)`. Add `mask=mask` to that `_edit(...)` call (and `generate()` already receives `mask` from the protocol — confirm the signature has it from Task 1; the provider's concrete `generate()` must include `mask: InputImage | None = None`).
- `_edit(...)`: add `mask: InputImage | None = None` parameter. After building the `image=[...]` kwarg, add:
  ```python
        if mask is not None:
            kwargs["mask"] = (
                f"mask{_ext_for(mask.content_type)}",
                mask.data,
                mask.content_type,
            )
  ```
- Update the `_edit` docstring (mask: optional inpainting mask sent to images.edit; must match the first image's size/format with an alpha channel, enforced by OpenAI).

> Note: `_edit` is gpt-image-only (guarded). gpt-image models all advertise `supports_mask=True`, and the tool only routes a mask to a mask-capable model, so a mask reaching `_edit` is always valid at the routing layer.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openai_provider.py -q`
Expected: PASS (mask tests + existing edit/generate tests unchanged).

- [ ] **Step 5: Full gates + commit**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
git add src/image_generation_mcp/providers/openai.py tests/test_openai_provider.py
git commit -m "feat(openai): forward inpainting mask to images.edit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Documentation

**Files:** `docs/providers/openai.md`, `docs/tools.md`.

- [ ] **Step 1: Document**

In `docs/providers/openai.md`, update the "Masks" section: masks are now supported via `transform_image`'s `mask` parameter for the gpt-image family. The mask must match the first reference image's size and format and carry an alpha channel (OpenAI enforces this). Replace the prior "does not send a mask" wording.

In `docs/tools.md`, document the `mask` parameter on `transform_image`: a single reference (gallery id / `image://` URI / local file path) used as an inpainting mask; only mask-capable providers accept it (currently OpenAI gpt-image; check `supports_mask` in `list_providers`); applies to the first reference image.

**Vale-clean** on added lines (no em-dashes, no "e.g."/"i.e.", no "**Note:**", no three-verb lists). Run `vale sync` then `vale --minAlertLevel=error docs/providers/openai.md docs/tools.md`; add genuine terms (e.g. `inpainting`) to `.vale/styles/config/vocabularies/Base/accept.txt` if needed (it may already be present).

- [ ] **Step 2: Verify + commit**

```bash
uv run mkdocs build 2>&1 | tail -5
vale --minAlertLevel=error docs/providers/openai.md docs/tools.md
git add docs/providers/openai.md docs/tools.md
git commit -m "docs: document the transform_image mask parameter (OpenAI inpainting)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Pre-PR verification

- [ ] `uv run pytest -x -q` pass; ruff/format clean; `uv run mypy src/ tests/` clean.
- [ ] `uv run pytest --cov=image_generation_mcp.providers.openai --cov=image_generation_mcp._server_tools --cov-report=term-missing` — patch coverage ≥ 80% (mask resolution, supports_mask routing, non-OpenAI rejection, _edit mask forwarding).
- [ ] Grep for any provider-name-hardcoded user-facing string introduced (lesson from #263/#265/#260); keep cross-provider guidance generic where possible.
- [ ] Run `preflight-circus` against `BASE..HEAD` (or an opus whole-branch review) before `gh pr create`.
- [ ] PR body: `Closes #261`, `Refs #256`, agent-attribution signature; note Vale red is the known #244 gate (non-blocking) if it shows on the new plan doc.

## Self-Review notes (author)
- `mask` threaded exactly like `strength`/`reference_images` but as a single resolved `InputImage`; consumed only by OpenAI gpt-image; other providers reject it.
- Routing gains a `supports_mask` requirement (auto `eligible` + explicit `capable`) only when a mask is supplied; error messages mention masks.
- `transform_image` already requires `reference_images`, so a mask always has a base image — no separate guard needed.
- Mask provenance (`source_id`) folded into `source_image_ids`.
