# Reference-image input — Foundation + Gemini single-image i2i (Issue #257) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the foundational primitive for feeding an image *into* generation — a reference-image resolver, a provider-protocol extension, capability metadata, and a new `transform_image` MCP tool — with Gemini single-image image-to-image as the first working consumer.

**Architecture:** A new `_input_images.py` module is the *only* place that knows about input sources (gallery `image_id`/`image://` URI and gated local file path); it produces a provider-facing `InputImage` value object. `ImageProvider.generate()` gains an optional `reference_images` parameter threaded through `ImageService.generate()` and the existing background-task runner. Providers advertise `supports_image_input` / `max_input_images`; non-Gemini providers raise `ImageInputUnsupported` for now. The `transform_image` tool resolves references synchronously (so errors surface before enqueue), checks capability routing, then reuses the exact background/task + `ResourceLink` pattern of `generate_image`.

**Tech Stack:** Python 3.11+, FastMCP, `google-genai` (mocked in tests via the `_mock_genai` conftest fixture), Pillow, pytest, `uv`, ruff, mypy.

## Global Constraints

- Python 3.11+; type hints everywhere; Google-style docstrings on all public functions. (Verbatim project conventions.)
- `logging.getLogger(__name__)` throughout; no `print()`. Pseudo-structured logs: `logger.info("event_name key=%s", value)`; event name first; never f-strings in log calls.
- No bare `except:`; always specify the exception type.
- All env reads go through `fastmcp_pvl_core.env(_ENV_PREFIX, "SUFFIX", default)`; env prefix is `IMAGE_GENERATION_MCP`.
- New domain config fields go **between** the `CONFIG-FIELDS-START`/`CONFIG-FIELDS-END` and `CONFIG-FROM-ENV-START`/`CONFIG-FROM-ENV-END` sentinels in `config.py`. Never inherit from `ServerConfig`; compose.
- Write tools tagged `tags={"write"}`; hidden in read-only mode.
- Hard PR gates (all must be green before pushing): `uv run pytest -x -q`; `uv run ruff check --fix .` then `uv run ruff format .` then `uv run ruff format --check .`; `uv run mypy src/ tests/`; patch coverage ≥ 80%; docs updated in the same commit.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- Conventional commits (`feat:`, `test:`, `docs:`, `refactor:`). End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File Structure

- **Create** `src/image_generation_mcp/_input_images.py` — input-source resolution: `resolve_reference()` + `resolve_references()`, `ImageReferenceNotFound`, `LocalFileInputDisabled`, internal validation. The only module aware of gallery-vs-file input.
- **Modify** `src/image_generation_mcp/providers/types.py` — add `InputImage` dataclass; add `ImageInputUnsupported`, `TooManyInputImages` exceptions; extend the `ImageProvider.generate()` protocol signature with `reference_images`.
- **Modify** `src/image_generation_mcp/providers/capabilities.py` — add `supports_image_input` / `max_input_images` to `ModelCapabilities` (+ `to_dict`).
- **Modify** `src/image_generation_mcp/config.py` — add `allow_local_file_input` / `max_input_image_bytes` fields + env reads.
- **Modify** `src/image_generation_mcp/providers/gemini.py` — accept + send reference images; advertise `supports_image_input=True, max_input_images=1`; enforce `TooManyInputImages`.
- **Modify** `src/image_generation_mcp/providers/openai.py`, `providers/sd_webui.py`, `providers/placeholder.py` — accept the new param; raise `ImageInputUnsupported` when given non-empty references.
- **Modify** `src/image_generation_mcp/service.py` — thread `reference_images` through `generate()`; generalize provenance to `source_image_ids: list[str]` in `ImageRecord`, `register_image`, and the sidecar (with legacy-singular read in `_load_registry`).
- **Modify** `src/image_generation_mcp/_server_tools.py` — register the new `transform_image` tool (conditional on a provider supporting image input).
- **Modify** `src/image_generation_mcp/_server_resources.py` — surface `source_image_ids` in the `image://{id}/metadata` resource (and keep `source_image_id` working if currently emitted).
- **Tests:** `tests/test_input_images.py` (new), `tests/test_config.py`, `tests/test_capabilities.py`, `tests/test_types.py`, `tests/test_gemini_provider.py`, `tests/test_openai_provider.py`, `tests/test_sd_webui_provider.py`, `tests/test_placeholder.py`, `tests/test_service.py`, `tests/test_tools.py`, `tests/test_mcp_integration.py`.
- **Docs:** `README.md`, `docs/tools.md`, `docs/configuration.md`, `docs/providers/gemini.md`.

---

## Task 1: Config fields for input gating

