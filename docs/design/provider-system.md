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
|                      show_image              |
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
        background: str = "opaque",
        model: str | None = None,
    ) -> ImageResult: ...

    async def discover_capabilities(self) -> ProviderCapabilities: ...
```

The optional `model` parameter allows per-call model selection. When set, it
overrides the provider's constructor default. A1111 uses it for both preset
detection and `override_settings.sd_model_checkpoint`. OpenAI uses it as the
API `model` parameter with automatic size table switching.

The `discover_capabilities()` method is called once during server lifespan
after provider construction. Results are cached for the server lifetime
(frozen dataclasses). See [ADR-0007](../decisions/0007-provider-capability-model.md)
for the full design.

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

## Capability Discovery

At startup, after all providers are registered, the server calls
`discover_capabilities()` on each provider. Results are stored in
`ImageService._capabilities` as frozen `ProviderCapabilities` dataclasses.

### Per-Provider Strategy

| Provider | Discovery method | Notes |
|----------|-----------------|-------|
| **Placeholder** | Static return | Hardcoded capabilities, always succeeds |
| **OpenAI** | `client.models.list()` | Filters to known image models (gpt-image-1, dall-e-3, dall-e-2) |
| **A1111** | `GET /sdapi/v1/sd-models` + `/sdapi/v1/options` | Maps checkpoints to architecture-specific capabilities |

### Degraded Mode

If `discover_capabilities()` raises an exception, the provider is marked
`degraded=True` with an empty model list. Server startup is **not blocked** --
degraded providers can still generate images, but a warning is logged on each
generation request. This prevents a slow or unreachable A1111 instance from
blocking the entire server.

### Capability-Aware Selection

When `provider="auto"`, the selector uses capabilities as a **secondary filter**
alongside keyword heuristics. For example, when `background="transparent"` is
requested, providers without `supports_background=True` are deprioritized but
not excluded. Keywords remain the primary selection mechanism.

## Providers

### Placeholder Provider

- **Purpose:** Zero-cost solid-color PNG generation for testing and drafts
- **No dependencies:** Pure Python PNG encoder (zlib + struct)
- **Color:** Selected from 6-color palette via SHA-256 hash of prompt
- **Aspect ratios:** Maps to pixel sizes (256x256, 640x360, etc.)
- **Background:** Supports transparent (RGBA PNG with alpha=0)
- **Always registered** -- no API key or service needed

### OpenAI Provider

- **Models:** `gpt-image-1` (default), `dall-e-3`
- **API:** OpenAI Images API with `output_format` (gpt-image-1) or `response_format="b64_json"` (dall-e-3)
- **Negative prompt:** Appended as `"\n\nAvoid: {negative_prompt}"` to the prompt
- **Quality mapping:** gpt-image-1: `"standard"` -> `"high"`, `"hd"` -> `"high"`; dall-e-3: passed through unchanged
- **Size mapping:** Per-model aspect ratio -> pixel size tables
- **Background:** `gpt-image-1` supports `background` parameter natively; ignored for `dall-e-3`
- **Discovery:** Calls `client.models.list()`, filters to known image models, maps to `ModelCapabilities`
- **Error handling:** Converts `APIConnectionError`, `APIStatusError` (with content policy detection)
- **Registered when:** `IMAGE_GENERATION_MCP_OPENAI_API_KEY` is set

### A1111 Provider (Stable Diffusion WebUI)

- **API:** HTTP POST to `/sdapi/v1/txt2img`
- **Model-aware presets:** Auto-detects SD architecture from checkpoint name:
  - **SD 1.5** (default): 768px base, 30 steps, CFG 7.0, DPM++ 2M sampler, Karras scheduler
  - **SDXL**: 1024px base, 35 steps, CFG 7.5, DPM++ 2M sampler, Karras scheduler
  - **SDXL Lightning/Turbo**: 1024px base, 6 steps, CFG 2.0, DPM++ SDE sampler, Karras scheduler
- **Checkpoint override:** When `model` is specified, sends `override_settings.sd_model_checkpoint`
- **Negative prompt:** Native support via `negative_prompt` field in payload
- **Background:** Ignored (SD does not support native transparent backgrounds); debug log emitted
- **Discovery:** Calls `/sdapi/v1/sd-models` + `/sdapi/v1/options`, maps checkpoints to architecture-specific `ModelCapabilities`
- **Metadata:** Extracts seed and active model name from response `info` JSON
- **Timeout:** 180s (SDXL at high res on consumer GPUs)
- **Registered when:** `IMAGE_GENERATION_MCP_A1111_HOST` is set

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

When capabilities are available and `background="transparent"` is requested,
providers with `supports_background=True` are tried first within each candidate
set. This is a secondary filter -- keyword heuristics still determine the rule,
but capable providers are preferred within that rule.

## ImageService

The `ImageService` is the central orchestrator, created during server lifespan
and injected via FastMCP's `Depends()` system.

### Responsibilities

1. **Provider registry** -- `register_provider(name, provider)` at startup
2. **Capability discovery** -- `discover_all_capabilities()` introspects each provider (graceful degradation)
3. **Generation dispatch** -- `generate(prompt, *, provider, ...)` resolves provider and delegates
4. **Image registry** -- `register_image()` saves original + sidecar JSON, indexes in memory
5. **Image retrieval** -- `get_image(id)` and `list_images()` for registered images
6. **Startup rebuild** -- `_load_registry()` reconstructs in-memory registry from sidecar files
7. **Base64 encoding** -- `get_image_base64(result)` for MCP `ImageContent`
8. **Provider listing** -- `list_providers()` returns availability + capability info

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

After all providers are registered, `discover_all_capabilities()` is called.
This introspects each provider and caches the results for the server lifetime.
Failures are handled gracefully -- the provider is marked degraded but remains
available for generation.

### Scratch Directory

Every generated image is saved to `IMAGE_GENERATION_MCP_SCRATCH_DIR` (default
`~/.image-generation-mcp/images/`) with the `{id}-original.{ext}` naming scheme.

## MCP Interface

### Tools

| Tool | Tags | Task | Description |
|------|------|------|-------------|
| `generate_image` | `write` | `task=True` | Generate image, return metadata + `ResourceLink` |
| `show_image` | *(none)* | -- | Display a registered image with optional transforms |
| `list_providers` | *(none)* | -- | List available providers with availability info |

`generate_image` supports both foreground and background execution via
`task=True` (see [ADR-0005](../decisions/0005-hybrid-background-tasks.md)).
Progress is reported at 3 stages via `Context.report_progress()`.

`generate_image` returns a `ToolResult` with:
- `TextContent` -- JSON metadata with `image_id`, `original_uri`, `resource_template`,
  `original_size_bytes`, `provider`, plus provider-specific metadata
- `ResourceLink` -- URI reference to `image://{id}/view`

