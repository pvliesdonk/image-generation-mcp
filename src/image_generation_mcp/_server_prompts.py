"""MCP prompt registrations — provider selection and prompt guidance.

Prompts provide reusable LLM instruction templates exposed to clients.
Write prompts should be tagged with ``tags={"write"}`` so they are hidden
in read-only mode alongside write tools.

See https://gofastmcp.com/servers/prompts for the full prompt API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from mcp.types import Icon

from image_generation_mcp._server_deps import get_service

if TYPE_CHECKING:
    from image_generation_mcp.service import ImageService
    from image_generation_mcp.styles import StyleEntry

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
- **Supports:** Native negative prompt (SD 1.5/SDXL only), fine-grained parameter control
- **Prompt style depends on the loaded model:**
  - **SD 1.5 / SDXL:** Comma-separated CLIP tags (see sd_prompt_guide)
  - **Flux (dev/schnell):** Natural language descriptions, like OpenAI (see sd_prompt_guide)
- **Note:** Compatible with A1111, Forge, reForge, and Forge-neo
- Check `list_providers` for each model's `prompt_style` field

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
Guide for writing SD WebUI prompts. The correct prompt style depends on the
model architecture — check `list_providers` to see which models are loaded.

## SD 1.5 / SDXL — CLIP Tag Format

These models use a CLIP text encoder. Format prompts as comma-separated
descriptive tags ordered by importance:

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

### Quality Tags

Add these to improve output quality:
- `masterpiece, best quality` — general quality boost
- `highly detailed, sharp focus` — detail enhancement
- `8k, ultra high res` — resolution boost (use sparingly)
- `professional, award winning` — style refinement

### Negative Prompt

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

### CLIP Token Limits

- **SD 1.5:** 77 tokens per CLIP chunk. Use `BREAK` to start a new chunk.
- **SDXL:** 77 tokens per chunk, but two CLIP encoders (ViT-L + ViT-bigG).

Keep prompts concise. Front-load the most important tags — tokens beyond
the first 77-token chunk have diminishing influence.

### BREAK Syntax

Use `BREAK` to separate prompt concepts into different CLIP chunks:

```
1girl, detailed face, blue eyes BREAK
forest background, sunlight through trees BREAK
masterpiece, best quality, sharp focus
```

## Flux — Natural Language Format

Flux models (flux-dev, flux-schnell) use a T5 text encoder, NOT CLIP.
Write prompts as natural language descriptions — the same style as OpenAI.

**Key differences from SD 1.5 / SDXL:**
- Use complete sentences, not comma-separated tags
- Do NOT include quality tags (`masterpiece`, `best quality`) — they are meaningless to Flux
- Do NOT write a negative prompt — Flux does not support them (the server omits them automatically)
- Do NOT use `BREAK` syntax — Flux does not use CLIP chunking
- CFG scale and sampler are handled automatically by the server

### Flux Example Prompts

**Portrait:**
```
A young woman with long flowing hair and striking blue eyes wearing a
school uniform, standing beneath cherry blossom trees with soft natural
light filtering through the petals
```

**Landscape:**
```
A dramatic mountain landscape at sunset with towering peaks reflected in
a perfectly still alpine lake, storm clouds lit orange and purple by the
setting sun
```

**Product shot:**
```
A pair of pristine white sneakers on a clean white background, shot from
a three-quarter angle with professional studio lighting and crisp focus
```

### Flux Schnell vs Flux Dev

- **Flux Schnell:** 4 steps, fastest generation (~5-10s). Good for drafts.
- **Flux Dev:** 20 steps, higher quality (~60-120s). Use for final output.

Both use Euler sampler, Simple scheduler, CFG 1.0, and distilled CFG 3.5
(all set automatically by the server).

## Aspect Ratios

Supported aspect ratios: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`.
The server maps these to optimal pixel dimensions for each SD model.

## Workflow

1. Check `list_providers` to see available models and their `prompt_style`
   (`"clip"` for SD 1.5/SDXL, `"natural_language"` for Flux)
2. Write your prompt in the appropriate style for the model
3. For SD 1.5/SDXL: add quality tags and a negative prompt
4. For Flux: write a natural language description, skip negative prompt
5. Call `generate_image` with `provider="sd_webui"`:

**SD 1.5 / SDXL example:**
```
generate_image(
    prompt="1girl, long hair, school uniform, cherry blossoms, masterpiece, best quality",
    negative_prompt="lowres, bad anatomy, bad hands, worst quality, low quality",
    provider="sd_webui",
    aspect_ratio="2:3"
)
```

**Flux example:**
```
generate_image(
    prompt="A young woman with long hair in a school uniform standing beneath cherry blossom trees",
    provider="sd_webui",
    model="flux1-dev-bnb-nf4-v2.safetensors",
    aspect_ratio="2:3"
)
```
"""


