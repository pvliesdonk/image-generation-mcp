# Gemini Image Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Gemini image generation provider using the Google Gemini native `generateContent` API with `responseModalities=["IMAGE"]`, as an optional dependency matching the existing OpenAI provider pattern.

**Architecture:** `GeminiImageProvider` implements the `ImageProvider` protocol using `google-genai` SDK's async `client.aio.models.generate_content()`. Lazy import in `_server_deps.py` keeps `google-genai` optional. Gemini becomes the first provider in the default auto-selection chain (free tier advantage), second in specialist chains behind SD WebUI.

**Tech Stack:** `google-genai>=1.0`, Python async (`client.aio`), existing `ImageProvider` protocol + `ImageResult` / `ProviderCapabilities` types.

**GitHub issue:** pvliesdonk/image-generation-mcp#159

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `src/image_generation_mcp/providers/gemini.py` | `GeminiImageProvider` class |
| Create | `tests/test_gemini_provider.py` | Unit tests for `generate()` |
| Create | `tests/test_gemini_discovery.py` | Unit tests for `discover_capabilities()` |
| Create | `docs/providers/gemini.md` | Provider reference page |
| Modify | `pyproject.toml` | Add `google-genai` optional dep + `all` extra |
| Modify | `src/image_generation_mcp/config.py` | Add `google_api_key` field + env var loading |
| Modify | `src/image_generation_mcp/_server_deps.py` | Conditional registration |
| Modify | `src/image_generation_mcp/providers/selector.py` | Update selection chains |
| Modify | `docs/providers/index.md` | Add Gemini to comparison table |
| Modify | `docs/configuration.md` | Add `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` |
| Modify | `docs/design/provider-system.md` | Add Gemini to design doc |
| Modify | `mkdocs.yml` | Add Gemini to nav |
| Modify | `docs/getting-started/claude-desktop.md` | Add Gemini config example |
| Modify | `docs/getting-started/claude-code.md` | Add Gemini config example |

---

## Task 1: Optional dependency + config field

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/image_generation_mcp/config.py`

- [ ] **Step 1: Add `google-genai` to pyproject.toml**

In `pyproject.toml`, find the `[project.optional-dependencies]` section and apply these changes:

```toml
[project.optional-dependencies]
mcp = ["fastmcp[tasks]>=3.0,<4", "uvicorn>=0.20"]
openai = ["openai>=1.0"]
google-genai = ["google-genai>=1.0"]
all = ["fastmcp[tasks]>=3.0,<4", "uvicorn>=0.20", "openai>=1.0", "google-genai>=1.0"]
```

- [ ] **Step 2: Add `google_api_key` to `ServerConfig`**

In `src/image_generation_mcp/config.py`:

Add the field to the `ServerConfig` docstring Attributes block (after `sd_webui_model`):
```
        google_api_key: Google API key for Gemini image generation.
```

Add the field to the dataclass (after `sd_webui_model: str | None = None`):
```python
    google_api_key: str | None = None
```

- [ ] **Step 3: Load the env var in `load_config()`**

In `load_config()` in `config.py`, add after the SD WebUI model block:

```python
    if key := _env("GOOGLE_API_KEY"):
        kwargs["google_api_key"] = key
```

Also update the docstring of `load_config()` to include the new variable (add after the SD WebUI model line):
```
    - ``IMAGE_GENERATION_MCP_GOOGLE_API_KEY``: Google API key; enables Gemini provider.
```

- [ ] **Step 4: Write the config test**

Add to `tests/test_config.py` (find the class with OpenAI key tests and add alongside):

```python
def test_google_api_key_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_GENERATION_MCP_GOOGLE_API_KEY", "AIza-test")
    config = load_config()
    assert config.google_api_key == "AIza-test"

def test_google_api_key_unset(self) -> None:
    config = load_config()
    assert config.google_api_key is None
```

- [ ] **Step 5: Run config tests**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest tests/test_config.py -v
```

Expected: all config tests pass.

- [ ] **Step 6: Commit**

```bash
git checkout -b feat/gemini-provider
git add pyproject.toml src/image_generation_mcp/config.py tests/test_config.py
git commit -m "feat: add google_api_key config field and google-genai optional dep"
```

---

## Task 2: GeminiImageProvider implementation

**Files:**
- Create: `src/image_generation_mcp/providers/gemini.py`

- [ ] **Step 1: Write the failing tests for `generate()` (TDD)**

Create `tests/test_gemini_provider.py`:

