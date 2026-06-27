# OpenAI gpt-image image editing (Issue #258) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement reference-image input for the OpenAI provider via the `images.edit` endpoint, so `transform_image` can do image-to-image edits and multi-image composition (up to 16 references) on the gpt-image family.

**Architecture:** The foundation (PR #263) already added `reference_images` to `ImageProvider.generate()`, the `transform_image` tool (capability-routed), and `InputImage`. The OpenAI provider currently *rejects* `reference_images` with `ImageInputUnsupported`. This issue replaces that rejection (for edit-capable gpt-image models) with a real `images.edit` call, and advertises `supports_image_input` / `max_input_images=16` so the tool routes correctly. No tool-layer changes are needed.

**Tech Stack:** Python 3.11+, the `openai` AsyncOpenAI SDK (`client.images.edit`), pytest (SDK mocked via the `_mock_openai` conftest fixture), uv, ruff, mypy.

## Global Constraints

- Python 3.11+; full type hints; Google-style docstrings on public functions.
- `logging.getLogger(__name__)`; no f-strings in log calls (lazy `%s`); no bare `except` (catch specific types — the provider funnels SDK errors through `_handle_error`).
- Hard gates before any push: `uv run pytest -x -q`; `uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .`; `uv run mypy src/ tests/`; patch coverage ≥ 80%; docs updated.
- TDD: failing test first, watch it fail, implement, watch it pass, commit.
- Conventional commits ending with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Verified API facts** (OpenAI docs, 2026-06-27): `client.images.edit(model=, image=<FileTypes | list[FileTypes]>, prompt=, size=, quality=, n=, background=, output_format=)` returns `data[0].b64_json`. GPT image models accept **up to 16** reference images. `image` FileTypes accepts a `(filename, bytes, content_type)` tuple. `mask` and `input_fidelity` are OUT OF SCOPE (mask = #261; omit input_fidelity — gpt-image-2 disallows changing it). Only gpt-image-* support this no-mask reference edit; dall-e-3 has no edit, dall-e-2 edit is mask-only.

## Scope decisions

- OpenAI `max_input_images = 16` (API native), multi-image composition supported. (#260 remains Gemini-specific.)
- Edit applies to gpt-image-2 / gpt-image-1.5 / gpt-image-1 / gpt-image-1-mini only. dall-e-3 and dall-e-2 keep `supports_image_input=False` → `ImageInputUnsupported`.
- No `transform_image` tool changes (already capability-routed). No mask support.

---

## File Structure

- **Modify** `src/image_generation_mcp/providers/openai.py` — add `_MAX_INPUT_IMAGES = 16`; advertise `supports_image_input` / `max_input_images` on the four gpt-image models; dispatch `generate()` to a new `_edit()` path when `reference_images` is non-empty; share request-param building between generate and edit; raise `TooManyInputImages` / `ImageInputUnsupported` appropriately.
- **Modify** `tests/test_openai_provider.py` — update the now-incorrect `test_openai_rejects_reference_images` (gpt-image now *supports* edit); add edit-path tests.
- **Modify** `tests/test_openai_discovery.py` — assert the new capability fields.
- **Modify** `docs/providers/openai.md`, `docs/tools.md` — document OpenAI image input/composition.

---

## Task 1: OpenAI capability fields for image input

**Files:**
- Modify: `src/image_generation_mcp/providers/openai.py` (module constant + `discover_capabilities`)
- Test: `tests/test_openai_discovery.py`

**Interfaces:**
- Produces: `_MAX_INPUT_IMAGES = 16` (module constant); the four gpt-image `ModelCapabilities` carry `supports_image_input=True, max_input_images=16`; dall-e-3/dall-e-2 keep the defaults (`False`/`0`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_openai_discovery.py` (match the file's existing discovery-test harness — it builds a provider with `models.list` mocked to return the known ids, then awaits `discover_capabilities()`; mirror an existing test's mock setup):

```python
async def test_gpt_image_models_advertise_image_input() -> None:
    provider = _provider_with_models(  # reuse this file's existing helper/pattern
        {"gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini", "dall-e-3"}
    )
    caps = await provider.discover_capabilities()
    by_id = {m.model_id: m for m in caps.models}
    for mid in ("gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"):
        assert by_id[mid].supports_image_input is True
        assert by_id[mid].max_input_images == 16
    # dall-e-3 has no edit support
    assert by_id["dall-e-3"].supports_image_input is False
    assert by_id["dall-e-3"].max_input_images == 0
```

> If `tests/test_openai_discovery.py` has no `_provider_with_models` helper, follow the actual pattern the file uses to mock `models.list()` (e.g. setting `provider._client.models.list = AsyncMock(return_value=...)` with objects exposing `.id`). The requirement is: discover with the gpt-image ids present and assert the four new capability values.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_openai_discovery.py -k image_input -v`
Expected: FAIL — `supports_image_input` is `False`/`max_input_images` is `0` for the gpt-image models (foundation defaults).

- [ ] **Step 3: Implement**

In `openai.py`, add the module constant near the other constants (after `_NO_BACKGROUND_GPT_IMAGE`):

```python
# OpenAI's images.edit endpoint accepts up to 16 reference images for the
# gpt-image family (multi-image composition). dall-e-3 has no edit endpoint;
# dall-e-2 edit is mask-only (out of scope here).
_MAX_INPUT_IMAGES = 16
```

In `discover_capabilities`, add to EACH of the four gpt-image `ModelCapabilities(...)` constructions (`gpt-image-1`, and the loop covering `gpt-image-1-mini` + `gpt-image-1.5`, and `gpt-image-2`):

```python
                    supports_image_input=True,
                    max_input_images=_MAX_INPUT_IMAGES,
```

Do NOT add these to dall-e-3 or dall-e-2 (they keep the `False`/`0` defaults).

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_openai_discovery.py -k image_input -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/providers/openai.py tests/test_openai_discovery.py
git commit -m "feat(openai): advertise image-input capability (max 16) on gpt-image models

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: OpenAI `images.edit` reference-image path

**Files:**
- Modify: `src/image_generation_mcp/providers/openai.py` (`generate` dispatch + new `_edit`; shared param helper)
- Test: `tests/test_openai_provider.py`

**Interfaces:**
- Consumes: `_MAX_INPUT_IMAGES` (Task 1), `InputImage`, `TooManyInputImages`, `ImageInputUnsupported`, `ImageResult`.
- Produces: `generate()` dispatches to an edit path when `reference_images` is non-empty; gpt-image models call `client.images.edit`; non-edit models raise `ImageInputUnsupported`; >16 refs raise `TooManyInputImages`.

Behavior contract:
1. `reference_images` empty/None → existing text-to-image behavior, unchanged.
2. `reference_images` non-empty:
   - `effective_model = model or self._model`. If not a gpt-image model → `ImageInputUnsupported("openai", effective_model)` (dall-e has no no-mask reference edit).
   - `len(reference_images) > _MAX_INPUT_IMAGES` → `TooManyInputImages("openai", effective_model, _MAX_INPUT_IMAGES, len(reference_images))`.
   - Build `image=[(filename, ref.data, ref.content_type) for ref in reference_images]` (filename = `f"reference_{i}{ext}"`, ext from content_type).
   - Call `client.images.edit(model=, image=, prompt=<effective, with "Avoid:" negative>, n=1, size=, quality=<api_quality>, output_format=<format>, background=<if model supports>)` — same param mapping as the gpt-image generate path.
   - Parse `response.data[0].b64_json` identically to generate; metadata `{"model","size","quality","api_quality","edited": True}`.

- [ ] **Step 1: Write the failing tests**

Update the existing module-level `test_openai_rejects_reference_images` in `tests/test_openai_provider.py` — gpt-image now *supports* edit, so the rejection must assert against a NON-edit model:

```python
async def test_openai_rejects_reference_images_for_non_edit_model() -> None:
    """dall-e-3 has no edit endpoint -> reference_images raises ImageInputUnsupported."""
    from image_generation_mcp.providers.openai import OpenAIImageProvider
    from image_generation_mcp.providers.types import ImageInputUnsupported, InputImage

    provider = OpenAIImageProvider(api_key="sk-test", model="dall-e-3")
    with pytest.raises(ImageInputUnsupported):
        await provider.generate(
            "a cat",
            reference_images=[InputImage(data=b"x", content_type="image/png")],
        )
```

(Delete the old `test_openai_rejects_reference_images` that used the default gpt-image-1 model — it asserts behavior this issue intentionally changes. Replace, don't keep both.)

Add edit-path tests (use the `_mock_openai` fixture + the file's mock pattern: set `provider._client.images.edit = AsyncMock(return_value=mock_response)`):

```python
@pytest.mark.usefixtures("_mock_openai")
class TestOpenAIEdit:
    def _mk_provider(self, model="gpt-image-1"):
        from image_generation_mcp.providers.openai import OpenAIImageProvider
        return OpenAIImageProvider(api_key="sk-test", model=model)

    def _mk_response(self, b64="aGk="):
        item = MagicMock()
        item.b64_json = b64
        resp = MagicMock()
        resp.data = [item]
        return resp

    async def test_edit_with_single_reference_calls_images_edit(self) -> None:
        from image_generation_mcp.providers.types import InputImage
        provider = self._mk_provider()
        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.edit = AsyncMock(return_value=self._mk_response())

        ref = InputImage(data=b"png-bytes", content_type="image/png", source_id="a")
        result = await provider.generate("make it blue", reference_images=[ref])

        provider._client.images.edit.assert_awaited_once()
        kwargs = provider._client.images.edit.call_args.kwargs
        assert kwargs["model"] == "gpt-image-1"
        assert isinstance(kwargs["image"], list) and len(kwargs["image"]) == 1
        # file tuple: (filename, data, content_type)
        fname, data, ctype = kwargs["image"][0]
        assert data == b"png-bytes"
        assert ctype == "image/png"
        assert result.provider_metadata.get("edited") is True

    async def test_edit_with_multiple_references(self) -> None:
        from image_generation_mcp.providers.types import InputImage
        provider = self._mk_provider()
        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.edit = AsyncMock(return_value=self._mk_response())
        refs = [InputImage(data=b"a", content_type="image/png"),
                InputImage(data=b"b", content_type="image/jpeg")]
        await provider.generate("compose", reference_images=refs)
        assert len(provider._client.images.edit.call_args.kwargs["image"]) == 2

    async def test_edit_too_many_references_raises(self) -> None:
        from image_generation_mcp.providers.types import InputImage, TooManyInputImages
        provider = self._mk_provider()
        provider._client = MagicMock()
        refs = [InputImage(data=b"x", content_type="image/png") for _ in range(17)]
        with pytest.raises(TooManyInputImages):
            await provider.generate("x", reference_images=refs)

    async def test_edit_negative_prompt_appended(self) -> None:
        from image_generation_mcp.providers.types import InputImage
        provider = self._mk_provider()
        provider._client = MagicMock()
        provider._client.images = MagicMock()
        provider._client.images.edit = AsyncMock(return_value=self._mk_response())
        await provider.generate(
            "x", negative_prompt="dogs",
            reference_images=[InputImage(data=b"a", content_type="image/png")],
        )
        assert "Avoid: dogs" in provider._client.images.edit.call_args.kwargs["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_openai_provider.py -k "edit or non_edit_model" -v`
Expected: FAIL — `images.edit` is never called (current code raises `ImageInputUnsupported` for all reference_images), and the non-edit test imports/paths don't yet hold.

- [ ] **Step 3: Implement the edit path**

In `openai.py`, import `TooManyInputImages` (add to the `.types` import block alongside `ImageInputUnsupported`).

Extract the shared gpt-image request kwargs into a helper so generate and edit don't duplicate it:

```python
    def _gpt_image_request(
        self,
        *,
        effective_model: str,
        prompt: str,
        negative_prompt: str | None,
        aspect_ratio: str,
        quality: str,
        background: str,
    ) -> tuple[dict[str, Any], str]:
        """Build the shared gpt-image request kwargs and resolved content type.

        Returns ``(kwargs, content_type)`` where ``kwargs`` carries prompt, n,
        size, quality, output_format and (when the model supports it)
        background — everything common to ``images.generate`` and
        ``images.edit`` for the gpt-image family. The caller adds ``model`` and,
        for edits, ``image``.
        """
        size = _GPT_IMAGE_SIZES.get(aspect_ratio)
        if size is None:
            supported = ", ".join(sorted(_GPT_IMAGE_SIZES))
            raise ImageProviderError(
                "openai",
                f"Unsupported aspect_ratio '{aspect_ratio}'. Supported: {supported}",
            )
        effective_prompt = prompt
        if negative_prompt:
            effective_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"
        api_quality = {"standard": "auto", "hd": "high"}.get(quality, quality)
        kwargs: dict[str, Any] = {
            "prompt": effective_prompt,
            "n": 1,
            "size": size,
            "quality": api_quality,
            "output_format": self._output_format,
        }
        if effective_model not in _NO_BACKGROUND_GPT_IMAGE:
            kwargs["background"] = background
        elif background == "transparent":
            logger.debug(
                "%s does not support background parameter, ignoring", effective_model
            )
        return kwargs, _FORMAT_TO_CONTENT_TYPE[self._output_format]
```

> Refactor the existing gpt-image branch of `generate()` to use `_gpt_image_request` too (so the kwargs/size/quality/background logic lives in one place); leave the dall-e branch as-is. Keep `generate()`'s response-parsing and metadata block. The goal is no duplicated request-building between generate and edit — a reviewer will flag duplication.

Add the dispatch at the TOP of `generate()` (replace the current `if reference_images: raise ImageInputUnsupported(...)`):

```python
        if reference_images:
            return await self._edit(
                prompt,
                reference_images=reference_images,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
                background=background,
                model=model,
            )
```

Add the `_edit` method:

```python
    async def _edit(
        self,
        prompt: str,
        *,
        reference_images: Sequence[InputImage],
        negative_prompt: str | None,
        aspect_ratio: str,
        quality: str,
        background: str,
        model: str | None,
    ) -> ImageResult:
        """Edit/compose using OpenAI ``images.edit`` (gpt-image family only).

        Args:
            prompt: Edit description.
            reference_images: 1..16 input images (gpt-image composition).
            negative_prompt: Appended as ``"Avoid: ..."``.
            aspect_ratio / quality / background: Same mapping as generation.
            model: Override model; must be a gpt-image model.

        Raises:
            ImageInputUnsupported: model has no no-mask edit endpoint (dall-e).
            TooManyInputImages: more than 16 references supplied.
            ImageProviderError / *ContentPolicy* / *Connection*: API failures.
        """
        effective_model = model or self._model
        if not _is_gpt_image_model(effective_model):
            raise ImageInputUnsupported("openai", effective_model)
        if len(reference_images) > _MAX_INPUT_IMAGES:
            raise TooManyInputImages(
                "openai", effective_model, _MAX_INPUT_IMAGES, len(reference_images)
            )

        kwargs, content_type = self._gpt_image_request(
            effective_model=effective_model,
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
        )
        kwargs["model"] = effective_model
        kwargs["image"] = [
            (f"reference_{i}{_ext_for(ref.content_type)}", ref.data, ref.content_type)
            for i, ref in enumerate(reference_images)
        ]

        logger.debug(
            "OpenAI image edit: model=%s refs=%d size=%s",
            effective_model,
            len(reference_images),
            kwargs["size"],
        )
        try:
            response = await self._client.images.edit(**kwargs)
        except ImageProviderError:
            raise
        except Exception as e:
            self._handle_error(e)

        if not response.data:
            raise ImageProviderError("openai", "Empty response from image edit API")
        b64_data = response.data[0].b64_json
        if not b64_data:
            raise ImageProviderError("openai", "No image data in edit response")
        logger.info(
            "OpenAI image edited: model=%s refs=%d",
            effective_model,
            len(reference_images),
        )
        return ImageResult.from_base64(
            b64_data,
            content_type=content_type,
            model=effective_model,
            size=kwargs["size"],
            quality=quality,
            api_quality=kwargs["quality"],
            edited=True,
        )
```

Add the small extension-map helper near the top-level constants:

```python
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _ext_for(content_type: str) -> str:
    """Return a filename extension for an input image content type."""
    return _CONTENT_TYPE_TO_EXT.get(content_type, ".png")
```

Update the `generate()` docstring's `reference_images` line to describe the new behavior (image-to-image / composition via `images.edit` for gpt-image; raises `ImageInputUnsupported` for dall-e).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openai_provider.py -v`
Expected: PASS (existing generate tests unchanged + new edit tests + the rewritten non-edit rejection test).

- [ ] **Step 5: Full gates**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/providers/openai.py tests/test_openai_provider.py
git commit -m "feat(openai): image-to-image and composition via images.edit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Documentation

**Files:**
- Modify: `docs/providers/openai.md`, `docs/tools.md`

**Interfaces:** none. Required by the docs hard gate.

- [ ] **Step 1: Document OpenAI image input**

In `docs/providers/openai.md`, add an "Image input (editing and composition)" section: the gpt-image family (gpt-image-2/1.5/1/1-mini) accepts reference images via `transform_image` — single-image edits and multi-image composition up to 16 references; dall-e-3/dall-e-2 do not (no-mask reference edit unsupported). Note `supports_image_input` / `max_input_images` appear in `list_providers`.

In `docs/tools.md`, update the `transform_image` section to note OpenAI is now a supported image-input provider (in addition to Gemini), with up to 16 references for composition.

**Keep the prose Vale-clean** (these are site docs): no em-dashes (use commas/parentheses), no "e.g."/"i.e." (write "for example"/"that is"), no "**Note:**" metacommentary, no three-parallel-verb lists. Run `vale sync` then `vale --minAlertLevel=error docs/providers/openai.md docs/tools.md` and fix any error on the lines you add (add genuine technical terms to `.vale/styles/config/vocabularies/Base/accept.txt` if needed).

- [ ] **Step 2: Verify**

Run: `uv run mkdocs build 2>&1 | tail -5` (no errors) and `vale --minAlertLevel=error docs/providers/openai.md docs/tools.md` (0 errors on added lines).

- [ ] **Step 3: Commit**

```bash
git add docs/providers/openai.md docs/tools.md
git commit -m "docs: document OpenAI image input (editing + composition)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Pre-PR verification

- [ ] `uv run pytest -x -q` — all pass.
- [ ] ruff check/format clean; `uv run mypy src/ tests/` clean.
- [ ] `uv run pytest --cov=image_generation_mcp.providers.openai --cov-report=term-missing` — patch coverage ≥ 80% (edit path, both error branches, capability fields covered).
- [ ] Run `preflight-circus` against `BASE..HEAD` before `gh pr create`. Pre-emptively grep for any provider-name-hardcoded user-facing string and confirm messages stay provider-neutral where appropriate (lesson from #263).
- [ ] PR body: `Closes #258`, `Refs #256`, agent-attribution signature; note Vale is the known-broken #244 gate (non-blocking) if it shows red on unrelated docs.

## Self-Review notes (author)

- Capability fields (T1) → edit implementation (T2) → docs (T3). The tool layer needs no change (capability-routed already).
- `_gpt_image_request` is extracted to avoid duplicating request-building between `generate` and `_edit` (pre-empts the DRY finding pattern seen on #263).
- The foundation's `test_openai_rejects_reference_images` is rewritten (not deleted) to assert the new state (rejection only for non-edit models) — removal/refactor discipline.
- Type consistency: `_MAX_INPUT_IMAGES = 16`, `_edit(... reference_images: Sequence[InputImage] ...)`, file tuple `(filename, bytes, content_type)`, metadata `edited=True`.