_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"


def _build_apply_style_text(entry: StyleEntry, user_request: str) -> str:
    """Build the combined prompt text for applying a style.

    Extracted as a module-level function for testability.

    Args:
        entry: The style to apply.
        user_request: The user's image generation request.

    Returns:
        Combined text with style body, defaults, and adaptation instructions.
    """
    defaults = []
    if entry.provider:
        defaults.append(f"- Suggested provider: {entry.provider}")
    if entry.aspect_ratio:
        defaults.append(f"- Aspect ratio: {entry.aspect_ratio}")
    if entry.quality:
        defaults.append(f"- Quality: {entry.quality}")
    if entry.tags:
        defaults.append(f"- Tags: {', '.join(entry.tags)}")

    defaults_text = "\n".join(defaults) if defaults else "- (no defaults set)"

    return f"""\
# Apply Style: {entry.name}

## User Request

{user_request}

## Style Creative Brief

{entry.body}

## Style Defaults

{defaults_text}

## Instructions

You are applying the style "{entry.name}" to the user's request above.

**Important: Styles are creative briefs, not prompt fragments.**

1. Read the style's creative brief above and extract the visual direction:
   palette, composition, mood, medium, constraints.
2. Combine that direction with the user's specific request.
3. Compose a provider-appropriate prompt for `generate_image`:
   - **For OpenAI:** Compose in natural language. Describe the scene
     incorporating the style's visual direction.
   - **For SD WebUI (SD 1.5/SDXL):** Compose as comma-separated CLIP tags.
     Translate the style's concepts into appropriate tags. Include a
     negative prompt based on the style's constraints.
   - **For SD WebUI (Flux):** Compose in natural language, similar to OpenAI.
   - Check `list_providers` for each model's `prompt_style` field.
4. **Do NOT copy the style text verbatim into the prompt.** Interpret and
   adapt it for the target provider's format.
5. Use the style's frontmatter defaults (provider, aspect_ratio, quality)
   as starting parameters, unless the user explicitly overrides them.
6. Use `select_provider` guidance for provider choice when provider is
   "auto" or not specified in the style."""


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
            "Guide for writing SD WebUI prompts — "
            "CLIP tags for SD 1.5/SDXL, natural language for Flux"
        ),
        icons=[Icon(src=_LUCIDE.format("book-open-text"), mimeType="image/svg+xml")],
    )
    def sd_prompt_guide() -> str:
        """Return Stable Diffusion prompt writing guide."""
        return _SD_PROMPT_GUIDE

    @mcp.prompt(
        name="apply_style",
        description=(
            "Apply a saved style preset to an image generation request. "
            "Loads the style's creative brief and instructs the LLM to "
            "interpret it per-provider — not copy it verbatim."
        ),
        icons=[Icon(src=_LUCIDE.format("palette"), mimeType="image/svg+xml")],
    )
    def apply_style(
        style_name: str,
        user_request: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Return combined prompt text for applying a style to a request.

        Args:
            style_name: Name of the style preset to apply.
            user_request: The user's image generation request.

        Returns:
            Combined text with style body, defaults, and adaptation
            instructions for the LLM.
        """
        entry = service.get_style(style_name)
        if entry is None:
            return (
                f"Style '{style_name}' not found. "
                "Use style://list to browse available styles, "
                "or save_style to create a new one."
            )

        return _build_apply_style_text(entry, user_request)
