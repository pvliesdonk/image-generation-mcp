# MCP Tools

image-generation-mcp exposes four domain tools plus two auto-generated resource-bridge tools to MCP clients.

## generate_image

Generate an image from a text prompt. Waits for completion (up to ~40s) and returns the image inline with a thumbnail preview and metadata. If generation takes longer, returns `status: "generating"` — call `show_image(uri=original_uri)` to retrieve the result later. Check each model's `prompt_style` in `list_providers` to choose CLIP tags vs. natural language prompts.

| Property | Value |
|----------|-------|
| **Tags** | `write` (hidden in read-only mode) |
| **Annotations** | `readOnlyHint: false`, `destructiveHint: false`, `openWorldHint: true` |
| **Task** | `task=True` (retained for forward compatibility) |
| **Pattern** | Inline wait (up to 40s) with background fallback |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | *(required)* | Text description of the desired image |
| `provider` | str | `"auto"` | Provider name (`openai`, `sd_webui`, `placeholder`) or `"auto"` for keyword-based selection |
| `negative_prompt` | str | `null` | Things to avoid in the image. Native support on SD WebUI (SD 1.5/SDXL only — Flux models do NOT support negative prompts); appended as "Avoid:" on OpenAI. |
| `aspect_ratio` | str | `"1:1"` | Desired ratio: `1:1`, `16:9`, `9:16`, `3:2`, `2:3` |
| `quality` | str | `"standard"` | Quality level: `standard` or `hd` |
| `background` | str | `"opaque"` | Background mode: `opaque` or `transparent`. Supported by OpenAI (gpt-image-1) and Placeholder. SD WebUI ignores this parameter. |
| `model` | str | `null` | Specific model to use (e.g., an SD WebUI checkpoint name or `"dall-e-3"` for OpenAI). Overrides the provider's default. Use `list_providers` to see available model IDs. |

### Return value

Returns a `ToolResult` containing:

**When completed inline (most cases):**

1. **ImageContent** -- WebP thumbnail (max 512px, <1MB)
2. **TextContent** -- JSON metadata with `status: "completed"`
3. **ResourceLink** -- URI reference to `image://{id}/view`

```json
{
  "status": "completed",
  "image_id": "a1b2c3d4e5f6",
  "prompt": "watercolor painting of a mountain landscape at sunset",
  "provider": "openai",
  "model": "gpt-image-1",
  "dimensions": [1024, 1024],
  "original_uri": "image://a1b2c3d4e5f6/view",
  "metadata_uri": "image://a1b2c3d4e5f6/metadata",
  "resource_template": "image://a1b2c3d4e5f6/view{?format,width,height,quality,crop_x,crop_y,crop_w,crop_h,rotate,flip}"
}
```

**When generation exceeds 40s (rare):**

1. **TextContent** -- JSON metadata with `status: "generating"`
2. **ResourceLink** -- URI reference to `image://{id}/view` (image pending)

Call `show_image` with the `original_uri` to retrieve the result once ready.

### Inline wait with background fallback

The tool waits up to 40 seconds for the image to be generated. Most providers complete well within this window:

- **Placeholder**: instant
- **OpenAI**: 5-15s
- **SD WebUI (standard)**: 10-30s

If generation completes within the timeout, the result is returned directly — **one tool call, one result, no polling**. This avoids the disruptive pattern of multiple visible tool-call cards in the conversation UI.

For very slow generations (>40s, e.g., HD SD WebUI with complex prompts), the tool falls back to returning `status: "generating"`. The background task continues running and the client can poll via `show_image`.

The `image://list` resource also includes pending generations with their status.

### Cost confirmation (elicitation)

When all of these conditions are met, `generate_image` asks the user to confirm before calling the provider:

1. The resolved provider is in `IMAGE_GENERATION_MCP_PAID_PROVIDERS` (default: `"openai"`)
2. The MCP client supports [elicitation](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/elicitation) (advertised via `ClientCapabilities.elicitation`)

If the user declines or cancels, the tool returns a cancellation message without making the API call. If the client does not support elicitation, generation proceeds without confirmation (current behavior preserved).

!!! note "Elicitation client support"
    Elicitation was added in the MCP spec 2025-06-18 revision. As of this writing, few clients support it. The confirmation is a progressive enhancement — it activates automatically on capable clients and is invisible on others.

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

Normally `generate_image` returns the completed image directly. Use `show_image` when you need to apply transforms (resize, crop, format conversion) or as a fallback if `generate_image` returned `status: "generating"`.

