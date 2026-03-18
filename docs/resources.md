# MCP Resources

image-gen-mcp exposes resources for provider information and image access.

## info://providers

Provider capabilities and supported features.

**MIME type:** `application/json`

### Response

```json
{
  "providers": {
    "placeholder": { "available": true, "description": "PlaceholderImageProvider (placeholder)" },
    "openai": { "available": true, "description": "OpenAIImageProvider (openai)" }
  },
  "supported_aspect_ratios": ["1:1", "16:9", "9:16", "3:2", "2:3"],
  "supported_quality_levels": ["standard", "hd"]
}
```

Only registered (configured) providers appear. Unavailable providers are not listed.

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