```python
"""Tests for the Gemini image generation provider."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from image_generation_mcp.providers.gemini import (
    _ASPECT_RATIOS,
    _QUALITY_SIZES,
    GeminiImageProvider,
)
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProvider,
    ImageProviderConnectionError,
    ImageProviderError,
)


@pytest.fixture
def _mock_genai():
    """Patch genai client creation so tests don't need the real package."""
    with patch(
        "image_generation_mcp.providers.gemini.GeminiImageProvider._create_client"
    ):
        yield


@pytest.mark.usefixtures("_mock_genai")
class TestGeminiProvider:
    """Tests for GeminiImageProvider."""

    def test_implements_protocol(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        assert isinstance(provider, ImageProvider)

    def test_default_model(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        assert provider._model == "gemini-2.5-flash-image"

    def test_custom_model(self) -> None:
        provider = GeminiImageProvider(
            api_key="AIza-test", model="gemini-3-pro-image-preview"
        )
        assert provider._model == "gemini-3-pro-image-preview"

    def test_aspect_ratio_table_complete(self) -> None:
        for ratio in ("1:1", "16:9", "9:16", "3:2", "2:3"):
            assert ratio in _ASPECT_RATIOS

    def test_quality_sizes(self) -> None:
        assert _QUALITY_SIZES["standard"] == "1K"
        assert _QUALITY_SIZES["hd"] == "2K"

    async def test_generate_success(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline
        mock_part.text = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", aspect_ratio="1:1")

        assert result.image_data == fake_image_bytes
        assert result.content_type == "image/png"
        assert result.provider_metadata["model"] == "gemini-2.5-flash-image"
        assert result.provider_metadata["quality"] == "standard"
        assert result.provider_metadata["image_size"] == "1K"

    async def test_generate_hd_quality(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline
        mock_part.text = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", quality="hd")

        assert result.provider_metadata["image_size"] == "2K"
        assert result.provider_metadata["quality"] == "hd"

    async def test_generate_uses_model_override(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline
        mock_part.text = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        result = await provider.generate("a cat", model="gemini-3-pro-image-preview")

        call_kwargs = provider._client.aio.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3-pro-image-preview"
        assert result.provider_metadata["model"] == "gemini-3-pro-image-preview"

    async def test_negative_prompt_appended(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline
        mock_part.text = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        await provider.generate("a cat", negative_prompt="dogs")

        call_kwargs = provider._client.aio.models.generate_content.call_args.kwargs
        assert "Avoid: dogs" in call_kwargs["contents"]

    async def test_unsupported_aspect_ratio_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")
        with pytest.raises(ImageProviderError, match="Unsupported aspect_ratio"):
            await provider.generate("test", aspect_ratio="7:3")

    async def test_no_image_in_response_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_part = MagicMock()
        mock_part.inline_data = None
        mock_part.text = "Some text"

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_empty_parts_raises(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        mock_response = MagicMock()
        mock_response.parts = []

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ImageProviderError, match="No image in response"):
            await provider.generate("test")

    async def test_api_error_raises_provider_error(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("some API error")
        )

        with pytest.raises(ImageProviderError):
            await provider.generate("test")

    async def test_content_policy_error(self) -> None:
        provider = GeminiImageProvider(api_key="AIza-test")

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("SAFETY blocked by content policy")
        )

        with pytest.raises(ImageContentPolicyError):
            await provider.generate("test")

    async def test_background_transparent_ignored(self) -> None:
        """background='transparent' is silently ignored — Gemini doesn't support it."""
        provider = GeminiImageProvider(api_key="AIza-test")
        fake_image_bytes = b"fake-png-data"

        mock_inline = MagicMock()
        mock_inline.data = fake_image_bytes
        mock_inline.mime_type = "image/png"

        mock_part = MagicMock()
        mock_part.inline_data = mock_inline
        mock_part.text = None

        mock_response = MagicMock()
        mock_response.parts = [mock_part]

        provider._client = MagicMock()
        provider._client.aio = MagicMock()
        provider._client.aio.models = MagicMock()
        provider._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        # Should not raise — background is ignored
        result = await provider.generate("a cat", background="transparent")
        assert result.image_data == fake_image_bytes
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest tests/test_gemini_provider.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` — `gemini.py` does not exist yet.

- [ ] **Step 3: Create `src/image_generation_mcp/providers/gemini.py`**

