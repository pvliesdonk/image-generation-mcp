# MCP Tools

image-generation-mcp exposes four domain tools plus two auto-generated resource-bridge tools to MCP clients.

## generate_image

Generate an image from a text prompt. Returns metadata with resource URIs and a `ResourceLink` to the image. Call `show_image` with the image URI to display it. Read `info://prompt-guide` for provider-specific prompt writing tips.

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
| `model` | str | `null` | Specific model to use (e.g., an A1111 checkpoint name or `"dall-e-3"` for OpenAI). Overrides the provider's default. Use `list_providers` to see available model IDs. |

### Return value

Returns a `ToolResult` with:

1. **TextContent** -- JSON metadata:
2. **ResourceLink** -- URI reference to `image://{id}/view` for the generated image

```json
{
  "image_id": "a1b2c3d4e5f6",
  "prompt": "watercolor painting of a mountain landscape at sunset",
  "original_uri": "image://a1b2c3d4e5f6/view",
  "metadata_uri": "image://a1b2c3d4e5f6/metadata",
  "resource_template": "image://a1b2c3d4e5f6/view{?format,width,height,quality}",
  "dimensions": [1024, 1024],
  "original_size_bytes": 1048576,
  "provider": "openai",
  "model": "gpt-image-1",
  "size": "1024x1024"
}
```

Call `show_image` with the `original_uri` (or the `resource_template` with transform params) to display the image.

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

## show_image

Display a registered image with optional on-demand transforms. Accepts a full `image://` resource URI with transforms encoded in the query string.

| Property | Value |
|----------|-------|
| **Tags** | *(none)* -- always visible (read-only operation) |
| **Task** | No |
| **MCP App** | `ui://image-viewer/view.html` (interactive viewer in supported clients) |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `uri` | str | *(required)* | Full `image://` resource URI (e.g., `image://a1b2c3/view?format=webp&width=512`) |

Transforms are encoded in the URI query string using the same parameters as the `image://{id}/view` resource template: `format`, `width`, `height`, `quality`.

### Return value

Returns a `ToolResult` with:

1. **ImageContent** -- a WebP thumbnail preview (max 512px, always under 1 MB) for inline display in MCP clients. This is always WebP regardless of the requested format.
2. **TextContent** -- JSON metadata with the full-resolution details:

```json
{
  "image_id": "a1b2c3d4e5f6",
  "prompt": "watercolor painting of a mountain landscape at sunset",
  "provider": "openai",
  "dimensions": [1024, 683],
  "thumbnail_dimensions": [512, 342],
  "original_size_bytes": 3145728,
  "format": "image/png",
  "transforms_applied": {}
}
```

The `dimensions` field reports the actual image size (or the transformed size if transforms were requested). The `thumbnail_dimensions` field reports the size of the inline preview, which is capped at 512px. When `dimensions` and `thumbnail_dimensions` differ, the inline preview is a downscaled version — use the `image://` resource URI or `create_download_link` for full resolution.

### Examples

```
# Show the original image
show_image(uri="image://a1b2c3d4e5f6/view")

# Show resized to 512px wide as WebP
show_image(uri="image://a1b2c3d4e5f6/view?format=webp&width=512")

# Show center-cropped to 256x256
show_image(uri="image://a1b2c3d4e5f6/view?width=256&height=256")
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

---

## list_resources / read_resource (auto-generated)

These tools are automatically generated by the [ResourcesAsTools](https://gofastmcp.com/servers/transforms/resources-as-tools) transform. They bridge the gap for MCP clients that only support tools (e.g. Claude webchat) and cannot access resources directly.

| Tool | Description |
|------|-------------|
| `list_resources` | Returns JSON describing all available resources and templates |
| `read_resource` | Reads a specific resource by URI |

### Usage

```
Tool call: list_resources
  → returns JSON array of all image:// and info:// resources

Tool call: read_resource
  uri: "image://a1b2c3d4e5f6/view"
  → returns the full-resolution image

Tool call: read_resource
  uri: "image://a1b2c3d4e5f6/metadata"
  → returns generation metadata JSON

Tool call: read_resource
  uri: "image://list"
  → returns JSON array of all generated images
```

These tools provide access to the same resources documented in [Resources](resources.md), including on-the-fly image transforms via URI template parameters.

---

## create_download_link

Create a one-time-use HTTP download URL for an image. Enables server-to-server image transfer between MCP servers (e.g., saving an image to a vault, attaching to email).

| Property | Value |
|----------|-------|
| **Tags** | *(none)* |
| **Task** | No |
| **Transport** | HTTP/SSE only (hidden on stdio — no HTTP server available) |
| **Requires** | `IMAGE_GENERATION_MCP_BASE_URL` |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `uri` | str | *(required)* | Full `image://` resource URI (e.g., `image://a1b2c3/view?format=webp&width=512`) |
| `ttl_seconds` | int | `300` | Link lifetime in seconds (default 5 minutes) |

### Return value

```json
{
  "download_url": "https://mcp.example.com/artifacts/7f3a...e9b1",
  "expires_in_seconds": 300,
  "uri": "image://a1b2c3d4e5f6/view?format=webp&width=512"
}
```

The download URL:
- Serves the image once with correct `Content-Type`, then **invalidates the link**
- Returns HTTP 404 after first download or after TTL expires
- Does not require bearer token or OIDC auth (the random token is the auth)
- The artifact endpoint bypasses MCP authentication

### Example workflow

```
User: Generate a photo and save it to my vault

1. generate_image(prompt="sunset photo") → image_id: "a1b2c3..."
2. create_download_link(uri="image://a1b2c3/view?format=jpeg")
   → download_url: "https://mcp.example.com/artifacts/7f3a..."
3. vault-mcp: save_artifact_from_url(url="https://...", path="photos/sunset.jpg")
```

---

## MCP Apps: Image Viewer

Clients that support [MCP Apps](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/apps) (Claude Desktop, claude.ai) render an interactive image viewer alongside `show_image` results.

The viewer is a custom HTML resource at `ui://image-viewer/view.html` that:

- Listens for `show_image` tool results via the `@modelcontextprotocol/ext-apps` SDK
- Displays the image with metadata (prompt, provider, dimensions, file size)
- Supports light and dark color schemes

No configuration is needed — the viewer activates automatically on MCP Apps-capable clients. Clients without Apps support see the standard base64 image + metadata response.