**Files:**
- Modify: `src/image_generation_mcp/config.py` (CONFIG-FIELDS and CONFIG-FROM-ENV sentinel blocks)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `ProjectConfig.allow_local_file_input: bool` (default `False`), `ProjectConfig.max_input_image_bytes: int` (default `20 * 1024 * 1024`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_allow_local_file_input_defaults_false(monkeypatch) -> None:
    monkeypatch.delenv("IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT", raising=False)
    from image_generation_mcp.config import load_config

    assert load_config().allow_local_file_input is False


def test_allow_local_file_input_parsed(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT", "true")
    from image_generation_mcp.config import load_config

    assert load_config().allow_local_file_input is True


def test_max_input_image_bytes_default(monkeypatch) -> None:
    monkeypatch.delenv("IMAGE_GENERATION_MCP_MAX_INPUT_IMAGE_BYTES", raising=False)
    from image_generation_mcp.config import load_config

    assert load_config().max_input_image_bytes == 20 * 1024 * 1024


def test_max_input_image_bytes_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("IMAGE_GENERATION_MCP_MAX_INPUT_IMAGE_BYTES", "notanumber")
    from image_generation_mcp.config import load_config

    assert load_config().max_input_image_bytes == 20 * 1024 * 1024
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -k "input" -v`
Expected: FAIL with `AttributeError: 'ProjectConfig' object has no attribute 'allow_local_file_input'`.

- [ ] **Step 3: Add the fields and env reads**

In `config.py`, inside `CONFIG-FIELDS-START`/`-END`, after `styles_dir`:

```python
    allow_local_file_input: bool = False
    max_input_image_bytes: int = 20 * 1024 * 1024
```

Inside `CONFIG-FROM-ENV-START`/`-END`, before the `config = ProjectConfig(` call:

```python
    allow_local_file_input = parse_bool(
        env(_ENV_PREFIX, "ALLOW_LOCAL_FILE_INPUT", "false")
    )

    raw_max_input = env(_ENV_PREFIX, "MAX_INPUT_IMAGE_BYTES")
    max_input_image_bytes = 20 * 1024 * 1024
    if raw_max_input:
        try:
            max_input_image_bytes = int(raw_max_input)
        except ValueError:
            logger.warning(
                "Invalid MAX_INPUT_IMAGE_BYTES=%r — using default %d",
                raw_max_input,
                max_input_image_bytes,
            )
```

Add both to the `ProjectConfig(...)` constructor call:

```python
        allow_local_file_input=allow_local_file_input,
        max_input_image_bytes=max_input_image_bytes,
```

Also extend the `load_config` docstring's "Reads:" list with the two new vars.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -k "input" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/config.py tests/test_config.py
git commit -m "feat: add config gates for reference-image input

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `InputImage` value type + provider exceptions

**Files:**
- Modify: `src/image_generation_mcp/providers/types.py`
- Test: `tests/test_types.py`

**Interfaces:**
- Produces:
  - `InputImage(data: bytes, content_type: str = "image/png", source_id: str | None = None)` frozen dataclass with `size_bytes` property.
  - `ImageInputUnsupported(ImageProviderError)` — `__init__(self, provider: str, model: str | None = None)`.
  - `TooManyInputImages(ImageProviderError)` — `__init__(self, provider: str, model: str | None, max_input_images: int, given: int)`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_types.py`:

```python
def test_input_image_size_bytes() -> None:
    from image_generation_mcp.providers.types import InputImage

    img = InputImage(data=b"1234", content_type="image/png", source_id="abc123")
    assert img.size_bytes == 4
    assert img.source_id == "abc123"


def test_image_input_unsupported_message() -> None:
    from image_generation_mcp.providers.types import (
        ImageInputUnsupported,
        ImageProviderError,
    )

    exc = ImageInputUnsupported("openai", "gpt-image-2")
    assert isinstance(exc, ImageProviderError)
    assert "gpt-image-2" in str(exc)
    assert exc.provider == "openai"


def test_too_many_input_images_message() -> None:
    from image_generation_mcp.providers.types import TooManyInputImages

    exc = TooManyInputImages("gemini", "gemini-2.5-flash-image", 1, 3)
    assert "1" in str(exc)
    assert "3" in str(exc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_types.py -k "input or too_many" -v`
Expected: FAIL with `ImportError: cannot import name 'InputImage'`.

- [ ] **Step 3: Implement in `providers/types.py`**

After the `ImageResult` class, add:

```python
@dataclass(frozen=True)
class InputImage:
    """A reference image supplied as input to a generation call.

    The input counterpart of :class:`ImageResult`.

    Attributes:
        data: Raw image bytes.
        content_type: MIME type (e.g., ``image/png``).
        source_id: Gallery image id when resolved from the store, else
            ``None`` (e.g. for local-file sources).
    """

    data: bytes
    content_type: str = "image/png"
    source_id: str | None = None

    @property
    def size_bytes(self) -> int:
        """Size of the image data in bytes."""
        return len(self.data)
```

After the existing exception classes, add:

```python
class ImageInputUnsupported(ImageProviderError):
    """Raised when a provider/model cannot accept reference images."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        target = f" model {model!r}" if model else ""
        super().__init__(
            provider,
            f"does not support reference-image input{target}. "
            "Use a Gemini model for image-to-image edits.",
        )


class TooManyInputImages(ImageProviderError):
    """Raised when more reference images are supplied than a model accepts."""

    def __init__(
        self, provider: str, model: str | None, max_input_images: int, given: int
    ) -> None:
        target = f" model {model!r}" if model else ""
        super().__init__(
            provider,
            f"{target} accepts at most {max_input_images} reference image(s); "
            f"{given} were given.",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_types.py -k "input or too_many" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/providers/types.py tests/test_types.py
git commit -m "feat: add InputImage type and image-input provider exceptions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Capability fields `supports_image_input` / `max_input_images`

**Files:**
- Modify: `src/image_generation_mcp/providers/capabilities.py`
- Test: `tests/test_capabilities.py`

**Interfaces:**
- Produces: `ModelCapabilities.supports_image_input: bool = False`, `ModelCapabilities.max_input_images: int = 0`, both serialized in `to_dict()`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_capabilities.py`:

```python
def test_model_caps_image_input_defaults() -> None:
    from image_generation_mcp.providers.capabilities import ModelCapabilities

    cap = ModelCapabilities(model_id="m", display_name="M")
    assert cap.supports_image_input is False
    assert cap.max_input_images == 0


def test_model_caps_image_input_in_to_dict() -> None:
    from image_generation_mcp.providers.capabilities import ModelCapabilities

    cap = ModelCapabilities(
        model_id="m",
        display_name="M",
        supports_image_input=True,
        max_input_images=1,
    )
    d = cap.to_dict()
    assert d["supports_image_input"] is True
    assert d["max_input_images"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capabilities.py -k "image_input" -v`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'supports_image_input'`.

- [ ] **Step 3: Implement**

In `capabilities.py`, add to `ModelCapabilities` fields (after `supports_background`):

```python
    supports_image_input: bool = False
    max_input_images: int = 0
```

Add to the `result` dict in `ModelCapabilities.to_dict()` (after `supports_background`):

```python
            "supports_image_input": self.supports_image_input,
            "max_input_images": self.max_input_images,
```

Add the two attributes to the class docstring's Attributes list.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capabilities.py -k "image_input" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/providers/capabilities.py tests/test_capabilities.py
git commit -m "feat: add image-input capability fields to ModelCapabilities

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Input-reference resolver (`_input_images.py`)

**Files:**
- Create: `src/image_generation_mcp/_input_images.py`
- Test: `tests/test_input_images.py` (new)

**Interfaces:**
- Consumes: `InputImage` (Task 2).
- Produces:
  - `ImageReferenceNotFound(Exception)`, `LocalFileInputDisabled(Exception)`, `InputImageTooLarge(Exception)`, `InvalidInputImage(Exception)`.
  - `GalleryLoader = Callable[[str], tuple[bytes, str]]` — returns `(data, content_type)`, raises `KeyError` when the id is unknown.
  - `resolve_reference(ref: str, *, loader: GalleryLoader, allow_local_files: bool, max_bytes: int) -> InputImage`
  - `resolve_references(refs: Sequence[str], *, loader: GalleryLoader, allow_local_files: bool, max_bytes: int) -> list[InputImage]`

Resolution rule (deterministic): a ref that starts with `image://` or matches `^[0-9a-f]{12}$` is a **gallery** reference (loaded via `loader`; unknown → `ImageReferenceNotFound`). Anything else is a **file path** (rejected with `LocalFileInputDisabled` when `allow_local_files` is False).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_input_images.py`:

```python
"""Tests for the input-reference resolver."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from image_generation_mcp._input_images import (
    ImageReferenceNotFound,
    InputImageTooLarge,
    InvalidInputImage,
    LocalFileInputDisabled,
    resolve_reference,
    resolve_references,
)


def _png_bytes(color: str = "red", size: tuple[int, int] = (4, 4)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _loader_with(mapping):
    def loader(image_id: str):
        if image_id not in mapping:
            raise KeyError(image_id)
        return mapping[image_id]

    return loader


def test_resolve_bare_image_id() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    img = resolve_reference(
        "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10_000
    )
    assert img.data == data
    assert img.source_id == "0123456789ab"


def test_resolve_image_uri() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    img = resolve_reference(
        "image://0123456789ab/view",
        loader=loader,
        allow_local_files=False,
        max_bytes=10_000,
    )
    assert img.source_id == "0123456789ab"


def test_unknown_gallery_id_raises() -> None:
    loader = _loader_with({})
    with pytest.raises(ImageReferenceNotFound):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10_000
        )


def test_file_path_rejected_when_disabled() -> None:
    loader = _loader_with({})
    with pytest.raises(LocalFileInputDisabled):
        resolve_reference(
            "/tmp/foo.png", loader=loader, allow_local_files=False, max_bytes=10_000
        )


def test_file_path_read_when_enabled(tmp_path) -> None:
    p = tmp_path / "ref.png"
    p.write_bytes(_png_bytes("blue"))
    loader = _loader_with({})
    img = resolve_reference(
        str(p), loader=loader, allow_local_files=True, max_bytes=10_000
    )
    assert img.source_id is None
    assert img.content_type == "image/png"


def test_missing_file_raises(tmp_path) -> None:
    loader = _loader_with({})
    with pytest.raises(ImageReferenceNotFound):
        resolve_reference(
            str(tmp_path / "nope.png"),
            loader=loader,
            allow_local_files=True,
            max_bytes=10_000,
        )


def test_oversized_image_rejected() -> None:
    data = _png_bytes(size=(64, 64))
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    with pytest.raises(InputImageTooLarge):
        resolve_reference(
            "0123456789ab", loader=loader, allow_local_files=False, max_bytes=10
        )


def test_non_image_bytes_rejected(tmp_path) -> None:
    p = tmp_path / "bad.png"
    p.write_bytes(b"not an image")
    loader = _loader_with({})
    with pytest.raises(InvalidInputImage):
        resolve_reference(
            str(p), loader=loader, allow_local_files=True, max_bytes=10_000
        )


def test_resolve_references_multiple() -> None:
    data = _png_bytes()
    loader = _loader_with({"0123456789ab": (data, "image/png")})
    imgs = resolve_references(
        ["0123456789ab", "image://0123456789ab/view"],
        loader=loader,
        allow_local_files=False,
        max_bytes=10_000,
    )
    assert len(imgs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_input_images.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'image_generation_mcp._input_images'`.

- [ ] **Step 3: Implement `_input_images.py`**

```python
"""Resolution of caller-supplied image references into raw bytes.

The single module that knows about input sources (gallery ids/URIs and
local file paths). Producing :class:`InputImage` values for providers.
Adding base64/URL sources later is localized here.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from image_generation_mcp.providers.types import InputImage

logger = logging.getLogger(__name__)

GalleryLoader = Callable[[str], tuple[bytes, str]]
"""Loads ``(data, content_type)`` for a gallery image id; raises KeyError if unknown."""

_IMAGE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_IMAGE_URI_RE = re.compile(r"^image://([0-9a-zA-Z]+)(?:/.*)?$")

_PIL_FORMAT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}


class ImageReferenceNotFound(Exception):
    """Raised when a gallery id is unknown or a file path does not exist."""

    def __init__(self, ref: str) -> None:
        super().__init__(
            f"Image reference {ref!r} not found. "
            "Use a gallery image_id (read image://list) or an existing file path."
        )


class LocalFileInputDisabled(Exception):
    """Raised when a file-path reference is given but file input is disabled."""

    def __init__(self, ref: str) -> None:
        super().__init__(
            f"Local file input is disabled; cannot read {ref!r}. "
            "Set IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT=true to enable "
            "(only when callers are trusted with server filesystem access)."
        )


class InputImageTooLarge(Exception):
    """Raised when a reference image exceeds the configured byte cap."""

    def __init__(self, ref: str, size: int, max_bytes: int) -> None:
        super().__init__(
            f"Image reference {ref!r} is {size} bytes; "
            f"exceeds the {max_bytes}-byte limit."
        )


class InvalidInputImage(Exception):
    """Raised when reference bytes cannot be decoded as an image."""

    def __init__(self, ref: str) -> None:
        super().__init__(f"Image reference {ref!r} is not a decodable image.")


def _parse_gallery_id(ref: str) -> str | None:
    """Return the gallery id for *ref*, or ``None`` if it is not a gallery ref."""
    uri_match = _IMAGE_URI_RE.match(ref)
    if uri_match:
        return uri_match.group(1)
    if _IMAGE_ID_RE.match(ref):
        return ref
    return None


def _validate(ref: str, data: bytes, content_type: str, max_bytes: int) -> str:
    """Validate size and decodability; return the resolved content type."""
    if len(data) > max_bytes:
        raise InputImageTooLarge(ref, len(data), max_bytes)
    try:
        with PILImage.open(io.BytesIO(data)) as img:
            fmt = img.format
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidInputImage(ref) from exc
    return _PIL_FORMAT_TO_MIME.get(fmt or "", content_type)


def resolve_reference(
    ref: str,
    *,
    loader: GalleryLoader,
    allow_local_files: bool,
    max_bytes: int,
) -> InputImage:
    """Resolve a single image reference into an :class:`InputImage`.

    Args:
        ref: An ``image://`` URI, a 12-hex gallery id, or a local file path.
        loader: Loads ``(data, content_type)`` for a gallery id.
        allow_local_files: Whether file-path references may be read.
        max_bytes: Maximum allowed byte size for the resolved image.

    Returns:
        The resolved :class:`InputImage`.

    Raises:
        ImageReferenceNotFound: Unknown gallery id or missing file.
        LocalFileInputDisabled: File-path ref while file input is disabled.
        InputImageTooLarge: Resolved image exceeds ``max_bytes``.
        InvalidInputImage: Bytes are not a decodable image.
    """
    gallery_id = _parse_gallery_id(ref)
    if gallery_id is not None:
        try:
            data, content_type = loader(gallery_id)
        except KeyError as exc:
            raise ImageReferenceNotFound(ref) from exc
        resolved_type = _validate(ref, data, content_type, max_bytes)
        return InputImage(data=data, content_type=resolved_type, source_id=gallery_id)

    if not allow_local_files:
        raise LocalFileInputDisabled(ref)
    path = Path(ref)
    if not path.is_file():
        raise ImageReferenceNotFound(ref)
    data = path.read_bytes()
    resolved_type = _validate(ref, data, "application/octet-stream", max_bytes)
    logger.debug("resolved_file_reference path=%s bytes=%d", ref, len(data))
    return InputImage(data=data, content_type=resolved_type, source_id=None)


def resolve_references(
    refs: Sequence[str],
    *,
    loader: GalleryLoader,
    allow_local_files: bool,
    max_bytes: int,
) -> list[InputImage]:
    """Resolve a list of references, preserving order.

    Args:
        refs: References to resolve.
        loader: Loads ``(data, content_type)`` for a gallery id.
        allow_local_files: Whether file-path references may be read.
        max_bytes: Per-image maximum byte size.

    Returns:
        Resolved :class:`InputImage` values in input order.
    """
    return [
        resolve_reference(
            ref,
            loader=loader,
            allow_local_files=allow_local_files,
            max_bytes=max_bytes,
        )
        for ref in refs
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_input_images.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/_input_images.py tests/test_input_images.py
git commit -m "feat: add input-reference resolver for gallery ids and gated file paths

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Provider protocol extension + non-Gemini guards

**Files:**
- Modify: `src/image_generation_mcp/providers/types.py` (protocol signature)
- Modify: `src/image_generation_mcp/providers/openai.py`, `providers/sd_webui.py`, `providers/placeholder.py`
- Test: `tests/test_openai_provider.py`, `tests/test_sd_webui_provider.py`, `tests/test_placeholder.py`

**Interfaces:**
- Consumes: `InputImage`, `ImageInputUnsupported` (Task 2).
- Produces: every provider's `generate()` accepts `reference_images: Sequence[InputImage] | None = None`. Non-Gemini providers raise `ImageInputUnsupported(<name>, model)` when given a non-empty list; with `None`/`[]` behavior is unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_openai_provider.py` (and mirror in `test_sd_webui_provider.py` with `"sd_webui"` and in `test_placeholder.py` with the placeholder provider; placeholder needs no API mock):

```python
async def test_openai_rejects_reference_images(openai_provider) -> None:
    from image_generation_mcp.providers.types import (
        ImageInputUnsupported,
        InputImage,
    )

    with pytest.raises(ImageInputUnsupported):
        await openai_provider.generate(
            "a cat",
            reference_images=[InputImage(data=b"x", content_type="image/png")],
        )
```

For placeholder (`tests/test_placeholder.py`):

```python
async def test_placeholder_rejects_reference_images() -> None:
    from image_generation_mcp.providers.placeholder import PlaceholderProvider
    from image_generation_mcp.providers.types import (
        ImageInputUnsupported,
        InputImage,
    )

    with pytest.raises(ImageInputUnsupported):
        await PlaceholderProvider().generate(
            "x", reference_images=[InputImage(data=b"x", content_type="image/png")]
        )
```

> Note: use the existing per-file provider fixture name (e.g. `openai_provider`, `sd_webui_provider`). If a file constructs the provider inline instead of via fixture, follow that file's existing pattern.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_openai_provider.py tests/test_sd_webui_provider.py tests/test_placeholder.py -k reference_images -v`
Expected: FAIL with `TypeError: generate() got an unexpected keyword argument 'reference_images'`.

- [ ] **Step 3: Extend the protocol and guard each non-Gemini provider**

In `providers/types.py`, update the `ImageProvider.generate()` protocol signature to add the parameter (keep all existing params, add before `progress_callback`):

```python
        reference_images: Sequence[InputImage] | None = None,
```

Add `from collections.abc import Callable, Sequence` (Sequence) to the imports, and document the new arg in the protocol docstring:

```
            reference_images: Optional input images for image-to-image edits
                or composition. Providers that do not support image input
                raise :class:`ImageInputUnsupported` when this is non-empty.
```

In **each** of `openai.py`, `sd_webui.py`, `placeholder.py`, add the same parameter to the concrete `generate()` signature and guard at the top of the method body (use the provider's own name string and `effective_model`/`model` as available; placeholder has no model so pass `model`):

```python
        if reference_images:
            from image_generation_mcp.providers.types import ImageInputUnsupported

            raise ImageInputUnsupported("openai", model)
```

Each file also needs `InputImage` and `Sequence` imported (add `Sequence` to the `collections.abc` import; import `InputImage` and `ImageInputUnsupported` from `.types`). Where a provider's signature lists params, place `reference_images: Sequence[InputImage] | None = None` immediately before `progress_callback`.

> The placeholder's `generate()` currently ignores `model`; keep `model` in its signature and pass it to `ImageInputUnsupported("placeholder", model)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openai_provider.py tests/test_sd_webui_provider.py tests/test_placeholder.py -v`
Expected: PASS (existing tests + 3 new rejection tests).

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/providers/types.py src/image_generation_mcp/providers/openai.py src/image_generation_mcp/providers/sd_webui.py src/image_generation_mcp/providers/placeholder.py tests/test_openai_provider.py tests/test_sd_webui_provider.py tests/test_placeholder.py
git commit -m "feat: extend provider protocol with reference_images; guard non-Gemini providers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Gemini single-image image-to-image

**Files:**
- Modify: `src/image_generation_mcp/providers/gemini.py`
- Test: `tests/test_gemini_provider.py`, `tests/test_gemini_discovery.py`

**Interfaces:**
- Consumes: `InputImage`, `ImageInputUnsupported`, `TooManyInputImages` (Task 2).
- Produces: Gemini `generate()` accepts `reference_images`; sends them as image parts in `contents`; advertises `supports_image_input=True, max_input_images=1`; raises `TooManyInputImages` when more than 1 is given.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gemini_provider.py`:

```python
async def test_generate_with_reference_image_sends_parts() -> None:
    from image_generation_mcp.providers.gemini import GeminiImageProvider
    from image_generation_mcp.providers.types import InputImage

    provider = GeminiImageProvider(api_key="AIza-test")

    mock_inline = MagicMock()
    mock_inline.data = b"out-png"
    mock_inline.mime_type = "image/png"
    mock_part = MagicMock()
    mock_part.inline_data = mock_inline
    mock_response = MagicMock()
    mock_response.parts = [mock_part]

    provider._client = MagicMock()
    gen = AsyncMock(return_value=mock_response)
    provider._client.aio.models.generate_content = gen

    ref = InputImage(data=b"in-png", content_type="image/png", source_id="abc")
    result = await provider.generate("make it blue", reference_images=[ref])

    assert result.image_data == b"out-png"
    # contents is a list: [prompt, <image part>]
    contents = gen.call_args.kwargs["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 2


async def test_generate_rejects_two_reference_images() -> None:
    from image_generation_mcp.providers.gemini import GeminiImageProvider
    from image_generation_mcp.providers.types import InputImage, TooManyInputImages

    provider = GeminiImageProvider(api_key="AIza-test")
    provider._client = MagicMock()
    refs = [
        InputImage(data=b"a", content_type="image/png"),
        InputImage(data=b"b", content_type="image/png"),
    ]
    with pytest.raises(TooManyInputImages):
        await provider.generate("x", reference_images=refs)
```

Add to `tests/test_gemini_discovery.py` (or wherever Gemini capabilities are asserted):

```python
async def test_gemini_advertises_image_input(gemini_provider) -> None:
    caps = await gemini_provider.discover_capabilities()
    for m in caps.models:
        assert m.supports_image_input is True
        assert m.max_input_images == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gemini_provider.py tests/test_gemini_discovery.py -k "reference or image_input" -v`
Expected: FAIL — `generate()` rejects the kwarg / capability assertion fails.

- [ ] **Step 3: Implement in `gemini.py`**

Add `Sequence` import: `from collections.abc import Sequence`. Import the new types:

```python
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
    InputImage,
    ProgressCallback,
    TooManyInputImages,
)
```

Add a module constant:

```python
_MAX_INPUT_IMAGES = 1
```

Update `generate()` signature to include `reference_images: Sequence[InputImage] | None = None` (before `progress_callback`). After computing `effective_model` and before building `config`, add:

```python
        if reference_images and len(reference_images) > _MAX_INPUT_IMAGES:
            raise TooManyInputImages(
                "gemini", effective_model, _MAX_INPUT_IMAGES, len(reference_images)
            )
```

Replace the `contents=full_prompt` call site so reference bytes are sent as parts:

```python
        contents: list[object] = [full_prompt]
        for ref in reference_images or []:
            contents.append(
                types.Part.from_bytes(data=ref.data, mime_type=ref.content_type)
            )

        try:
            response = await self._client.aio.models.generate_content(
                model=effective_model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            self._handle_error(exc)
```

In `discover_capabilities()`, add to each `ModelCapabilities(...)`:

```python
                    supports_image_input=True,
                    max_input_images=_MAX_INPUT_IMAGES,
```

Update the `generate()` docstring to document `reference_images` (single image; image-to-image edit) and the `TooManyInputImages` raise.

> `types.Part.from_bytes` is a `MagicMock` attribute under the `_mock_genai` fixture, so it returns a mock — the test asserts on `contents` length, not on the SDK call internals. Confirm the real `google-genai` API at implementation time via the openai-docs/context7 path is **not** applicable here; use the Gemini docs (`google-genai` `types.Part.from_bytes(data=..., mime_type=...)` is the documented image-input constructor).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gemini_provider.py tests/test_gemini_discovery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/providers/gemini.py tests/test_gemini_provider.py tests/test_gemini_discovery.py
git commit -m "feat: Gemini single-image image-to-image input

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Thread `reference_images` through the service + generalize provenance

**Files:**
- Modify: `src/image_generation_mcp/service.py`
- Modify: `src/image_generation_mcp/_server_resources.py` (metadata resource emits `source_image_ids`)
- Test: `tests/test_service.py`, `tests/test_resources.py`

**Interfaces:**
- Consumes: `InputImage` (Task 2), the provider `generate()` extension (Tasks 5–6).
- Produces:
  - `ImageService.generate(..., reference_images: Sequence[InputImage] | None = None)` passes the list to the resolved provider.
  - `ImageRecord.source_image_ids: list[str]` (replaces the singular `source_image_id`).
  - `ImageService.register_image(..., source_image_ids: list[str] | None = None)`; sidecar writes `source_image_ids`; `_load_registry` reads `source_image_ids`, falling back to a legacy `source_image_id` scalar.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_service.py`:

```python
async def test_generate_passes_reference_images_to_provider(tmp_path) -> None:
    from unittest.mock import AsyncMock
    from image_generation_mcp.service import ImageService
    from image_generation_mcp.providers.types import ImageResult, InputImage

    service = ImageService(scratch_dir=tmp_path, default_provider="fake")
    fake = AsyncMock()
    fake.generate = AsyncMock(
        return_value=ImageResult(image_data=b"x", content_type="image/png")
    )
    service.register_provider("fake", fake)

    refs = [InputImage(data=b"in", content_type="image/png", source_id="abc")]
    await service.generate("p", provider="fake", reference_images=refs)

    assert fake.generate.call_args.kwargs["reference_images"] == refs


def test_register_image_records_source_ids(tmp_path) -> None:
    from image_generation_mcp.service import ImageService
    from image_generation_mcp.providers.types import ImageResult
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    service = ImageService(scratch_dir=tmp_path)
    record = service.register_image(
        ImageResult(image_data=buf.getvalue(), content_type="image/png"),
        "gemini",
        prompt="p",
        source_image_ids=["abc", "def"],
    )
    assert record.source_image_ids == ["abc", "def"]


def test_load_registry_reads_legacy_source_image_id(tmp_path) -> None:
    import json
    from PIL import Image
    import io
    from image_generation_mcp.service import ImageService

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    (tmp_path / "aaaaaaaaaaaa-original.png").write_bytes(buf.getvalue())
    (tmp_path / "aaaaaaaaaaaa.json").write_text(
        json.dumps(
            {
                "id": "aaaaaaaaaaaa",
                "prompt": "p",
                "negative_prompt": None,
                "provider": "gemini",
                "aspect_ratio": "1:1",
                "quality": "standard",
                "content_type": "image/png",
                "original_filename": "aaaaaaaaaaaa-original.png",
                "original_dimensions": [4, 4],
                "provider_metadata": {},
                "created_at": "2026-01-01T00:00:00+00:00",
                "source_image_id": "legacy123456",
            }
        )
    )
    service = ImageService(scratch_dir=tmp_path)
    assert service.get_image("aaaaaaaaaaaa").source_image_ids == ["legacy123456"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_service.py -k "reference or source" -v`
Expected: FAIL — `generate()` rejects the kwarg / `source_image_ids` attribute missing.

- [ ] **Step 3: Implement in `service.py`**

`ImageRecord`: replace `source_image_id: str | None = None` with:

```python
    source_image_ids: list[str] = field(default_factory=list)
```

`ImageService.generate()`: add `reference_images: Sequence[InputImage] | None = None` to the signature (import `Sequence` from `collections.abc` and `InputImage` from `.providers.types`), and pass it to `resolved_provider.generate(...)`:

```python
            reference_images=reference_images,
```

`register_image()`: replace the `source_image_id: str | None = None` parameter with `source_image_ids: list[str] | None = None`; in the body use `ids = list(source_image_ids or [])`; set `source_image_ids=ids` on the `ImageRecord`; in the sidecar dict replace `"source_image_id": record.source_image_id` with `"source_image_ids": record.source_image_ids`.

`_load_registry()`: when building each record from sidecar JSON, resolve provenance with legacy fallback:

```python
            source_ids = data.get("source_image_ids")
            if source_ids is None:
                legacy = data.get("source_image_id")
                source_ids = [legacy] if legacy else []
```

and pass `source_image_ids=source_ids` to the `ImageRecord(...)` construction.

Find the existing caller `_save_edited_image` (in `_server_tools.py`) which passes `source_image_id=...` to `register_image` — update it to `source_image_ids=[source_image_id]`.

In `_server_resources.py`, locate where the `image://{id}/metadata` payload is built and emit `"source_image_ids": record.source_image_ids` (replace any `source_image_id` key).

> Run `grep -rn "source_image_id" src/` and update **every** reference so the singular field is fully gone from first-party code (the legacy read in `_load_registry` is the only place the old key name survives, and only as an on-disk sidecar key).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_service.py tests/test_resources.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/image_generation_mcp/service.py src/image_generation_mcp/_server_resources.py src/image_generation_mcp/_server_tools.py tests/test_service.py tests/test_resources.py
git commit -m "feat: thread reference_images through service; generalize provenance to source_image_ids

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `transform_image` MCP tool

**Files:**
- Modify: `src/image_generation_mcp/_server_tools.py`
- Test: `tests/test_tools.py`, `tests/test_mcp_integration.py`

**Interfaces:**
- Consumes: `resolve_references` (Task 4), `ImageService.generate(reference_images=...)` + `register_image(source_image_ids=...)` (Task 7), capability fields (Task 3).
- Produces: a `transform_image` tool registered only when ≥1 provider model reports `supports_image_input`.

Behavior contract:
1. Validate `aspect_ratio`/`quality`/`background` exactly as `generate_image` does.
2. Resolve `reference_images` **synchronously** via `resolve_references` (loader built from `service.get_image`), so resolution errors surface in the tool result, not the background task. Map resolver exceptions to `ValueError` with the resolver message.
3. Resolve provider name; verify the chosen provider has a model with `supports_image_input` and `max_input_images >= len(refs)`; otherwise raise `ValueError` naming Gemini.
4. Enqueue a background task mirroring `generate_image`, calling `service.generate(..., reference_images=resolved)` and `service.register_image(..., source_image_ids=[r.source_id for r in resolved if r.source_id])`.
5. Return the same pending-status `ToolResult` + `ResourceLink` shape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tools.py` (follow the file's existing harness for invoking a tool against a service with a fake provider; reuse whatever fixture other tool tests use — e.g. a registered fake provider that returns an `ImageResult`):

```python
async def test_transform_image_rejects_unknown_reference(transform_capable_server) -> None:
    # transform_capable_server: a FastMCP/service harness with a provider whose
    # capabilities report supports_image_input=True (mirror existing tool-test setup).
    result = await transform_capable_server.call_tool(
        "transform_image",
        {"prompt": "make it blue", "reference_images": ["deadbeef0000"]},
    )
    text = _text_of(result)  # helper used elsewhere in this file
    assert "not found" in text.lower() or "error" in text.lower()


async def test_transform_image_absent_without_image_input(text_only_server) -> None:
    tools = await text_only_server.list_tools()
    assert "transform_image" not in {t.name for t in tools}
```

> If `tests/test_tools.py` has no existing pattern for "tool absent" assertions, add the registration-conditional test in `tests/test_mcp_capabilities_surface.py` instead, matching its existing style.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools.py -k transform -v`
Expected: FAIL — `transform_image` is not a registered tool.

- [ ] **Step 3: Implement the tool in `_server_tools.py`**

Add a module-level helper near the top:

```python
def _any_provider_supports_image_input(service: ImageService) -> bool:
    """Return True if any discovered model accepts reference images."""
    return any(
        m.supports_image_input
        for caps in service.capabilities.values()
        for m in caps.models
    )
```

In `register_tools`, gate the registration. Because capabilities are discovered during lifespan (after `register_tools` runs at construction), register the tool unconditionally **but** have it return a clear error if no provider supports image input — OR, preferred, register conditionally using the same mechanism other conditional tools use. Match the existing pattern: `create_download_link` is gated on `transport`; image-input gating must be on runtime capability, which is only known post-discovery. **Decision:** register `transform_image` always, and in its body short-circuit with a `ValueError` ("No configured provider supports reference-image input; configure Gemini.") when `_any_provider_supports_image_input(service)` is False. Implement the `test_transform_image_absent_without_image_input` test instead as `test_transform_image_errors_without_image_input` asserting that error text.

> Update Step 1's second test accordingly: assert the error message rather than tool absence. (This keeps registration static, matching FastMCP's construction-time registration; capability discovery is not available at registration time.)

Tool body:

```python
    @mcp.tool(
        tags={"write"},
        task=True,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        icons=[Icon(src=_LUCIDE.format("images"), mimeType="image/svg+xml")],
    )
    async def transform_image(
        prompt: str,
        reference_images: list[str],
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Edit or transform image(s) using a model that accepts image input.

        Supply one or more reference images (gallery ``image_id``, an
        ``image://`` URI, or — when enabled — a local file path) plus a
        prompt describing the change. Currently served by Gemini models
        (single reference image); call ``list_providers`` and check
        ``supports_image_input`` / ``max_input_images`` to route.

        Returns immediately; poll ``check_generation_status(image_id)`` and
        then ``show_image(uri=original_uri)`` once completed — same flow as
        ``generate_image``.

        Args:
            prompt: Description of the desired edit/transformation.
            reference_images: Gallery ids / ``image://`` URIs and/or local
                file paths (file paths require
                ``IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT=true``).
            provider: Provider to use, or ``"auto"``.
            negative_prompt: Things to avoid (provider support varies).
            aspect_ratio: Desired aspect ratio.
            quality: ``"standard"`` or ``"hd"``.
            background: ``"opaque"`` or ``"transparent"`` (provider-dependent).
            model: Specific model id; see ``list_providers``.

        Returns:
            JSON with ``status``, ``image_id``, ``original_uri`` (pending).
        """
        # 1. Validate enums (reuse generate_image's checks)
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            raise ValueError(
                f"Unsupported aspect_ratio '{aspect_ratio}'. "
                f"Supported: {list(SUPPORTED_ASPECT_RATIOS)}"
            )
        if quality not in SUPPORTED_QUALITY_LEVELS:
            raise ValueError(
                f"Unsupported quality '{quality}'. "
                f"Supported: {list(SUPPORTED_QUALITY_LEVELS)}"
            )
        if background not in SUPPORTED_BACKGROUNDS:
            raise ValueError(
                f"Unsupported background '{background}'. "
                f"Supported: {', '.join(SUPPORTED_BACKGROUNDS)}"
            )
        if not reference_images:
            raise ValueError("transform_image requires at least one reference image.")
        if not _any_provider_supports_image_input(service):
            raise ValueError(
                "No configured provider supports reference-image input. "
                "Configure Gemini (IMAGE_GENERATION_MCP_GOOGLE_API_KEY)."
            )

        # 2. Resolve references synchronously
        def _loader(image_id: str) -> tuple[bytes, str]:
            try:
                record = service.get_image(image_id)
            except ImageProviderError as exc:
                raise KeyError(image_id) from exc
            return record.original_path.read_bytes(), record.content_type

        try:
            resolved = await asyncio.to_thread(
                resolve_references,
                reference_images,
                loader=_loader,
                allow_local_files=config.allow_local_file_input,
                max_bytes=config.max_input_image_bytes,
            )
        except (
            ImageReferenceNotFound,
            LocalFileInputDisabled,
            InputImageTooLarge,
            InvalidInputImage,
        ) as exc:
            raise ValueError(str(exc)) from exc

        # 3. Resolve provider + capability routing
        resolved_name = await asyncio.to_thread(
            service.resolve_provider_name, provider, prompt, background=background
        )
        caps = service.capabilities.get(resolved_name)
        capable = [
            m
            for m in (caps.models if caps else ())
            if m.supports_image_input
            and (model is None or m.model_id == model)
            and m.max_input_images >= len(resolved)
        ]
        if not capable:
            raise ValueError(
                f"Provider '{resolved_name}' has no model accepting "
                f"{len(resolved)} reference image(s). Use a Gemini model."
            )

        # 4. Paid-provider elicitation (reuse generate_image's block verbatim)
        #    -> copy the elicitation confirmation block from generate_image here.

        # 5. Enqueue background task (mirror generate_image)
        image_id = service.allocate_image_id()
        service.register_pending(
            image_id=image_id,
            prompt=prompt,
            provider=resolved_name,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
            model=model,
        )

        async def _background_transform() -> None:
            try:
                provider_name, result = await service.generate(
                    prompt,
                    provider=resolved_name,
                    negative_prompt=negative_prompt,
                    aspect_ratio=aspect_ratio,
                    quality=quality,
                    background=background,
                    model=model,
                    reference_images=resolved,
                )
                await asyncio.to_thread(
                    service.register_image,
                    result,
                    provider_name,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    aspect_ratio=aspect_ratio,
                    quality=quality,
                    background=background,
                    image_id=image_id,
                    source_image_ids=[r.source_id for r in resolved if r.source_id],
                )
                service.complete_pending(image_id)
            except ImageContentPolicyError:
                service.fail_pending(
                    image_id,
                    "Content policy rejected the request. Try rephrasing.",
                )
            except ImageProviderConnectionError:
                service.fail_pending(
                    image_id, "Provider is unreachable. Try again later."
                )
            except Exception as exc:
                service.fail_pending(image_id, str(exc))
                logger.error(
                    "Background transform failed: %s: %s", image_id, exc, exc_info=True
                )

        task = asyncio.create_task(_background_transform())
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

        metadata: dict[str, Any] = {
            "status": "generating",
            "image_id": image_id,
            "prompt": prompt,
            "provider": resolved_name,
            "source_image_ids": [r.source_id for r in resolved if r.source_id],
            "original_uri": f"image://{image_id}/view",
            "metadata_uri": f"image://{image_id}/metadata",
        }
        return ToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, indent=2)),
                ResourceLink(
                    type="resource_link",
                    uri=AnyUrl(f"image://{image_id}/view"),
                    name="Transformed image (generating)",
                ),
            ]
        )
```

Add the imports at the top of `_server_tools.py`:

```python
from image_generation_mcp._input_images import (
    ImageReferenceNotFound,
    InputImageTooLarge,
    InvalidInputImage,
    LocalFileInputDisabled,
    resolve_references,
)
```

Copy the paid-provider elicitation block from `generate_image` (lines around the `config.paid_providers` check) into step 4 verbatim, adapted to `transform_image`'s variables.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools.py tests/test_mcp_integration.py -k transform -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite + gates**

```bash
uv run pytest -x -q
uv run ruff check --fix . && uv run ruff format . && uv run ruff format --check .
uv run mypy src/ tests/
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/image_generation_mcp/_server_tools.py tests/test_tools.py tests/test_mcp_integration.py
git commit -m "feat: add transform_image tool for reference-image input

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Documentation

**Files:**
- Modify: `README.md`, `docs/tools.md`, `docs/configuration.md`, `docs/providers/gemini.md`

**Interfaces:** none (docs only). Required by hard gate #5.

- [ ] **Step 1: Document the tool**

In `docs/tools.md` and the README tool table, add a `transform_image` entry: purpose (image-to-image edit / transform via reference images), parameters (`prompt`, `reference_images`, `provider`, `negative_prompt`, `aspect_ratio`, `quality`, `background`, `model`), the gallery-id/URI/file-path input forms, the poll-then-`show_image` flow, and the "Gemini single image only this release" note.

- [ ] **Step 2: Document the config vars**

In `docs/configuration.md` and the README config table, add:
- `IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT` (default `false`) — enables local file paths as `transform_image` references; security note that it grants callers server-filesystem read access via path, so enable only for trusted callers / local deployments.
- `IMAGE_GENERATION_MCP_MAX_INPUT_IMAGE_BYTES` (default `20971520`) — per-reference byte cap.

- [ ] **Step 3: Document Gemini image input**

In `docs/providers/gemini.md`, add a short "Image input (image-to-image)" section: Gemini accepts one reference image this release; describe edit-by-prompt usage; note `supports_image_input` / `max_input_images` appear in `list_providers`; forward-note that multi-image composition is tracked in #260 (only as a doc cross-link, never in code/docstrings).

- [ ] **Step 4: Verify docs build**

Run: `uv run mkdocs build 2>&1 | tail -5` (if mkdocs is configured) or confirm Markdown renders.
Expected: no build errors.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/tools.md docs/configuration.md docs/providers/gemini.md
git commit -m "docs: document transform_image, file-input config, Gemini image input

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Pre-PR verification (run before `gh pr create`)

- [ ] `uv run pytest -x -q` — all pass.
- [ ] `uv run ruff check --fix .` → `uv run ruff format .` → `uv run ruff format --check .` — clean.
- [ ] `uv run mypy src/ tests/` — no errors.
- [ ] `uv run pytest --cov=image_generation_mcp --cov-report=term-missing` — patch coverage ≥ 80% on changed modules (`_input_images.py`, `config.py`, `capabilities.py`, `types.py`, `gemini.py`, `service.py`, `_server_tools.py`).
- [ ] `grep -rn "source_image_id\b" src/` — only the legacy sidecar-read in `service._load_registry` remains; the singular field is gone from first-party APIs.
- [ ] Run the `preflight-circus` skill (five-lens local review of `BASE..HEAD`) before pushing.
- [ ] PR body includes `Closes #257` and the agent-attribution signature.

## Self-Review notes (author)

- **Spec coverage:** every Issue-#257 deliverable maps to a task — resolver (T4), config gate (T1), protocol extension + errors (T2/T5), capability fields (T3), Gemini single-image i2i (T6), provenance `source_image_ids` (T7), `transform_image` tool (T8), docs (T9). ✔
- **Adjustment captured during writing:** `transform_image` is registered statically (FastMCP registers at construction, before capability discovery), so the "tool absent without image input" behavior becomes a clear runtime error instead — Task 8 Step 3 records this and revises the Step 1 test accordingly.
- **Type consistency:** `source_image_ids: list[str]`, `reference_images: Sequence[InputImage] | None`, `InputImage(data, content_type, source_id)`, `resolve_references(refs, *, loader, allow_local_files, max_bytes)` used identically across tasks.
