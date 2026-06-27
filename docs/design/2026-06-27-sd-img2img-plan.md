# SD WebUI img2img + denoising strength (Issue #259) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Implement reference-image input for the SD WebUI provider via the `/sdapi/v1/img2img` endpoint, and add a `strength` (denoising) parameter to `transform_image` that only SD uses.

**Architecture:** The foundation already threads `reference_images` through `ImageProvider.generate()`, the `transform_image` tool, and the capability model. SD WebUI currently *rejects* `reference_images`. This issue (1) threads a new optional `strength: float` param through the same path (protocol → service → `_start_background_generation` → tool), which only SD consumes (others ignore with a debug log); and (2) implements SD's img2img path with `init_images` + `denoising_strength`, advertising `supports_image_input` / `max_input_images=1`.

**Tech Stack:** Python 3.11+, httpx (SD WebUI REST API), pytest (httpx mocked), uv, ruff, mypy.

## Global Constraints

- Python 3.11+; full type hints; Google-style docstrings.
- `logging.getLogger(__name__)`; no f-strings in log calls (lazy `%s`, event-name-first); no bare `except`.
- Hard gates before push: `uv run pytest -x -q`; `uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .`; `uv run mypy src/ tests/`; patch coverage ≥ 80%; docs updated.
- TDD: failing test first → implement → pass → commit. Conventional commits with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **SD WebUI img2img API** (A1111/Forge `/sdapi/v1/img2img`): same payload as `txt2img` PLUS `init_images` (list of base64-encoded image strings, no data: prefix) and `denoising_strength` (float 0–1, A1111 default 0.75). Response shape is identical to txt2img (`data["images"][0]` base64, `data["info"]`).
- **`strength` is SD-specific.** Range 0–1. Default 0.75 when unset. Non-SD providers ignore it (debug log when set). It only takes effect with `reference_images` (img2img); txt2img ignores it.