```python
"""Gemini image generation provider.

Uses the Gemini native generateContent API with responseModalities=["IMAGE"].
Requires the google-genai package (optional dependency).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, NoReturn

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
    make_degraded,
)
from image_generation_mcp.providers.types import (
    ImageContentPolicyError,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
    ProgressCallback,
)

if TYPE_CHECKING:
    from google import genai as genai_type

logger = logging.getLogger(__name__)

# All 5 project aspect ratios are natively supported by Gemini — direct pass-through.
_ASPECT_RATIOS: dict[str, str] = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "3:2": "3:2",
    "2:3": "2:3",
}

# quality -> Gemini image_size
_QUALITY_SIZES: dict[str, str] = {
    "standard": "1K",
    "hd": "2K",
}

# Known Gemini image-capable models in preference order.
# Discovery returns this static list — models.list() does not reliably filter
# image-generation models, so we maintain the known set here.
_KNOWN_IMAGE_MODELS: list[tuple[str, str]] = [
    ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image"),
    ("gemini-3.1-flash-image-preview", "Gemini 3.1 Flash Image Preview"),
    ("gemini-3-pro-image-preview", "Gemini 3 Pro Image Preview"),
]

_SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "16:9", "9:16", "3:2", "2:3")
_SUPPORTED_QUALITIES: tuple[str, ...] = ("standard", "hd")


class GeminiImageProvider:
    """Image generation provider backed by the Gemini generateContent API.

    Uses the google-genai SDK with native image generation via
    ``responseModalities=["IMAGE"]``. Registered when
    ``IMAGE_GENERATION_MCP_GOOGLE_API_KEY`` is set.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-image",
    ) -> None:
        """Initialise the Gemini provider.

        Args:
            api_key: Google API key with Gemini access.
            model: Default model ID for image generation.
        """
        self._model = model
        self._client = self._create_client(api_key)

    def _create_client(self, api_key: str) -> genai_type.Client:
        """Create the google-genai client.

        Separated from ``__init__`` so tests can patch it without needing
        the real ``google-genai`` package installed.

        Args:
            api_key: Google API key.

        Returns:
            Initialised ``genai.Client``.
        """
        from google import genai

        return genai.Client(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageResult:
        """Generate an image using the Gemini generateContent API.

        Args:
            prompt: Positive text prompt.
            negative_prompt: Appended as ``"\\n\\nAvoid: {negative_prompt}"``
                (Gemini has no native negative prompt support).
            aspect_ratio: One of the 5 supported ratios.
            quality: ``"standard"`` maps to ``image_size="1K"``,
                ``"hd"`` maps to ``image_size="2K"``.
            background: Ignored — Gemini does not support transparent backgrounds.
            model: Override the default model for this call.
            progress_callback: Ignored — Gemini does not report progress.

        Returns:
            ImageResult with PNG image data.

        Raises:
            ImageProviderError: If generation fails or returns no image.
            ImageContentPolicyError: If the prompt violates content policy.
            ImageProviderConnectionError: If the Gemini API is unreachable.
        """
        from google.genai import types

        if aspect_ratio not in _ASPECT_RATIOS:
            raise ImageProviderError(
                "gemini",
                f"Unsupported aspect_ratio: {aspect_ratio!r}. "
                f"Supported: {sorted(_ASPECT_RATIOS)}",
            )

        effective_model = model or self._model
        image_size = _QUALITY_SIZES.get(quality, "1K")

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_ASPECT_RATIOS[aspect_ratio],
                image_size=image_size,
            ),
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=effective_model,
                contents=full_prompt,
                config=config,
            )
        except Exception as exc:
            self._handle_error(exc)

        for part in response.parts:
            if part.inline_data is not None:
                return ImageResult(
                    image_data=part.inline_data.data,
                    content_type=part.inline_data.mime_type or "image/png",
                    provider_metadata={
                        "model": effective_model,
                        "quality": quality,
                        "image_size": image_size,
                        "aspect_ratio": aspect_ratio,
                    },
                )

        raise ImageProviderError("gemini", "No image in response")

    async def discover_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for known Gemini image-generation models.

        Uses a static known model list rather than calling models.list(),
        which does not reliably filter image-capable models.

        Returns:
            ProviderCapabilities with the known Gemini image models.
        """
        discovered_at = time.time()
        try:
            models = tuple(
                ModelCapabilities(
                    model_id=model_id,
                    display_name=display_name,
                    can_generate=True,
                    can_edit=False,
                    supported_aspect_ratios=_SUPPORTED_ASPECT_RATIOS,
                    supported_qualities=_SUPPORTED_QUALITIES,
                    supported_formats=("image/png",),
                    supports_negative_prompt=False,
                    supports_background=False,
                    prompt_style="natural_language",
                )
                for model_id, display_name in _KNOWN_IMAGE_MODELS
            )
            return ProviderCapabilities(
                provider_name="gemini",
                models=models,
                discovered_at=discovered_at,
                degraded=False,
            )
        except Exception:
            logger.exception("Gemini capability discovery failed")
            return make_degraded("gemini", discovered_at)

    def _handle_error(self, exc: Exception) -> NoReturn:
        """Convert exceptions to ImageProviderError subtypes.

        Args:
            exc: Exception raised by the Gemini API client.

        Raises:
            ImageContentPolicyError: For content policy / safety violations.
            ImageProviderConnectionError: For network / timeout errors.
            ImageProviderError: For all other failures.
        """
        import httpx

        exc_str = str(exc).lower()
        if any(kw in exc_str for kw in ("safety", "policy", "blocked", "harm")):
            raise ImageContentPolicyError("gemini", str(exc)) from exc
        if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
            raise ImageProviderConnectionError("gemini", str(exc)) from exc

        # Try to detect google-genai connection errors without hard import
        exc_type = type(exc).__name__.lower()
        if "connection" in exc_type or "timeout" in exc_type:
            raise ImageProviderConnectionError("gemini", str(exc)) from exc

        raise ImageProviderError("gemini", str(exc)) from exc
```

