# MCP Resources

image-generation-mcp exposes resources for provider information and image access.

## info://providers

Provider capabilities and supported features.

**MIME type:** `application/json`

### Response

```json
{
  "providers": {
    "placeholder": {
      "available": true,
      "description": "Zero-cost solid-color PNG — instant, no API key, for testing and drafts",
      "capabilities": {
        "provider_name": "placeholder",
        "models": [
          {
            "model_id": "placeholder",
            "display_name": "Placeholder (solid-color PNG)",
            "can_generate": true,
            "can_edit": false,
            "supports_mask": false,
            "supported_aspect_ratios": ["1:1", "16:9", "9:16", "3:2", "2:3"],
            "supported_qualities": ["standard"],
            "supported_formats": ["png"],
            "supports_negative_prompt": false,
            "supports_background": true,
            "max_resolution": 640,
            "default_steps": null,
            "default_cfg": null,
            "prompt_style": null
          }
        ],
        "supports_background": true,
        "supports_negative_prompt": false,
        "discovered_at": 1710777600.0,
        "degraded": false
      }
    },
    "openai": {
      "available": true,
      "description": "OpenAI (gpt-image-1 / dall-e-3) — best for text, logos, and general-purpose generation",
      "capabilities": {
        "provider_name": "openai",
        "models": [
          {
            "model_id": "gpt-image-1",
            "display_name": "GPT Image 1",
            "can_generate": true,
            "can_edit": true,
            "supports_mask": true,
            "supported_aspect_ratios": ["1:1", "16:9", "9:16", "3:2", "2:3"],
            "supported_qualities": ["standard", "hd"],
            "supported_formats": ["png", "jpeg", "webp"],
            "supports_negative_prompt": false,
            "supports_background": true,
            "max_resolution": 1536,
            "default_steps": null,
            "default_cfg": null,
            "prompt_style": null
          }
        ],
        "supports_background": true,
        "supports_negative_prompt": false,
        "discovered_at": 1710777600.0,
        "degraded": false
      }
    }
  },
  "supported_aspect_ratios": ["1:1", "16:9", "9:16", "3:2", "2:3"],
  "supported_quality_levels": ["standard", "hd"],
  "supported_backgrounds": ["opaque", "transparent"]
}
```

Only registered (configured) providers appear. Degraded providers (where capability discovery failed at startup) show `"degraded": true` with an empty `models` list -- they remain available for generation.

---

## info://prompt-guide

Provider-specific prompt writing guidance for LLM clients. Read this resource to learn how to write effective prompts for each provider.

**MIME type:** `text/markdown`

### Content

Markdown document covering:

- **General tips** — aspect ratio selection, quality levels, when to use negative prompts
- **OpenAI** — natural-language prompts, style keywords, text rendering tips
- **SD WebUI (Stable Diffusion)** — CLIP tags for SD 1.5/SDXL, natural language for Flux, negative prompts, BREAK syntax, model-specific advice
- **Placeholder** — prompt-to-color mapping explanation

The `generate_image` tool description references this resource. LLM clients can read it before generating images to produce better prompts.

---

## image://{id}/view

Image data with optional CDN-style transforms. This is a resource template (RFC 6570) with query parameters.

**URI template:** `image://{image_id}/view{?format,width,height,quality}`

**MIME type:** varies (depends on original format or requested format)

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | str | *(original)* | Convert to `png`, `webp`, or `jpeg` |
| `width` | int | *(original)* | Target width in pixels |
| `height` | int | *(original)* | Target height in pixels |
| `quality` | int | `90` | Compression quality for lossy formats (1-100) |

### Transform behavior

| Parameters provided | Behavior |
|--------------------|----------|
| None | Returns original bytes unchanged |
| `format` only | Format conversion (e.g. PNG to WebP) |
| `width` + `height` | Center-crop to exact dimensions |
| `width` only | Proportional resize (height calculated from aspect ratio) |
| `height` only | Proportional resize (width calculated from aspect ratio) |
| `format` + dimensions | Convert and resize/crop |

### Examples