`show_image` accepts a full `image://` resource URI (transforms encoded in
query string) and returns:
- `ImageContent` -- the image (original or transformed) as base64
- `TextContent` -- JSON metadata with `image_id`, `prompt`, `provider`,
  `dimensions`, `original_size_bytes`, `format`, `transforms_applied`

`show_image` is wired to the MCP Apps image viewer via
`AppConfig(resourceUri="ui://image-viewer/view.html")`.

In read-only mode (`IMAGE_GENERATION_MCP_READ_ONLY=true`), `generate_image` is hidden.

### Resources

| URI | Description |
|-----|-------------|
| `info://providers` | JSON of provider capabilities, models, supported features |
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

All environment variables use the `IMAGE_GENERATION_MCP_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | Path | `~/.image-generation-mcp/images/` | Scratch directory for saved images |
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | str | *(none)* | OpenAI API key; enables OpenAI provider |
| `IMAGE_GENERATION_MCP_A1111_HOST` | str | *(none)* | A1111 WebUI URL; enables A1111 provider |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | str | `"auto"` | Default provider (`auto`, `openai`, `a1111`, `placeholder`) |
| `IMAGE_GENERATION_MCP_READ_ONLY` | bool | `true` | When true, hides write-tagged tools |

## Future Work

- **More providers:** BFL/FLUX, Stability, Ideogram, FAL, Gemini, Replicate
- **ComfyUI provider:** Workflow-based API with CLIP text encode nodes
- **Image editing:** Masks, inpainting, background removal
- **Rate limiting:** Per-provider request throttling
- **Auto-cleanup:** TTL-based scratch directory cleanup
- **Response caching:** Cache frequently-requested transforms
