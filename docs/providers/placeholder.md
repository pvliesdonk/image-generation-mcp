# Placeholder Provider

Zero-cost solid-color PNG generation for testing, drafts, and CI pipelines.

## Overview

The placeholder provider generates simple solid-color PNG images without any external dependencies or API keys. The color is deterministically derived from the MD5 hash of the prompt, so the same prompt always produces the same color.

## When to use

- **Testing** -- verify your MCP client configuration without API costs
- **Drafts and mock-ups** -- create placeholder images during development
- **CI pipelines** -- test image generation workflows without external services
- **Demos** -- show the image generation flow without requiring API keys

## Availability

The placeholder provider is **always registered** -- it requires no configuration, no API key, and no external service.

## Aspect ratios

| Aspect ratio | Size |
|-------------|------|
| `1:1` | 480x480 |
| `16:9` | 640x360 |
| `9:16` | 360x640 |
| `3:2` | 480x320 |
| `2:3` | 320x480 |

## Parameters

- **prompt** -- used to determine the output color (via MD5 hash)
- **negative_prompt** -- ignored
- **quality** -- ignored
- **aspect_ratio** -- maps to pixel sizes above

## Output

- **Format:** PNG
- **Content:** Solid color fill
- **Size:** ~1-2 KB per image
- **Generation time:** Instant (< 1ms)