| Property | Value |
|----------|-------|
| **Tags** | *(none)* -- always visible (read-only operation) |
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` |
| **Task** | No |
| **MCP App** | `ui://image-viewer/view.html` (interactive viewer in supported clients) |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `uri` | str | *(required)* | Full `image://` resource URI (e.g., `image://a1b2c3/view?format=webp&width=512`) |
| `with_link` | bool | `true` | When `true`, include a one-time `download_url` in the metadata if the server is running on HTTP transport with `BASE_URL` configured. |

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
  "model": "gpt-image-1",
  "prompt_style": null,
  "dimensions": [1024, 683],
  "thumbnail_dimensions": [512, 342],
  "original_size_bytes": 3145728,
  "format": "image/png",
  "transforms_applied": {},
  "download_url": "https://mcp.example.com/artifacts/7f3a...e9b1"
}
```

The `model` field contains the specific model used by the provider (e.g., `"gpt-image-1"`, `"dreamshaper_xl"`), or `null` if the provider does not report a model name.

The `download_url` field is only present when `with_link` is `true` (default) and the server is running on HTTP transport with `IMAGE_GENERATION_MCP_BASE_URL` configured. The link is a one-time download URL (5-minute TTL) — see `create_download_link` for details. The MCP App widget cannot open this URL from its sandboxed iframe, so LLMs should present it directly to the user as a clickable link in the conversation text.

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

## edit_image

Open an image for interactive editing (crop, rotate, flip) in the image viewer UI. The user edits in the viewer widget and saves as a new image. Always edits the original image — resource template transforms are ephemeral and LLM-facing; editor transforms are persistent and user-facing.

| Property | Value |
|----------|-------|
| **Tags** | *(none — read-only, always visible)* |
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` |
| **MCP App** | Opens `ui://image-viewer/view.html` widget |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_id` | str | *(required)* | ID of the image to edit. Use `image://list` to browse available image IDs. |

### Return value

Returns a `ToolResult` with:

1. **TextContent** — JSON metadata with `editable: true` to activate the editor UI:

```json
{
  "editable": true,
  "image_id": "a1b2c3d4e5f6",
  "content_type": "image/png",
  "dimensions": [640, 360],
  "prompt": "watercolor painting of a mountain landscape",
  "provider": "openai"
}
```

2. **ImageContent** — Full-resolution image as base64 (not a thumbnail). The viewer UI uses this to initialize the Cropper.js editor.

### Editor UI

When `editable: true` is received by the MCP Apps widget, it activates the Cropper.js-based editor with:

- **Crop**: Interactive crop box with aspect ratio presets (Free, 1:1, 16:9, 4:3)
- **Rotate**: 90° counter-clockwise / clockwise buttons (lossless)
- **Flip**: Horizontal and vertical flip buttons (lossless)
- **Reset**: Resets all pending edits
- **Save as new image**: Applies transforms server-side and saves as a new image record with `source_image_id` provenance
- **Cancel**: Returns to the waiting state

Saving calls the internal `_save_edited_image` app-only tool and then shows the new image via `show_image`.

### Saved image provenance

Saved images include a `source_image_id` field in their sidecar JSON referencing the original. The `image://{id}/metadata` resource exposes this field.

---

## browse_gallery

Open an interactive visual gallery of all generated images. The gallery renders a responsive thumbnail grid directly in Claude Desktop / claude.ai via the MCP Apps widget.

| Property | Value |
|----------|-------|
| **Tags** | *(none — read-only, always visible)* |
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` |
| **MCP App** | Opens `ui://image-gallery/view.html` widget |

### Parameters

None. The gallery loads all images automatically.

### Return value

JSON with gallery data (for non-UI clients):

```json
{
  "total": 42,
  "page": 1,
  "page_size": 12,
  "items": [
    {
      "image_id": "a1b2c3d4e5f6",
      "status": "completed",
      "prompt": "a mountain landscape",
      "provider": "openai",
      "dimensions": [1024, 1024],
      "created_at": "2026-03-24T10:00:00+00:00",
      "thumbnail_b64": "<base64-encoded 128px WebP>",
      "content_type": "image/png"
    }
  ]
}
```

For MCP Apps-capable clients, the gallery widget is rendered inline with:
- Responsive thumbnail grid (3×3 default, adaptive to available width)
- Hover overlay showing prompt excerpt and provider badge
- Download button (`downloadFile` → `openLink` fallback)
- Prev/Next pagination
- Lightbox view on thumbnail click (see below)

---

## gallery_full_image (app-only)

Load full-resolution image data for the gallery lightbox. App-only — not shown to the model; called internally by the gallery UI when a thumbnail is clicked.

| Property | Value |
|----------|-------|
| **Tags** | *(none)* |
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` |
| **MCP App** | `ui://image-gallery/view.html` (app-only, `visibility=["app"]`) |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_id` | str | *(required)* | Image ID to load |

### Return value

