# Provider System Design

## Overview

The image generation MCP server uses a multi-provider architecture where each
provider implements a common protocol and is registered at startup based on
available configuration (API keys, service URLs). A central `ImageService`
orchestrates provider selection, image generation, and scratch storage.

## Architecture

```
MCP Client (Claude)
    │
    ▼
┌─────────────────────────────────────────────┐
│  MCP Layer                                  │
│  _server_tools.py    generate_image         │
│                      list_providers         │
│  _server_prompts.py  select_provider        │
│                      sd_prompt_guide        │
│  _server_resources.py info://providers      │
└─────────────────┬───────────────────────────┘
                  │ Depends(get_service)
                  ▼
┌─────────────────────────────────────────────┐
│  ImageService (service.py)                  │
│  - Provider registry (name → instance)      │
│  - generate() → dispatches to provider      │
│  - save_to_scratch() → persists images      │
│  - list_providers() → availability info     │
│  - _resolve_provider() → auto or explicit   │
└──────┬──────────┬──────────┬────────────────┘
       │          │          │
       ▼          ▼          ▼
  ┌─────────┐ ┌────────┐ ┌──────────────┐
  │ OpenAI  │ │ A1111  │ │ Placeholder  │
  │Provider │ │Provider│ │ Provider     │
  └─────────┘ └────────┘ └──────────────┘
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
- `size_bytes` property — length of `image_data`
- `from_base64()` classmethod — construct from base64-encoded string + keyword metadata

### Exception Hierarchy

```
ImageProviderError(Exception)
├── ImageContentPolicyError    # Content policy violation (OpenAI)
└── ImageProviderConnectionError  # Network/timeout errors
```

All exceptions carry `provider: str` and `message: str` for clear error reporting.

## Providers

### Placeholder Provider

- **Purpose:** Zero-cost solid-color PNG generation for testing and drafts
- **No dependencies:** Pure Python PNG encoder (zlib + struct)
- **Color:** Deterministic from MD5 hash of prompt
- **Aspect ratios:** Maps to pixel sizes (480x480, 640x360, etc.)
- **Always registered** — no API key or service needed

### OpenAI Provider

- **Models:** `gpt-image-1` (default), `dall-e-3`
- **API:** OpenAI Images API with `response_format="b64_json"`
- **Negative prompt:** Appended as `"\n\nAvoid: {negative_prompt}"` to the prompt
- **Quality mapping:** `"standard"` → `"medium"`, `"hd"` → `"high"`, `"low"` → `"low"`
- **Size mapping:** Per-model aspect ratio → pixel size tables
- **Error handling:** Converts `APIConnectionError`, `APIStatusError` (with content policy detection)
- **Registered when:** `IMAGE_GEN_MCP_OPENAI_API_KEY` is set

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
- **Registered when:** `IMAGE_GEN_MCP_A1111_HOST` is set

## Provider Selection

When `provider="auto"` (default), the selector (`providers/selector.py`) analyzes
the prompt using keyword matching with word boundaries:

| Prompt Keywords | Preferred Provider Chain |
|----------------|------------------------|
| realistic, photo, portrait, headshot, product shot | a1111 → openai |
| text, logo, typography, poster, banner, sign | openai |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, sketch | a1111 → openai |
| anime, manga, kawaii, chibi | a1111 → openai |
| *(no match)* | openai → a1111 → placeholder |

First matching rule wins. Within a rule, the first available provider is selected.
If no rule matches, the default fallback chain is used. If no provider in the
chain is available, any registered provider is returned as last resort.

## ImageService

The `ImageService` is the central orchestrator, created during server lifespan
and injected via FastMCP's `Depends()` system.

### Responsibilities

1. **Provider registry** — `register_provider(name, provider)` at startup
2. **Generation dispatch** — `generate(prompt, *, provider, ...)` resolves provider and delegates
3. **Scratch storage** — `save_to_scratch(result, provider_name)` writes image to disk
4. **Base64 encoding** — `get_image_base64(result)` for MCP `ImageContent`
5. **Provider listing** — `list_providers()` returns availability info

### Provider Registration (Lifespan)

Registration happens in `_server_deps.py` during server startup:

1. **Placeholder** — always registered (zero cost, no API key)
2. **OpenAI** — registered if `config.openai_api_key` is set
3. **A1111** — registered if `config.a1111_host` is set

### Scratch Directory

Every generated image is saved to `IMAGE_GEN_MCP_SCRATCH_DIR` (default
`~/.image-gen-mcp/images/`) with filename format: `{timestamp}-{provider}-{hash}.{ext}`

## MCP Interface

### Tools

| Tool | Tags | Description |
|------|------|-------------|
| `generate_image` | `write` | Generate image, save to scratch, return `ImageContent` + metadata JSON |
| `list_providers` | *(none)* | List available providers with availability info |

`generate_image` returns a `ToolResult` with:
- `ImageContent` — base64-encoded image data
- `TextContent` — JSON metadata (provider, file_path, size_bytes, plus provider-specific metadata)

In read-only mode (`IMAGE_GEN_MCP_READ_ONLY=true`), `generate_image` is hidden.

### Resources

| URI | Description |
|-----|-------------|
| `info://providers` | JSON of provider capabilities |

### Prompts

| Prompt | Description |
|--------|-------------|
| `select_provider` | Guides Claude on provider strengths and selection criteria |
| `sd_prompt_guide` | Guides Claude on CLIP-based tag format, negative prompts, BREAK syntax |

## Configuration

All environment variables use the `IMAGE_GEN_MCP_` prefix.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GEN_MCP_SCRATCH_DIR` | Path | `~/.image-gen-mcp/images/` | Scratch directory for saved images |
| `IMAGE_GEN_MCP_OPENAI_API_KEY` | str | *(none)* | OpenAI API key; enables OpenAI provider |
| `IMAGE_GEN_MCP_A1111_HOST` | str | *(none)* | A1111 WebUI URL; enables A1111 provider |
| `IMAGE_GEN_MCP_DEFAULT_PROVIDER` | str | `"auto"` | Default provider (`auto`, `openai`, `a1111`, `placeholder`) |
| `IMAGE_GEN_MCP_READ_ONLY` | bool | `true` | When true, hides write-tagged tools |

## Future Work

- **More providers:** BFL/FLUX, Stability, Ideogram, FAL, Gemini, Replicate
- **ComfyUI provider:** Workflow-based API with CLIP text encode nodes
- **Image editing:** Masks, inpainting, background removal
- **Rate limiting:** Per-provider request throttling
- **Auto-cleanup:** TTL-based scratch directory cleanup