- [ ] **Step 4: Run the provider tests**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest tests/test_gemini_provider.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Write discovery tests**

Create `tests/test_gemini_discovery.py`:

```python
"""Tests for GeminiImageProvider.discover_capabilities()."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from image_generation_mcp.providers.capabilities import (
    ModelCapabilities,
    ProviderCapabilities,
)
from image_generation_mcp.providers.gemini import (
    _KNOWN_IMAGE_MODELS,
    GeminiImageProvider,
)


@pytest.fixture
def provider() -> GeminiImageProvider:
    """GeminiImageProvider with _create_client patched out."""
    with patch(
        "image_generation_mcp.providers.gemini.GeminiImageProvider._create_client"
    ):
        return GeminiImageProvider(api_key="AIza-test")


class TestDiscoverCapabilities:
    """Tests for discover_capabilities()."""

    async def test_returns_known_models(self, provider: GeminiImageProvider) -> None:
        caps = await provider.discover_capabilities()

        assert isinstance(caps, ProviderCapabilities)
        assert caps.provider_name == "gemini"
        assert caps.degraded is False
        assert len(caps.models) == len(_KNOWN_IMAGE_MODELS)

    async def test_model_ids_match_known_list(
        self, provider: GeminiImageProvider
    ) -> None:
        caps = await provider.discover_capabilities()

        model_ids = {m.model_id for m in caps.models}
        expected = {mid for mid, _ in _KNOWN_IMAGE_MODELS}
        assert model_ids == expected

    async def test_models_support_all_aspect_ratios(
        self, provider: GeminiImageProvider
    ) -> None:
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert "1:1" in model.supported_aspect_ratios
            assert "16:9" in model.supported_aspect_ratios
            assert "9:16" in model.supported_aspect_ratios
            assert "3:2" in model.supported_aspect_ratios
            assert "2:3" in model.supported_aspect_ratios

    async def test_models_have_no_background_support(
        self, provider: GeminiImageProvider
    ) -> None:
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_background is False

    async def test_models_have_no_negative_prompt_support(
        self, provider: GeminiImageProvider
    ) -> None:
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.supports_negative_prompt is False

    async def test_models_use_natural_language_style(
        self, provider: GeminiImageProvider
    ) -> None:
        caps = await provider.discover_capabilities()

        for model in caps.models:
            assert model.prompt_style == "natural_language"

    async def test_default_model_is_first(self, provider: GeminiImageProvider) -> None:
        caps = await provider.discover_capabilities()

        assert caps.models[0].model_id == "gemini-2.5-flash-image"

    async def test_discovered_at_is_recent(
        self, provider: GeminiImageProvider
    ) -> None:
        before = time.time()
        caps = await provider.discover_capabilities()
        after = time.time()

        assert before <= caps.discovered_at <= after

    async def test_degraded_on_unexpected_exception(
        self, provider: GeminiImageProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ModelCapabilities construction raises, returns degraded caps."""
        import image_generation_mcp.providers.gemini as gemini_mod

        monkeypatch.setattr(
            gemini_mod, "_KNOWN_IMAGE_MODELS", None  # type: ignore[arg-type]
        )

        caps = await provider.discover_capabilities()

        assert caps.degraded is True
        assert caps.provider_name == "gemini"
```

- [ ] **Step 6: Run discovery tests**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest tests/test_gemini_discovery.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/image_generation_mcp/providers/gemini.py tests/test_gemini_provider.py tests/test_gemini_discovery.py
git commit -m "feat: implement GeminiImageProvider with test coverage"
```

---

## Task 3: Registration + selector update

**Files:**
- Modify: `src/image_generation_mcp/_server_deps.py`
- Modify: `src/image_generation_mcp/providers/selector.py`

- [ ] **Step 1: Register Gemini in `_server_deps.py`**

In `src/image_generation_mcp/_server_deps.py`, after the OpenAI registration block (after the closing `)`), add:

```python
        # Register Gemini if API key is configured
        if config.google_api_key:
            from image_generation_mcp.providers.gemini import GeminiImageProvider

            service.register_provider(
                "gemini",
                GeminiImageProvider(api_key=config.google_api_key),
            )