```
# Original image
image://a1b2c3d4e5f6/view

# Convert to WebP
image://a1b2c3d4e5f6/view?format=webp

# Resize to 512px wide (proportional)
image://a1b2c3d4e5f6/view?width=512

# Center-crop to 256x256
image://a1b2c3d4e5f6/view?width=256&height=256

# Convert to JPEG at quality 85
image://a1b2c3d4e5f6/view?format=jpeg&quality=85
```

---

## image://{id}/metadata

Sidecar JSON metadata with generation provenance.

**MIME type:** `application/json`

### Response

```json
{
  "id": "a1b2c3d4e5f6",
  "content_type": "image/png",
  "provider": "openai",
  "prompt": "a watercolor painting of mountains at sunset",
  "negative_prompt": null,
  "aspect_ratio": "16:9",
  "quality": "standard",
  "original_dimensions": [1536, 1024],
  "provider_metadata": {
    "model": "gpt-image-1",
    "size": "1536x1024",
    "quality": "standard",
    "api_quality": "high"
  },
  "created_at": 1710777600.0
}
```

---

## image://list

List all registered images and pending generations.

**MIME type:** `application/json`

### Response

Each item includes a `status` field: `"completed"` for registered images, `"generating"` or `"failed"` for pending background generations.

```json
[
  {
    "image_id": "a1b2c3d4e5f6",
    "provider": "openai",
    "prompt": "a watercolor painting of mountains at sunset",
    "aspect_ratio": "16:9",
    "created_at": 1710777600.0,
    "status": "completed"
  },
  {
    "image_id": "c3d4e5f6a7b8",
    "provider": "sd_webui",
    "prompt": "a cyberpunk cityscape",
    "status": "generating",
    "progress": 0.3,
    "progress_message": "Step 9/30 (ETA 12s)"
  },
  {
    "image_id": "b2c3d4e5f6a7",
    "provider": "placeholder",
    "prompt": "test image",
    "aspect_ratio": "1:1",
    "created_at": 1710777500.0,
    "status": "completed"
  }
]
```

Pending generations (status `"generating"` or `"failed"`) appear in the list alongside completed images. They are cleaned up automatically after a 10-minute TTL.

---

## ui://image-viewer/view.html

Interactive image viewer rendered by MCP Apps-capable clients (Claude Desktop, claude.ai).

**MIME type:** `text/html;profile=mcp-app`

This resource is an [MCP App](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/apps) — a custom HTML page loaded in a sandboxed iframe via the `@modelcontextprotocol/ext-apps` SDK. It is wired to the `show_image` tool via `AppConfig(resourceUri=...)`.

### Sandbox domain

When `IMAGE_GENERATION_MCP_BASE_URL` is set, the Claude sandbox domain is auto-computed as `sha256(BASE_URL + HTTP_PATH)[:32].claudemcpcontent.com`. Override with `IMAGE_GENERATION_MCP_APP_DOMAIN` for other hosts or custom setups. When neither is set (stdio transport), the host assigns its own sandbox origin.

### Viewer states

| State | Trigger | Display |
|-------|---------|---------|
| Waiting | Widget loaded, no tool result yet | "Waiting for image..." |
| Generating | `show_image` returns `{"status": "generating", ...}` | Spinner, progress bar, provider info |
| Failed | `show_image` returns `{"status": "failed", ...}` | Error message |
| Completed | `show_image` returns image + metadata | Image, prompt, provider, dimensions, file size |
| Cancelled | Host cancels the tool call | "Cancelled" message |

### Features

- **Host theming** — applies `applyDocumentTheme()`, `applyHostStyleVariables()`, and `applyHostFonts()` from the ext-apps SDK; CSS uses host variables (`--color-text-primary`, `--font-sans`, etc.)
- **Safe area insets** — respects `safeAreaInsets` from `onhostcontextchanged` for mobile notch/status bar
- **localStorage cache** — persists rendered images (keyed by image ID, LRU-capped at 5 entries); restores cached state on `ontoolinput` before the tool result arrives
- **Download button** — uses the ext-apps `downloadFile` API with a `resource_link` to `image://{id}/view` for the full-resolution image; falls back to `openLink` with the artifact `download_url` when the host does not support `downloadFile`

Clients without MCP Apps support ignore this resource entirely.
