# ADR-0006: Image Asset Model with Resource-Based Transforms

## Status

Accepted

## Context

Image generation tools need to return results to MCP clients efficiently. A
1024x1024 PNG is 2-4MB, becoming 3-5MB in base64. Returning full-resolution
images inline in every tool response wastes bandwidth, especially when the
client only needs a preview.

Clients also need images in different formats (WebP for web, JPEG for
compatibility) and resolutions (exact pixel dimensions for final output).
Building separate tools for each transform creates an explosion of tool
surface area.

## Decision Drivers

- **Minimal payload** -- tool responses should be lightweight
- **Flexible access** -- clients choose format, resolution, quality on demand
- **No tool sprawl** -- avoid a separate tool for every transform operation
- **Lossless originals** -- transforms always start from the original, never
  from a derived version

## Considered Options

### Option 1: Return full-res base64 inline (current)

Tool returns the full image as base64 ImageContent.

**Pros:** Simple, one-step.
**Cons:** 3-5MB per response. No format/resolution flexibility. Client pays
full cost even for preview.

### Option 2: Separate transform tool

`generate_image` returns full image. `transform_image` tool takes a file path
and returns a transformed version.

**Pros:** Clear separation of concerns.
**Cons:** Two-step workflow for common cases. Transform tool duplicates
resource access patterns. Tool sprawl as transform options grow.

### Option 3: Resource template with transform-on-read (chosen)

Tool returns a thumbnail (tiny) plus resource URIs. A parameterized resource
template serves any variant on demand via query parameters.

**Pros:** Lightweight tool response. CDN-style transform-on-read. No tool
sprawl -- one resource template handles all transforms. Clients fetch exactly
what they need. Originals always preserved.
**Cons:** Two-step for full-res access (tool + resource read).

## Decision

**Option 3: Resource template with transform-on-read.**

### Tool Response Pattern

`generate_image` saves the original to scratch and returns:
- **ImageContent**: Small thumbnail (~256px, WebP, ~10-50KB) for immediate
  visual feedback
- **TextContent**: JSON metadata with resource URIs

The client "sees" the image immediately via the thumbnail. For full-res or
specific formats, it reads from the resource URI.

### Resource Template

```
image://{image_id}/view{?format,width,height,quality}
```

- No params -> original bytes (lossless, as provider returned)
- `format=webp` -> format conversion
- `width=1920&height=1080` -> resize/crop
- `format=webp&quality=85&width=1920&height=1080` -> full transform

All transforms start from the original -- never from a previously transformed
version. This prevents quality degradation chains.

**Critical constraint:** The resource function contains zero caching or
persistence logic in the initial implementation. Transforms are pure
functions: original bytes in, transformed bytes out. Caching is a future
optimization, not a launch requirement.

### Image Registry

In-memory `dict[str, ImageRecord]` on `ImageService`, keyed by image ID
(SHA-256 prefix of image data). Maps IDs to original file paths and metadata.

### Sidecar Metadata Files

Sidecar JSON files (`{id}.json`) persist the generation provenance alongside
each image (`{id}-original.{ext}`). The in-memory registry is a cache rebuilt
from sidecar files on startup. This ensures provenance survives server
restarts without introducing database dependencies.

### Resolution as a Read-Time Concern

The `generate_image` tool generates at the provider's native resolution.
Exact pixel dimensions are requested via query parameters on the resource
template (`?width=1920&height=1080`). This decouples generation quality from
output resolution and works uniformly across providers with different size
constraints.

## Consequences

### Positive

- Tool responses drop from ~3-5MB to ~10-50KB (thumbnail only)
- Clients fetch exactly the format/resolution they need
- No tool sprawl -- one resource template replaces an entire transform tool
- Originals always preserved -- no quality degradation
- CDN-style pattern is well-understood and extensible
- Registry survives server restarts via sidecar files

### Negative

- Two-step access for full-res images (tool response + resource read)
- Resource reads are synchronous -- large transforms could be slow
  (mitigated: Pillow transforms are <100ms for typical image sizes)

### Future Extensions

- Response caching for frequently-requested transforms
- TTL-based scratch dir cleanup
- Batch transform operations