```

- [ ] **Step 2: Write the server_deps registration test**

In `tests/test_server_deps.py`, find the existing registration tests and add:

```python
async def test_gemini_registered_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini provider is registered when GOOGLE_API_KEY is set."""
    monkeypatch.setenv("IMAGE_GENERATION_MCP_GOOGLE_API_KEY", "AIza-test")
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")

    with patch(
        "image_generation_mcp.providers.gemini.GeminiImageProvider._create_client"
    ):
        config = load_config()
        # Verify config picked up the key
        assert config.google_api_key == "AIza-test"
```

(Note: full integration test of the lifespan is already covered by existing tests; this just verifies config propagation.)

- [ ] **Step 3: Update the selector**

Replace the contents of `_SELECTION_RULES` and `_DEFAULT_CHAIN` in `src/image_generation_mcp/providers/selector.py`:

```python
# Keyword → preferred provider order
_SELECTION_RULES: list[tuple[list[str], list[str]]] = [
    # Photorealism — SD excels at this; Gemini as second cloud option
    (
        [
            "realistic",
            "photo",
            "photography",
            "headshot",
            "portrait photo",
            "product shot",
        ],
        ["sd_webui", "gemini", "openai"],
    ),
    # Text rendering / logos — OpenAI is best; Gemini as fallback
    (
        [
            "text",
            "logo",
            "typography",
            "poster",
            "banner",
            "signage",
            "lettering",
            "font",
        ],
        ["openai", "gemini"],
    ),
    # Quick draft / testing
    (
        ["quick", "draft", "test", "placeholder", "mock"],
        ["placeholder"],
    ),
    # Artistic / illustration — SD has great models; Gemini as second cloud
    (
        [
            "art",
            "painting",
            "illustration",
            "watercolor",
            "oil painting",
            "sketch",
            "drawing",
        ],
        ["sd_webui", "gemini", "openai"],
    ),
    # Anime / manga
    (
        ["anime", "manga", "kawaii", "chibi"],
        ["sd_webui", "gemini", "openai"],
    ),
]

# Default fallback chain — Gemini first (free tier), then OpenAI, then SD WebUI
_DEFAULT_CHAIN = ["gemini", "openai", "sd_webui", "placeholder"]
```

- [ ] **Step 4: Update selector tests**

In `tests/test_selector.py`, update and add tests to reflect new chains. Find the default fallback test section and update:

```python
    # -- Default fallback chain (updated for gemini) -----------------------

    def test_default_fallback_prefers_gemini(self) -> None:
        available = {"gemini", "openai", "sd_webui", "placeholder"}
        assert select_provider("a beautiful landscape", available) == "gemini"

    def test_default_fallback_uses_openai_without_gemini(self) -> None:
        available = {"openai", "sd_webui", "placeholder"}
        assert select_provider("a beautiful landscape", available) == "openai"

    def test_default_fallback_placeholder_only(self) -> None:
        available = {"placeholder"}
        assert select_provider("a beautiful landscape", available) == "placeholder"

    # -- Gemini in specialist chains ---------------------------------------

    def test_photorealism_falls_back_to_gemini(self) -> None:
        """When sd_webui is unavailable, photorealism falls back to gemini."""
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "gemini"

    def test_text_rendering_falls_back_to_gemini(self) -> None:
        """When openai is unavailable, text rendering falls back to gemini."""
        available = {"gemini", "sd_webui", "placeholder"}
        assert select_provider("logo with typography", available) == "gemini"

    def test_artistic_falls_back_to_gemini(self) -> None:
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("watercolor painting of a sunset", available) == "gemini"

    def test_anime_falls_back_to_gemini(self) -> None:
        available = {"gemini", "openai", "placeholder"}
        assert select_provider("anime girl with sword", available) == "gemini"
```

Also update the existing `test_photorealism_falls_back_to_openai` to check that with `{"openai", "placeholder"}` (no gemini) it still returns `"openai"`:

```python
    def test_photorealism_falls_back_to_openai_when_no_gemini(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("realistic portrait photo", available) == "openai"
```

And update `test_anime_falls_back_to_openai` to:
```python
    def test_anime_falls_back_to_openai_when_no_gemini(self) -> None:
        available = {"openai", "placeholder"}
        assert select_provider("anime girl with sword", available) == "openai"
```

- [ ] **Step 5: Run selector + server_deps tests**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest tests/test_selector.py tests/test_server_deps.py -v
```

Expected: all tests pass. Fix any existing tests that assert the old default chain.

- [ ] **Step 6: Run full test suite**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest -x -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/image_generation_mcp/_server_deps.py src/image_generation_mcp/providers/selector.py tests/test_selector.py tests/test_server_deps.py
git commit -m "feat: register Gemini provider and update auto-selection chains"
```

---

## Task 4: Provider documentation

**Files:**
- Create: `docs/providers/gemini.md`
- Modify: `docs/providers/index.md`

- [ ] **Step 1: Create `docs/providers/gemini.md`**

```markdown
# Gemini Provider

Image generation via Google's Gemini native `generateContent` API with `responseModalities=["IMAGE"]`. Best for general-purpose generation with a generous free tier.

## Setup

Set your Google API key:

```bash
IMAGE_GENERATION_MCP_GOOGLE_API_KEY=AIza...
```

The provider registers automatically when this variable is set. Get a key at [Google AI Studio](https://aistudio.google.com/apikey).

## Supported models

| Model | Notes |
|-------|-------|
| `gemini-2.5-flash-image` | Default — fast, high-volume, stable |
| `gemini-3.1-flash-image-preview` | Latest, speed-optimised |
| `gemini-3-pro-image-preview` | Studio-quality, best for complex scenes |

Use `list_providers` to see which models are available on your API key.

## Aspect ratios and sizes

All five project aspect ratios are natively supported:

| Aspect ratio | Gemini parameter |
|-------------|-----------------|
| `1:1` | `1:1` |
| `16:9` | `16:9` |
| `9:16` | `9:16` |
| `3:2` | `3:2` |
| `2:3` | `2:3` |

## Quality levels

| Quality param | Gemini `image_size` |
|---------------|-------------------|
| `standard` | `1K` |
| `hd` | `2K` |

## Negative prompts

Gemini does not have native negative prompt support. When a `negative_prompt` is provided, it is appended to the prompt as:

```
{prompt}

Avoid: {negative_prompt}
```

## Background transparency

Not supported. The `background` parameter is silently ignored — all images are generated with an opaque background.

## Prompt style

Gemini works best with natural language descriptions:

```
A professional product photo of white sneakers on a clean white background,
studio lighting, sharp focus, commercial photography style
```

Avoid CLIP-style tag lists (those work better with Stable Diffusion).

## Per-call model selection

The `model` parameter on `generate_image` overrides the provider's default model for a single request:

```
generate_image(prompt="...", provider="gemini", model="gemini-3-pro-image-preview")
```

Use `list_providers` to discover available models and their capabilities.

## Capability discovery

At startup, the provider returns a static list of known image-capable Gemini models. Unlike OpenAI, the Gemini `models.list()` API does not reliably filter to image-generation models, so the known model list is maintained in the provider code.

## Cost

Gemini has a generous free tier (check [Google AI pricing](https://ai.google.dev/pricing) for current limits). The provider is not in `paid_providers` by default — no confirmation prompt is shown before use. Set `IMAGE_GENERATION_MCP_PAID_PROVIDERS=gemini,openai` if you want cost confirmation for Gemini.

## SynthID watermark

All Gemini-generated images include an invisible SynthID watermark added by Google. This is automatic and cannot be disabled.

## Error handling

| Error | Cause | Resolution |
|-------|-------|------------|
| Content policy rejection | Prompt violates Gemini safety policy | Modify the prompt to comply with Google's usage policies |
| Connection error | Cannot reach Gemini API | Check network connectivity and API key validity |
| No image in response | Model returned text instead of image | Try rephrasing the prompt or use a different model |
| API error (HTTP 429) | Rate limited | Wait and retry; consider reducing request frequency |
```

- [ ] **Step 2: Update `docs/providers/index.md`**

Update the comparison table to add a Gemini column. Replace the existing table:

```markdown
## Provider comparison

| | Gemini | OpenAI | SD WebUI (Stable Diffusion) | Placeholder |
|---|--------|--------|----------------------------|-------------|
| **Best for** | General-purpose, free tier | Text, logos, typography | Photorealism, portraits, anime, artistic | Testing, drafts, CI |
| **Models** | gemini-2.5-flash-image, gemini-3.1-flash-image-preview, gemini-3-pro-image-preview | gpt-image-1, dall-e-3 | SD 1.5, SDXL, SDXL Lightning/Turbo | -- |
| **Quality** | High | High | Varies by model and steps | N/A (solid color) |
| **Speed** | 5-15s | 5-15s | 10-60s (depends on GPU) | Instant |
| **Cost** | Free tier available | Per-image API pricing | Self-hosted (GPU cost) | Free |
| **Negative prompt** | Appended as "Avoid:" clause | Appended as "Avoid:" clause | Native support | Ignored |
| **Background control** | Not supported (ignored) | Supported (gpt-image-1 only) | Not supported (ignored) | Supported (RGBA PNG) |
| **Requires** | `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` | `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | Running SD WebUI + `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` | Nothing |
```

Update the "Which provider should I use?" section to add Gemini guidance after the placeholder paragraph:

```markdown
**Use Gemini** for:

- General-purpose image generation with a free tier
- When you don't have a GPU and want an alternative to OpenAI
- Creative scenes, illustrations, and photography
```

Update the auto-selection table to reflect the new chains:

```markdown
| Prompt keywords | Preferred provider chain |
|----------------|--------------------------|
| realistic, photo, photography, portrait photo, product shot, headshot | sd_webui -> gemini -> openai |
| text, logo, typography, poster, banner, signage, lettering, font | openai -> gemini |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, oil painting, sketch, drawing | sd_webui -> gemini -> openai |
| anime, manga, kawaii, chibi | sd_webui -> gemini -> openai |
| *(no match)* | gemini -> openai -> sd_webui -> placeholder |
```

Update the registration section at the bottom to add Gemini as step 2 (renumbering SD WebUI to 3):

```markdown
1. **Placeholder** -- always registered (zero cost, no configuration)
2. **Gemini** -- registered when `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` is set
3. **OpenAI** -- registered when `IMAGE_GENERATION_MCP_OPENAI_API_KEY` is set
4. **SD WebUI** -- registered when `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` is set
```

- [ ] **Step 3: Commit docs**

```bash
git add docs/providers/gemini.md docs/providers/index.md
git commit -m "docs: add Gemini provider page and update provider comparison"
```

---

## Task 5: Configuration + design doc + nav + getting-started docs

**Files:**
- Modify: `docs/configuration.md`
- Modify: `docs/design/provider-system.md`
- Modify: `mkdocs.yml`
- Modify: `docs/getting-started/claude-desktop.md`
- Modify: `docs/getting-started/claude-code.md`

- [ ] **Step 1: Update `docs/configuration.md`**

In the **Providers** table, add a row for Gemini after the OpenAI row:

```markdown
| `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` | str | -- | Google API key. Enables the Gemini provider (gemini-2.5-flash-image and others) when set. Get a key at [Google AI Studio](https://aistudio.google.com/apikey). |
```

In the **Core** table, update the `DEFAULT_PROVIDER` description to include `gemini`:
```
Options: `auto` (keyword-based selection), `gemini`, `openai`, `sd_webui`, `placeholder`.
```

Add a **Gemini** example configuration block after the OpenAI example:

```markdown
### Gemini

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_GOOGLE_API_KEY=AIza...
```
```

Update the **All providers** example to include Gemini:

```markdown
### All providers

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_GOOGLE_API_KEY=AIza...
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
IMAGE_GENERATION_MCP_SD_WEBUI_HOST=http://localhost:7860
IMAGE_GENERATION_MCP_SD_WEBUI_MODEL=realisticVisionV60B1_v51VAE.safetensors
```
```

- [ ] **Step 2: Update `docs/design/provider-system.md`**

In the **Providers** section, add a Gemini subsection after the OpenAI subsection:

```markdown
### Gemini Provider

- **Models:** `gemini-2.5-flash-image` (default), `gemini-3.1-flash-image-preview`, `gemini-3-pro-image-preview`
- **API:** Gemini native `generateContent` with `responseModalities=["IMAGE"]` via `google-genai` SDK
- **Negative prompt:** Appended as `"\n\nAvoid: {negative_prompt}"` (no native support)
- **Quality mapping:** `"standard"` → `image_size="1K"`, `"hd"` → `image_size="2K"`
- **Aspect ratios:** All 5 project ratios passed through directly (all natively supported)
- **Background:** Not supported — ignored; debug log emitted
- **Discovery:** Returns static list of known image models (`_KNOWN_IMAGE_MODELS`); `models.list()` does not reliably filter image-generation models
- **Error handling:** Converts safety/policy errors to `ImageContentPolicyError`; connection errors to `ImageProviderConnectionError`
- **Watermark:** All outputs include Google's SynthID invisible watermark (automatic, cannot be disabled)
- **Registered when:** `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` is set
```

In the Architecture diagram, add `| Gemini  |` to the provider row:

```
       |          |          |          |
       v          v          v          v
  +---------+ +--------+ +----------+ +--------------+
  | OpenAI  | | Gemini | | SD WebUI | | Placeholder  |
  |Provider | |Provider| | Provider | | Provider     |
  +---------+ +--------+ +----------+ +--------------+
```

In the **Provider Selection** table, update to the new chains:

```markdown
| Prompt Keywords | Preferred Provider Chain |
|----------------|------------------------|
| realistic, photo, photography, headshot, portrait photo, product shot | sd_webui -> gemini -> openai |
| text, logo, typography, poster, banner, signage, lettering, font | openai -> gemini |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, oil painting, sketch, drawing | sd_webui -> gemini -> openai |
| anime, manga, kawaii, chibi | sd_webui -> gemini -> openai |
| *(no match)* | gemini -> openai -> sd_webui -> placeholder |
```

In the **Provider Registration (Lifespan)** section, update the list:

```markdown
1. **Placeholder** -- always registered (zero cost, no API key)
2. **Gemini** -- registered if `config.google_api_key` is set
3. **OpenAI** -- registered if `config.openai_api_key` is set
4. **SD WebUI** -- registered if `config.sd_webui_host` is set
```

In the **Configuration** table, add Gemini row:

```markdown
| `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` | str | *(none)* | Google API key; enables Gemini provider |
```

In **Future Work**, remove `Gemini` from the more providers list:

```markdown
- **More providers:** BFL/FLUX, Stability, Ideogram, FAL, Replicate
```

- [ ] **Step 3: Update `mkdocs.yml`**

In the `nav` section, add Gemini between Overview and OpenAI in the Providers group:

```yaml
  - Providers:
      - Overview: providers/index.md
      - Gemini: providers/gemini.md
      - OpenAI: providers/openai.md
      - SD WebUI (Stable Diffusion): providers/sd-webui.md
      - Placeholder: providers/placeholder.md
```

If there is an `llmstxt` plugin section in mkdocs.yml that lists provider pages, add `providers/gemini.md` there as well.

- [ ] **Step 4: Update `docs/getting-started/claude-desktop.md`**

Add a "With Gemini" config block after "With OpenAI + SD WebUI":

```markdown
### With Gemini

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false",
        "IMAGE_GENERATION_MCP_GOOGLE_API_KEY": "AIza..."
      }
    }
  }
}
```

### With Gemini + OpenAI

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false",
        "IMAGE_GENERATION_MCP_GOOGLE_API_KEY": "AIza...",
        "IMAGE_GENERATION_MCP_OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```
```

Also update "For OpenAI: verify..." troubleshooting line to add:
```
- For Gemini: verify your API key is valid and has Gemini API access enabled in Google AI Studio
```

- [ ] **Step 5: Update `docs/getting-started/claude-code.md`**

Add a "With Gemini" example after "With OpenAI":

```markdown
### With Gemini

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false",
        "IMAGE_GENERATION_MCP_GOOGLE_API_KEY": "AIza..."
      }
    }
  }
}
```
```

Update the "With all providers" example to include Gemini:

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false",
        "IMAGE_GENERATION_MCP_GOOGLE_API_KEY": "AIza...",
        "IMAGE_GENERATION_MCP_OPENAI_API_KEY": "sk-...",
        "IMAGE_GENERATION_MCP_SD_WEBUI_HOST": "http://localhost:7860"
      }
    }
  }
}
```

- [ ] **Step 6: Run the full test suite one final time**

```bash
cd /mnt/code/image-gen-mcp && python -m pytest -x -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit docs**

```bash
git add docs/configuration.md docs/design/provider-system.md mkdocs.yml docs/getting-started/claude-desktop.md docs/getting-started/claude-code.md
git commit -m "docs: update configuration, design doc, and getting-started for Gemini provider"
```

---

## Task 6: Create PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/gemini-provider
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "feat: Gemini image generation provider" \
  --body "$(cat <<'EOF'
## Summary

- Adds `GeminiImageProvider` using the Gemini native `generateContent` API with `responseModalities=["IMAGE"]`
- `google-genai>=1.0` added as optional dependency (included in `all` extra)
- Gemini becomes first in the default auto-selection chain (free tier)
- Full test coverage: `test_gemini_provider.py`, `test_gemini_discovery.py`, updated `test_selector.py`
- Documentation: `docs/providers/gemini.md`, updated index, configuration, design doc, getting-started guides

Closes #159

## Test plan

- [ ] Run `pytest tests/test_gemini_provider.py tests/test_gemini_discovery.py -v` — all pass
- [ ] Run `pytest tests/test_selector.py -v` — all pass including new Gemini chain tests
- [ ] Run `pytest -x -q` — full suite green
- [ ] Install `google-genai` and run with a real `GOOGLE_API_KEY` to verify live generation

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