```json
{
  "image_id": "a1b2c3d4e5f6",
  "b64": "<base64-encoded image bytes>",
  "content_type": "image/png",
  "dimensions": [1024, 1024],
  "prompt": "a mountain landscape",
  "provider": "openai",
  "created_at": "2026-03-24T10:00:00+00:00"
}
```

Images larger than 1 MB are resized to 1024 px wide WebP before encoding.

---

## delete_image

Permanently delete an image from the scratch directory. Removes the image file and its metadata sidecar. Hidden in read-only mode.

| Property | Value |
|----------|-------|
| **Tags** | `write` (hidden in read-only mode) |
| **Annotations** | `readOnlyHint: false`, `destructiveHint: true`, `openWorldHint: false` |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_id` | str | *(required)* | Image ID to delete (12-character hex string) |

### Return value

Text confirmation with the deleted image's prompt and provider, e.g.:

```
Deleted image a1b2c3d4e5f6 (prompt: 'a mountain landscape', provider: openai)
```

Raises an error if the image ID is not found.

---

## save_style

Save a reusable style preset as a markdown file. Styles are creative briefs that the LLM interprets per-provider — not prompt fragments. Use to capture a visual direction for reuse across conversations.

| Property | Value |
|----------|-------|
| **Tags** | `write` (hidden in read-only mode) |
| **Annotations** | `readOnlyHint: false`, `destructiveHint: false`, `openWorldHint: false` |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | *(required)* | Style identifier — used as the filename (`{name}.md`). Alphanumeric, hyphens, and underscores only. |
| `body` | str | *(required)* | Markdown prose describing the visual direction (the creative brief) |
| `tags` | list[str] | `null` | Optional categorization tags for browsing/filtering |
| `provider` | str | `null` | Suggested provider (`auto`, `openai`, `sd_webui`) |
| `aspect_ratio` | str | `null` | Default aspect ratio (e.g. `16:9`) |
| `quality` | str | `null` | Default quality level (`standard` or `hd`) |

### Return value

```json
{
  "name": "website",
  "created": true
}
```

`created` is `true` for new styles, `false` when overwriting an existing style.

### Example

```
User: Save this as my website style

Tool call: save_style
  name: "website"
  body: "Minimalist flat illustration. Geometric shapes, clean lines.
         Brand palette: deep teal, warm cream, coral accent."
  tags: ["brand", "web"]
  aspect_ratio: "16:9"
  quality: "hd"
```

---

## delete_style

Delete a style preset from disk. Permanently removes the style file and its in-memory entry. Hidden in read-only mode.

| Property | Value |
|----------|-------|
| **Tags** | `write` (hidden in read-only mode) |
| **Annotations** | `readOnlyHint: false`, `destructiveHint: true`, `openWorldHint: false` |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | *(required)* | Style identifier to delete |

### Return value

```json
{
  "name": "website",
  "deleted": true
}
```

Raises an error if the style is not found.

---

## list_providers

List available image generation providers and their status.

| Property | Value |
|----------|-------|
| **Tags** | *(none)* -- always visible |
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: true`, `idempotentHint: false` |
| **Task** | No |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `force_refresh` | bool | `false` | When `true`, re-runs capability discovery on all providers before returning. Use when providers may have changed (e.g., new SD WebUI checkpoints loaded). |

### Return value

JSON object with a `refreshed_at` ISO 8601 timestamp and provider names, availability, and capability information:

```json
{
  "refreshed_at": "2024-03-18T12:00:00+00:00",
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
  }
}
```

The response is wrapped in an object with `refreshed_at` (ISO 8601 timestamp of when the data was produced) and `providers` (the provider map). Only registered (configured) providers appear in the response. The `capabilities` key is present after startup discovery completes. Degraded providers (where capability discovery failed) show `"degraded": true` with an empty model list.

The `prompt_style` field on each model indicates the recommended prompt format: `"clip"` for SD 1.5/SDXL checkpoints (tag-based), `"natural_language"` for Flux checkpoints, and `null` for providers that do not set a preference (OpenAI, Placeholder).

### Example

```
User: Which image providers are available?

Tool call: list_providers

User: I just loaded a new checkpoint, refresh the list

Tool call: list_providers
  force_refresh: true
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
| **Annotations** | `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false` |
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
- Displays the image with metadata (prompt, provider, model name, dimensions, file size)
- Shows generating, failed, and cancelled states with progress indicators
- Integrates with host theming (colors, fonts, safe area insets) via ext-apps SDK
- Caches rendered images in `localStorage` for instant restore on revisit
- Offers a download button (uses `downloadFile` API or `openLink` fallback) for the full-resolution image

No configuration is needed — the viewer activates automatically on MCP Apps-capable clients. The Claude sandbox domain is auto-computed from `BASE_URL` (see [Configuration](configuration.md#server)). Clients without Apps support see the standard base64 image + metadata response.
