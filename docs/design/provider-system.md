# Provider System Design

## Overview

The image generation MCP server uses a multi-provider architecture where each
provider implements a common protocol and is registered at startup based on
available configuration (API keys, service URLs). A central `ImageService`
orchestrates provider selection, image generation, image registry management,
and scratch storage.

## Architecture

```
MCP Client (Claude)
    |
    v
+---------------------------------------------+
|  MCP Layer                                   |
|  _server_tools.py    generate_image          |
|                      list_providers          |
|  _server_prompts.py  select_provider         |
|                      sd_prompt_guide         |
|  _server_resources.py                        |
|    info://providers                          |
|    image://{id}/view{?format,w,h,quality}    |
|    image://{id}/metadata                     |
|    image://list                              |
+------------------+---+----------------------+
                   |   |
  Depends(service) |   | processing.py
                   v   v
+---------------------------------------------+
|  ImageService (service.py)                   |
|  - Provider registry (name -> instance)      |
|  - Image registry (_images dict + sidecars)  |
|  - generate() -> dispatches to provider      |
|  - register_image() -> saves + indexes       |
|  - get_image() / list_images()               |
|  - _load_registry() -> rebuilds from disk    |
+------+----------+----------+----------------+
       |          |          |
       v          v          v
  +---------+ +--------+ +--------------+
  | OpenAI  | | A1111  | | Placeholder  |
  |Provider | |Provider| | Provider     |
  +---------+ +--------+ +--------------+
```

## ImageProvider Protocol

All providers implement the `ImageProvider` protocol (runtime-checkable):

```python
@runtime_checkable
class ImageProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
    ) -> ImageResult: ...
```

### ImageResult

Frozen dataclass returned by all providers:

| Field | Type | Description |
|-------|------|-------------|
| `image_data` | `bytes` | Raw image bytes (PNG, JPEG, or WebP) |
| `content_type` | `str` | MIME type, default `"image/png"` |
| `provider_metadata` | `dict[str, Any]` | Provider-specific metadata (model, seed, size, etc.) |

Provides:
- `size_bytes` property -- length of `image_data`
- `from_base64()` classmethod -- construct from base64-encoded string + keyword metadata

### Exception Hierarchy

```
ImageProviderError(Exception)
+-- ImageContentPolicyError    # Content policy violation (OpenAI)
+-- ImageProviderConnectionError  # Network/timeout errors
```

All exceptions carry `provider: str` and `message: str` for clear error reporting.

## Providers

### Placeholder Provider

- **Purpose:** Zero-cost solid-color PNG generation for testing and drafts
- **No dependencies:** Pure Python PNG encoder (zlib + struct)
- **Color:** Selected from 6-color palette via SHA-256 hash of prompt
- **Aspect ratios:** Maps to pixel sizes (256x256, 640x360, etc.)
- **Always registered** -- no API key or service needed

### OpenAI Provider

- **Models:** `gpt-image-1` (default), `dall-e-3`
- **API:** OpenAI Images API with `response_format="b64_json"`
- **Negative prompt:** Appended as `"\n\nAvoid: {negative_prompt}"` to the prompt
- **Quality mapping:** `"standard"` -> `"medium"`, `"hd"` -> `"high"`, `"low"` -> `"low"`
- **Size mapping:** Per-model aspect ratio -> pixel size tables
- **Error handling:** Converts `APIConnectionError`, `APIStatusError` (with content policy detection)
- **Registered when:** `MCP_IMAGEGEN_OPENAI_API_KEY` is set

### A1111 Provider (Stable Diffusion WebUI)

- **API:** HTTP POST to `/sdapi/v1/txt2img`
- **Model-aware presets:** Auto-detects SD architecture from checkpoint name:
  - **SD 1.5** (default): 768px base, 30 steps, CFG 7.0, DPM++ 2M Karras
  - **SDXL**: 1024px base, 35 steps, CFG 7.5, DPM++ 2M Karras
  - **SDXL Lightning/Turbo**: 1024px base, 6 steps, CFG 2.0, DPM++ SDE Karras
- **Checkpoint override:** When `model` is specified, sends `override_settings.sd_model_checkpoint`
- **Negative prompt:** Native support via `negative_prompt` field in payload
- **Metadata:** Extracts seed and active model name from response `info` JSON
- **Timeout:** 180s (SDXL at high res on consumer GPUs)
- **Registered when:** `MCP_IMAGEGEN_A1111_HOST` is set

## Provider Selection

When `provider="auto"` (default), the selector (`providers/selector.py`) analyzes
the prompt using keyword matching with word boundaries:

| Prompt Keywords | Preferred Provider Chain |
|----------------|------------------------|
| realistic, photo, photography, headshot, portrait photo, product shot | a1111 -> openai |
| text, logo, typography, poster, banner, signage, lettering, font | openai |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, oil painting, sketch, drawing | a1111 -> openai |
| anime, manga, kawaii, chibi | a1111 -> openai |
| *(no match)* | openai -> a1111 -> placeholder |

