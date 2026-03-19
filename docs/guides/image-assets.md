# Image Assets

!!! note "Coming soon"
    This page will be expanded when the image asset model is fully documented.

## Overview

image-generation-mcp uses a content-addressed image registry to manage generated images. Each image is assigned a unique ID based on the SHA-256 hash of its content.

## Key concepts

- **Image ID** -- content-addressed identifier (`SHA-256[:12]`) for each generated image
- **Scratch directory** -- local storage at `IMAGE_GENERATION_MCP_SCRATCH_DIR` (default `~/.image-generation-mcp/images/`)
- **Sidecar metadata** -- JSON file alongside each image with generation provenance (prompt, provider, dimensions, timestamps)
- **Resource URIs** -- access images and transforms via `image://{id}/view{?format,width,height,quality}`
- **Transform-on-read** -- format conversion, resize, and crop happen at resource access time, not generation time

## How it works

1. `generate_image` creates the image and registers it in the local registry
2. The tool returns a small thumbnail preview plus resource URIs
3. Clients access the full-resolution image and transforms via resource URIs
4. The registry rebuilds from sidecar files on server startup

## Resources

- `image://{id}/view` -- original image or transformed version
- `image://{id}/metadata` -- generation metadata (prompt, provider, dimensions)
- `image://list` -- all registered images

See [Resources](../resources.md) for full details on available transforms.
