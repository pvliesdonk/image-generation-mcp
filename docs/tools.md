# MCP Tools

image-gen-mcp exposes two tools to MCP clients.

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
  "file_path": "/home/user/.image-gen-mcp/images/a1b2c3d4e5f6-original.png",
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

JSON object with provider names and availability information:

```json
{
  "placeholder": {
    "available": true,
    "description": "PlaceholderImageProvider (placeholder)"
  },
  "openai": {
    "available": true,
    "description": "OpenAIImageProvider (openai)"
  }
}
```

Only registered (configured) providers appear in the response.

### Example

```
User: Which image providers are available?

Tool call: list_providers
```