First matching rule wins. Within a rule, the first available provider is selected.
If no rule matches, the default fallback chain is used. If no provider in the
chain is available, any registered provider is returned as last resort.

## ImageService

The `ImageService` is the central orchestrator, created during server lifespan
and injected via FastMCP's `Depends()` system.

### Responsibilities

1. **Provider registry** -- `register_provider(name, provider)` at startup
2. **Generation dispatch** -- `generate(prompt, *, provider, ...)` resolves provider and delegates
3. **Image registry** -- `register_image()` saves original + sidecar JSON, indexes in memory
4. **Image retrieval** -- `get_image(id)` and `list_images()` for registered images
5. **Startup rebuild** -- `_load_registry()` reconstructs in-memory registry from sidecar files
6. **Base64 encoding** -- `get_image_base64(result)` for MCP `ImageContent`
7. **Provider listing** -- `list_providers()` returns availability info

### Image Asset Model

See [ADR-0006](../decisions/0006-image-asset-model.md) for the full decision.

**Image ID:** Content-addressed via `SHA-256(image_data)[:12]` (48 bits,
collision-safe for local store).

**Scratch layout:** Each image produces two files:
- `{id}-original.{ext}` -- the image bytes as returned by the provider
- `{id}.json` -- sidecar metadata (prompt, provider, dimensions, provider_metadata)

**Registry rebuild:** On startup, `_load_registry()` globs `*.json` in the
scratch directory, parses each sidecar, and populates `_images`. Corrupt JSON
is logged and skipped.

**Resolution is a read-time concern.** Providers generate at native resolution;
exact pixel dimensions are requested via the resource template query params.

### Provider Registration (Lifespan)

Registration happens in `_server_deps.py` during server startup:

1. **Placeholder** -- always registered (zero cost, no API key)
2. **OpenAI** -- registered if `config.openai_api_key` is set
3. **A1111** -- registered if `config.a1111_host` is set

### Scratch Directory

Every generated image is saved to `MCP_IMAGEGEN_SCRATCH_DIR` (default
`~/.mcp-imagegen/images/`) with the `{id}-original.{ext}` naming scheme.

## MCP Interface

### Tools

| Tool | Tags | Task | Description |
|------|------|------|-------------|
| `generate_image` | `write` | `task=True` | Generate image, return thumbnail + resource URIs |
| `list_providers` | *(none)* | -- | List available providers with availability info |

`generate_image` supports both foreground and background execution via
`task=True` (see [ADR-0005](../decisions/0005-hybrid-background-tasks.md)).
Progress is reported at 3 stages via `Context.report_progress()`.

`generate_image` returns a `ToolResult` with:
- `ImageContent` -- thumbnail (~256px WebP, ~10-50KB) for immediate visual feedback
- `TextContent` -- JSON metadata with `image_id`, `original_uri`, `resource_template`,
  `original_size_bytes`, `thumbnail_size_bytes`, `provider`, `file_path`,
  plus provider-specific metadata

In read-only mode (`MCP_IMAGEGEN_READ_ONLY=true`), `generate_image` is hidden.

### Resources

| URI | Description |
|-----|-------------|
| `info://providers` | JSON of provider capabilities |
| `image://{id}/view{?format,width,height,quality}` | Image with optional transforms (CDN-style) |
| `image://{id}/metadata` | Sidecar JSON with generation provenance |
| `image://list` | JSON array of all registered images |

The `image://{id}/view` resource template supports:
- No params -> original bytes unchanged
- `format` -> convert to png/webp/jpeg via `processing.convert_format()`
- `width` + `height` -> center-crop via `processing.crop_to_dimensions()`
- `width` only or `height` only -> proportional resize
- `quality` -> compression quality for lossy formats (default 90)

### Prompts

| Prompt | Description |
|--------|-------------|
| `select_provider` | Guides Claude on provider strengths and selection criteria |
| `sd_prompt_guide` | Guides Claude on CLIP-based tag format, negative prompts, BREAK syntax |

## Configuration

All environment variables use the `MCP_IMAGEGEN_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_IMAGEGEN_SCRATCH_DIR` | Path | `~/.mcp-imagegen/images/` | Scratch directory for saved images |
| `MCP_IMAGEGEN_OPENAI_API_KEY` | str | *(none)* | OpenAI API key; enables OpenAI provider |
| `MCP_IMAGEGEN_A1111_HOST` | str | *(none)* | A1111 WebUI URL; enables A1111 provider |
| `MCP_IMAGEGEN_DEFAULT_PROVIDER` | str | `"auto"` | Default provider (`auto`, `openai`, `a1111`, `placeholder`) |
| `MCP_IMAGEGEN_READ_ONLY` | bool | `true` | When true, hides write-tagged tools |

## Future Work

- **More providers:** BFL/FLUX, Stability, Ideogram, FAL, Gemini, Replicate
- **ComfyUI provider:** Workflow-based API with CLIP text encode nodes
- **Image editing:** Masks, inpainting, background removal
- **Rate limiting:** Per-provider request throttling
- **Auto-cleanup:** TTL-based scratch directory cleanup
- **Response caching:** Cache frequently-requested transforms
