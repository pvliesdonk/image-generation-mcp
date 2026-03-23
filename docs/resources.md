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

List all registered images.

**MIME type:** `application/json`

### Response

```json
[
  {
    "id": "a1b2c3d4e5f6",
    "provider": "openai",
    "prompt": "a watercolor painting of mountains at sunset",
    "aspect_ratio": "16:9",
    "created_at": 1710777600.0
  },
  {
    "id": "b2c3d4e5f6a7",
    "provider": "placeholder",
    "prompt": "test image",
    "aspect_ratio": "1:1",
    "created_at": 1710777500.0
  }
]
```

---

## ui://image-viewer/view.html

Interactive image viewer rendered by MCP Apps-capable clients (Claude Desktop, claude.ai).

**MIME type:** `text/html`

This resource is an [MCP App](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/apps) — a custom HTML page loaded in a sandboxed iframe. It listens for `show_image` tool results and displays the image with metadata. The `show_image` tool is wired to this resource via `AppConfig(resourceUri=...)`.

The viewer persists rendered images in `localStorage` (keyed by image ID, LRU-capped at 5 entries). When a new widget instance loads, the `ontoolinput` handler restores cached state immediately so the image is visible before the tool result arrives. The live `ontoolresult` always takes precedence over the cached version.

Clients without MCP Apps support ignore this resource entirely.
