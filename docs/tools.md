# MCP Tools

image-generation-mcp exposes two tools to MCP clients.

## generate_image

Generate an image from a text prompt. Returns a thumbnail preview and resource URIs for full-resolution access and on-demand transforms.

| Property | Value |
|----------|-------|
| **Tags** | `write` (hidden in read-only mode) |
| **Task** | `task=True` (supports foreground and background execution) |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | *(required)* | Text description of the desired image |
| `provider` | str | `"auto"` | Provider name (`openai`, `a1111`, `placeholder`) or `"auto"` for keyword-based selection |
| `negative_prompt` | str | `null` | Things to avoid in the image. Native support on A1111; appended as "Avoid:" on OpenAI. |
| `aspect_ratio` | str | `"1:1"` | Desired ratio: `1:1`, `16:9`, `9:16`, `3:2`, `2:3` |
| `quality` | str | `"standard"` | Quality level: `standard` or `hd` |
| `background` | str | `"opaque"` | Background mode: `opaque` or `transparent`. Supported by OpenAI (gpt-image-1) and Placeholder. A1111 ignores this parameter. |

### Return value

Returns a `ToolResult` with two content items:

1. **ImageContent** -- thumbnail preview (~256px WebP, typically 10-50 KB) for immediate visual feedback in the chat
2. **TextContent** -- JSON metadata:

```json
{
  "image_id": "a1b2c3d4e5f6",
  "original_uri": "image://a1b2c3d4e5f6/view",
  "resource_template": "image://a1b2c3d4e5f6/view{?format,width,height,quality}",
  "original_size_bytes": 1048576,
  "thumbnail_size_bytes": 12345,
  "provider": "openai",
  "file_path": "/home/user/.image-generation-mcp/images/a1b2c3d4e5f6-original.png",
  "model": "gpt-image-1",
  "size": "1024x1024"
}
```

### Progress reporting

The tool reports progress at 3 stages:

| Progress | Stage |
|----------|-------|
| 0/2 | Generating image |
| 1/2 | Saving to scratch |
| 2/2 | Done |

In foreground mode (default), clients receive these as streaming progress notifications. In background mode (`task=True`), clients poll for progress updates.

### Example

```
User: Generate a watercolor painting of a mountain landscape at sunset

Tool call: generate_image
  prompt: "watercolor painting of a mountain landscape at sunset,
           warm colors, dramatic sky"
  aspect_ratio: "16:9"
  quality: "hd"
```

---

## list_providers

List available image generation providers and their status.

| Property | Value |
|----------|-------|
| **Tags** | *(none)* -- always visible |
| **Task** | No |

### Parameters

None.

### Return value

JSON object with provider names, availability, and capability information:

```json
{
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
          "default_cfg": null
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
          "default_cfg": null
        }
      ],
      "supports_background": true,
      "supports_negative_prompt": false,
      "discovered_at": 1710777600.0,
      "degraded": false
    }
  }
}
```

Only registered (configured) providers appear in the response. The `capabilities` key is present after startup discovery completes. Degraded providers (where capability discovery failed) show `"degraded": true` with an empty model list.

### Example

```
User: Which image providers are available?

Tool call: list_providers
```