## Scope decisions
- SD img2img uses a single init image → `max_input_images=1`; >1 raises `TooManyInputImages`.
- `strength` is added to `transform_image` and threaded through the provider protocol (matching the `reference_images` precedent), consumed only by SD.
- No mask support (that is OpenAI #261). No SD inpainting.

---

## File Structure

- **Modify** `src/image_generation_mcp/providers/types.py` — add `strength: float | None = None` to the `ImageProvider.generate()` protocol signature + docstring.
- **Modify** `src/image_generation_mcp/service.py` — add `strength` to `ImageService.generate()`, pass through to the provider.
- **Modify** `src/image_generation_mcp/_server_tools.py` — add `strength` to `_start_background_generation` (pass-through) and to the `transform_image` tool (with 0–1 validation), thread to `service.generate`.
- **Modify** `src/image_generation_mcp/providers/gemini.py`, `providers/openai.py`, `providers/placeholder.py` — accept `strength`; ignore with a debug log when set.
- **Modify** `src/image_generation_mcp/providers/sd_webui.py` — extract a shared payload builder; add the img2img path (`reference_images` → `/sdapi/v1/img2img` with `init_images` + `denoising_strength`); advertise `supports_image_input` / `max_input_images=1`; consume `strength`.
- **Tests:** `tests/test_tools.py`, `tests/test_sd_webui_provider.py`, `tests/test_sd_webui_discovery.py`, `tests/test_gemini_provider.py`, `tests/test_openai_provider.py`, `tests/test_placeholder.py`, `tests/test_service.py`.
- **Docs:** `docs/providers/sd-webui.md`, `docs/tools.md`.

---

## Task 1: Thread `strength` through the protocol, service, tool, and non-SD providers

**Files:**
- Modify: `providers/types.py`, `service.py`, `_server_tools.py`, `providers/gemini.py`, `providers/openai.py`, `providers/placeholder.py`
- Test: `tests/test_tools.py`, `tests/test_service.py`, `tests/test_gemini_provider.py`, `tests/test_openai_provider.py`, `tests/test_placeholder.py`

**Interfaces:**
- Produces: `strength: float | None = None` on `ImageProvider.generate()`, `ImageService.generate()`, `_start_background_generation(...)`, and the `transform_image` tool. The tool validates `0.0 <= strength <= 1.0` (else `ValueError`). gemini/openai/placeholder accept and ignore it (debug log when not None). SD accepts it (consumed in Task 2).

- [ ] **Step 1: Write the failing tests**

In `tests/test_tools.py` (`TestTransformImageTool`), add strength-validation tests (mirror the existing param-validation tests; an out-of-range strength must raise before enqueue):

```python
@pytest.mark.parametrize("bad", [-0.1, 1.5, 2.0])
async def test_transform_image_rejects_out_of_range_strength(
    self, service: ImageService, bad: float
) -> None:
    # service fixture: placeholder only (no image-input) is fine — validation
    # happens before provider routing. Use an image-input-capable service so we
    # reach the strength check; simplest: inject a capable provider like the
    # other transform tests, then assert ValueError on bad strength.
    ...
```

> Implementer: reach the strength validation by using the same image-input-capable harness as the other `transform_image` tests (inject a fake provider with `supports_image_input=True` via `service._capabilities`, register one gallery image). Place the `strength` range check in the tool right after the existing enum validations and assert `pytest.raises(ValueError, match="strength")` for each bad value.

In `tests/test_gemini_provider.py`, `tests/test_openai_provider.py`, `tests/test_placeholder.py` add one test each that passing `strength` to a non-SD provider's `generate()` is accepted and ignored (no error). Example (placeholder):

```python
async def test_placeholder_ignores_strength() -> None:
    from image_generation_mcp.providers.placeholder import PlaceholderImageProvider

    result = await PlaceholderImageProvider().generate("x", strength=0.5)
    assert result.image_data  # produced normally, strength ignored
```

For gemini/openai, mirror an existing successful-generate test in that file but pass `strength=0.5` and assert it still returns an ImageResult (the SDK call is mocked; strength must not be forwarded to the SDK kwargs — assert it is absent from the call kwargs).

In `tests/test_service.py`, add a test that `ImageService.generate(..., strength=0.5)` forwards `strength=0.5` to the provider (AsyncMock fake): `assert fake.generate.call_args.kwargs["strength"] == 0.5`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k strength tests/test_service.py -k strength tests/test_placeholder.py -k strength -v`
Expected: FAIL — `generate()`/tool don't accept `strength` yet (`TypeError: unexpected keyword argument 'strength'`).

- [ ] **Step 3: Implement the plumbing**

**`providers/types.py`** — in the `ImageProvider.generate()` protocol signature, add before `progress_callback`:
```python
        strength: float | None = None,
```
Document it:
```
            strength: Denoising strength (0.0–1.0) for image-to-image. Only
                SD WebUI uses it (as ``denoising_strength``); other providers
                ignore it. Has no effect without ``reference_images``.
```

**`service.py`** — add `strength: float | None = None` to `ImageService.generate()` (before `progress_callback`), document it, and pass `strength=strength` to `resolved_provider.generate(...)`.

**`_server_tools.py`** — add `strength: float | None = None` to `_start_background_generation(...)` and forward it in its `service.generate(...)` call. In the `transform_image` tool, add `strength: float | None = None` to the signature, validate after the other enum checks:
```python
        if strength is not None and not 0.0 <= strength <= 1.0:
            raise ValueError(
                f"strength must be between 0.0 and 1.0; got {strength}."
            )
```
and pass `strength=strength` into `_start_background_generation(...)`. Document the param in the tool docstring (SD-only denoising; 0–1; no effect without an SD provider / reference images).

**`gemini.py`, `openai.py`, `placeholder.py`** — add `strength: float | None = None` to each `generate()` signature (before `progress_callback`). At the top of each body (after any existing reference-image handling), add:
```python
        if strength is not None:
            logger.debug("strength is not supported by <provider>; ignoring")
```
Use the provider's name. Do NOT forward `strength` to the underlying SDK/API kwargs. (openai/gemini: place after the reference-image dispatch/guard so the edit path is unaffected; openai's `_edit` does not take strength.)

**`sd_webui.py`** — add `strength: float | None = None` to `generate()` (before `progress_callback`). For this task SD does not yet use it (no img2img). Add a `# noqa: ARG002`-free placeholder: keep the param; Task 2 consumes it. (To avoid an unused-arg lint error now, Task 1 may leave a `# noqa: ARG002` on `strength` that Task 2 removes — OR sequence so Task 2 immediately follows. Prefer: Task 1 adds `strength` to sd_webui with `# noqa: ARG002`; Task 2 removes the noqa when it wires img2img.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py tests/test_service.py tests/test_gemini_provider.py tests/test_openai_provider.py tests/test_placeholder.py -q`
Expected: PASS (new strength tests + existing tests unchanged).

- [ ] **Step 5: Full gates + commit**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
git add src/image_generation_mcp/ tests/
git commit -m "feat: thread strength (denoising) param through transform_image; non-SD providers ignore it

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: SD WebUI img2img path + capability

**Files:**
- Modify: `src/image_generation_mcp/providers/sd_webui.py`
- Test: `tests/test_sd_webui_provider.py`, `tests/test_sd_webui_discovery.py`

**Interfaces:**
- Consumes: `strength` (Task 1), `InputImage`, `TooManyInputImages`, `_MAX_INPUT_IMAGES`.
- Produces: SD `generate()` routes to img2img when `reference_images` is non-empty; advertises `supports_image_input=True, max_input_images=1` on every checkpoint.

Behavior contract:
1. `reference_images` empty/None → existing txt2img behavior, unchanged.
2. `reference_images` non-empty: `len > 1` → `TooManyInputImages("sd_webui", effective_model, 1, len)`; build the shared payload + `init_images=[base64(ref.data)]` + `denoising_strength=strength if strength is not None else 0.75`; POST `/sdapi/v1/img2img`; parse the response identically to txt2img; metadata `edited=True`.
3. Capability: `supports_image_input=True, max_input_images=1` on each checkpoint.

- [ ] **Step 1: Write the failing tests**

In `tests/test_sd_webui_provider.py` (mirror the existing txt2img test mocking — it patches `provider._client.post` / uses an httpx mock; follow the file's pattern):

```python
async def test_img2img_with_reference_calls_img2img_endpoint() -> None:
    # provider = SdWebuiImageProvider(host="http://localhost:7860")
    # mock client.post to return 200 with {"images": ["<b64>"], "info": "{}"}
    # call generate("edit", reference_images=[InputImage(data=b"...", content_type="image/png")], strength=0.4)
    # assert the POST url ends with /sdapi/v1/img2img
    # assert payload["init_images"] == [base64.b64encode(b"...").decode()]
    # assert payload["denoising_strength"] == 0.4
    ...

async def test_img2img_default_denoising_when_strength_none() -> None:
    # same, strength=None → payload["denoising_strength"] == 0.75

async def test_img2img_too_many_references_raises() -> None:
    # two refs → TooManyInputImages

async def test_txt2img_unaffected_by_strength_without_references() -> None:
    # generate("x", strength=0.3) with no reference_images → posts to /txt2img,
    # payload has no init_images / denoising_strength
```

> Use the real base64 of small bytes; mock the HTTP client the same way the existing SD tests do (inspect `tests/test_sd_webui_provider.py` for the exact mock pattern — likely `respx` or a `MagicMock`/`AsyncMock` on `provider._client.post` returning an object with `.status_code` and `.json()`).

In `tests/test_sd_webui_discovery.py`, assert each discovered checkpoint reports `supports_image_input is True` and `max_input_images == 1`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sd_webui_provider.py -k img2img tests/test_sd_webui_discovery.py -k image_input -v`
Expected: FAIL — SD still raises `ImageInputUnsupported` for reference_images; capability fields are default False/0.

- [ ] **Step 3: Implement**

Add a module constant near the top: `_MAX_INPUT_IMAGES = 1` and `_DEFAULT_DENOISING_STRENGTH = 0.75`. Import `TooManyInputImages` from `.types`. Add `import base64`.

Extract a shared payload builder so txt2img and img2img don't duplicate it:
```python
    def _build_payload(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        aspect_ratio: str,
        effective_model: str | None,
        preset: _SdWebuiPreset,
    ) -> tuple[dict[str, Any], int, int]:
        """Build the shared SD WebUI request payload; returns (payload, w, h)."""
        # (move the current width/height + payload + negative + distilled_cfg +
        #  override_settings construction from generate() into here, returning
        #  the payload dict and the width/height for metadata/progress.)
```
Refactor the existing txt2img `generate()` body to call `_build_payload` (no behavior change to txt2img).

Replace the `if reference_images: raise ImageInputUnsupported(...)` guard with a dispatch: when `reference_images` is non-empty, build the payload via `_build_payload`, then:
```python
        if reference_images:
            if len(reference_images) > _MAX_INPUT_IMAGES:
                raise TooManyInputImages(
                    "sd_webui", effective_model, _MAX_INPUT_IMAGES,
                    len(reference_images),
                )
            payload["init_images"] = [
                base64.b64encode(reference_images[0].data).decode("ascii")
            ]
            payload["denoising_strength"] = (
                strength if strength is not None else _DEFAULT_DENOISING_STRENGTH
            )
            url = f"{self._host}/sdapi/v1/img2img"
        else:
            url = f"{self._host}/sdapi/v1/txt2img"
```
Keep the existing POST / error handling / response parsing (it is endpoint-agnostic). Add `edited=True` to the metadata when img2img is used. Remove the `# noqa: ARG002` from `strength` (now used). Update the `generate()` docstring (`reference_images` now does img2img; `strength` is denoising).

In `discover_capabilities`, add to each `ModelCapabilities(...)`:
```python
                    supports_image_input=True,
                    max_input_images=_MAX_INPUT_IMAGES,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sd_webui_provider.py tests/test_sd_webui_discovery.py -q`
Expected: PASS (img2img tests + capability + existing txt2img tests unchanged).

- [ ] **Step 5: Full gates + commit**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
git add src/image_generation_mcp/providers/sd_webui.py tests/test_sd_webui_provider.py tests/test_sd_webui_discovery.py
git commit -m "feat(sd_webui): img2img reference-image input with denoising strength

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Documentation

**Files:**
- Modify: `docs/providers/sd-webui.md`, `docs/tools.md`

- [ ] **Step 1: Document**

In `docs/providers/sd-webui.md`, add an "Image input (img2img)" section: any discovered checkpoint accepts a single reference image via `transform_image` (img2img); the `strength` parameter maps to `denoising_strength` (0–1, default 0.75; lower preserves the init image, higher regenerates more). `supports_image_input` / `max_input_images=1` appear in `list_providers`.

In `docs/tools.md`, document the new `strength` parameter on `transform_image`: SD-WebUI-only denoising strength (0–1); ignored by Gemini and OpenAI; no effect without a reference image.

**Vale-clean** (site docs): no em-dashes (use commas/parentheses), no "e.g."/"i.e." (write "for example"/"that is"), no "**Note:**" metacommentary, no three-parallel-verb lists. Run `vale sync` then `vale --minAlertLevel=error docs/providers/sd-webui.md docs/tools.md` and fix errors on added lines; add genuine terms to `.vale/styles/config/vocabularies/Base/accept.txt` if needed.

- [ ] **Step 2: Verify + commit**

```bash
uv run mkdocs build 2>&1 | tail -5
vale --minAlertLevel=error docs/providers/sd-webui.md docs/tools.md
git add docs/providers/sd-webui.md docs/tools.md
git commit -m "docs: document SD WebUI img2img and the strength parameter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Pre-PR verification

- [ ] `uv run pytest -x -q` pass; ruff/format clean; `uv run mypy src/ tests/` clean.
- [ ] `uv run pytest --cov=image_generation_mcp.providers.sd_webui --cov=image_generation_mcp._server_tools --cov-report=term-missing` — patch coverage ≥ 80% (img2img path, both denoising branches, TooManyInputImages, strength validation, non-SD ignore).
- [ ] Grep for any provider-name-hardcoded user-facing string introduced (lesson from #263/#265); keep messages provider-neutral where appropriate.
- [ ] Run `preflight-circus` against `BASE..HEAD` before `gh pr create`.
- [ ] PR body: `Closes #259`, `Refs #256`, agent-attribution signature; note Vale red is the known #244 gate (non-blocking) if it shows on the new plan doc / pre-existing content.

## Self-Review notes (author)
- `strength` threaded exactly like `reference_images` (protocol → service → helper → tool), consumed only by SD; non-SD ignore-with-log. Tool validates 0–1.
- `_build_payload` extraction prevents txt2img/img2img duplication (pre-empts the DRY finding pattern seen on #258/#263).
- Type consistency: `strength: float | None`, `_MAX_INPUT_IMAGES = 1`, `_DEFAULT_DENOISING_STRENGTH = 0.75`, `init_images=[b64]`, metadata `edited=True`.
