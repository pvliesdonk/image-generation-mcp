"""MCP prompt registrations — provider selection and prompt guidance.

Prompts provide reusable LLM instruction templates exposed to clients.
Write prompts should be tagged with ``tags={"write"}`` so they are hidden
in read-only mode alongside write tools.

See https://gofastmcp.com/servers/prompts for the full prompt API.
"""

from __future__ import annotations

from fastmcp import FastMCP
from mcp.types import Icon

_SELECT_PROVIDER_PROMPT = """\
You have access to an image generation MCP server with multiple providers.
Choose the best provider for the user's request based on these guidelines:

## Provider Strengths

### OpenAI (gpt-image-1 / dall-e-3)
- **Best for:** Text rendering, logos, typography, posters, banners, signs
- **Good at:** General-purpose generation, following complex instructions
- **Supports:** Negative prompt (as "Avoid:" clause), multiple quality levels
- **Prompt style:** Natural language descriptions work well

### SD WebUI (Stable Diffusion WebUI)
- **Best for:** Photorealism, portraits, product shots, artistic styles
- **Good at:** Anime/manga, watercolor, oil painting, illustration
- **Supports:** Native negative prompt, fine-grained parameter control
- **Prompt style:** Comma-separated tags work best (see sd_prompt_guide)
- **Note:** Compatible with A1111, Forge, reForge, and Forge-neo

### Placeholder
- **Best for:** Quick drafts, testing, mock-ups
- **Produces:** Solid-color PNG images (no real generation)
- **Use when:** You need a fast placeholder without API costs

## Selection Rules

1. If the request involves **text, logos, or typography** → use **openai**
2. If the request involves **photorealism, portraits, or product shots** → prefer **sd_webui** (fall back to openai)
3. If the request involves **art, illustration, anime, or painting** → prefer **sd_webui** (fall back to openai)
4. If the request is a **quick test or placeholder** → use **placeholder**
5. For **general requests** → default to **openai** (most versatile)

## Usage

Call `generate_image` with `provider="auto"` for automatic selection,
or specify a provider name directly. Use `list_providers` to see which
providers are currently available.
"""

_SD_PROMPT_GUIDE = """\
When generating images with the SD WebUI (Stable Diffusion) provider, format
prompts as comma-separated tags for best results. This guide covers the
CLIP-based prompt format used by Stable Diffusion models.

## Prompt Format

Use comma-separated descriptive tags, ordered by importance:

```
subject, medium, style, lighting, camera, quality tags
```

### Example Prompts

**Portrait:**
```
1girl, long hair, blue eyes, school uniform, standing, cherry blossoms,
soft lighting, detailed face, masterpiece, best quality
```

**Landscape:**
```
mountain landscape, sunset, dramatic clouds, lake reflection,
cinematic lighting, wide angle, 8k, highly detailed
```

**Product shot:**
```
white sneakers, product photography, studio lighting, white background,
sharp focus, commercial photography, high resolution
```

## Quality Tags

Add these to improve output quality:
- `masterpiece, best quality` — general quality boost
- `highly detailed, sharp focus` — detail enhancement
- `8k, ultra high res` — resolution boost (use sparingly)
- `professional, award winning` — style refinement

## Negative Prompt

Always include a negative prompt to avoid common artifacts:

**General-purpose negative:**
```
lowres, bad anatomy, bad hands, text, error, missing fingers,
extra digit, fewer digits, cropped, worst quality, low quality,
normal quality, jpeg artifacts, signature, watermark, blurry
```

**For photorealism, add:**
```
cartoon, anime, illustration, painting, drawing, art, sketch
```

**For anime/illustration, add:**
```
photo, realistic, 3d render
```

## CLIP Token Limits

- **SD 1.5:** 77 tokens per CLIP chunk. Use `BREAK` to start a new chunk.
- **SDXL:** 77 tokens per chunk, but two CLIP encoders (ViT-L + ViT-bigG).

Keep prompts concise. Front-load the most important tags — tokens beyond
the first 77-token chunk have diminishing influence.

## BREAK Syntax

Use `BREAK` to separate prompt concepts into different CLIP chunks:

```
1girl, detailed face, blue eyes BREAK
forest background, sunlight through trees BREAK
masterpiece, best quality, sharp focus
```

## Aspect Ratios

Supported aspect ratios: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`.
The server maps these to optimal pixel dimensions for each SD model.

## Workflow

1. Draft your prompt using comma-separated tags (subject first)
2. Add quality tags and a negative prompt
3. Call `generate_image` with `provider="sd_webui"`:

```
generate_image(
    prompt="1girl, long hair, school uniform, cherry blossoms, masterpiece, best quality",
    negative_prompt="lowres, bad anatomy, bad hands, worst quality, low quality",
    provider="sd_webui",
    aspect_ratio="2:3"
)
```
"""


_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"


def register_prompts(mcp: FastMCP) -> None:
    """Register all MCP prompts on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register prompts on.
    """

    @mcp.prompt(
        name="select_provider",
        description=(
            "Use when choosing a specific provider instead of auto-selection. "
            "Not needed when provider='auto' (the default)."
        ),
        icons=[Icon(src=_LUCIDE.format("route"), mimeType="image/svg+xml")],
    )
    def select_provider() -> str:
        """Return provider selection guidance."""
        return _SELECT_PROVIDER_PROMPT

    @mcp.prompt(
        name="sd_prompt_guide",
        description=(
            "Guide for writing Stable Diffusion prompts "
            "(CLIP tag format, negative prompts, BREAK syntax)"
        ),
        icons=[Icon(src=_LUCIDE.format("book-open-text"), mimeType="image/svg+xml")],
    )
    def sd_prompt_guide() -> str:
        """Return Stable Diffusion prompt writing guide."""
        return _SD_PROMPT_GUIDE
