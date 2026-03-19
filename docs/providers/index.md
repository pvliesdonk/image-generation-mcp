# Providers

image-generation-mcp supports multiple image generation providers. Each provider is registered at startup based on available configuration (API keys, service URLs).

## Provider comparison

| | OpenAI | A1111 (Stable Diffusion) | Placeholder |
|---|--------|--------------------------|-------------|
| **Best for** | Text, logos, typography, general-purpose | Photorealism, portraits, anime, artistic styles | Testing, drafts, CI |
| **Models** | gpt-image-1, dall-e-3 | SD 1.5, SDXL, SDXL Lightning/Turbo | -- |
| **Quality** | High | Varies by model and steps | N/A (solid color) |
| **Speed** | 5-15s | 10-60s (depends on GPU) | Instant |
| **Cost** | Per-image API pricing | Self-hosted (GPU cost) | Free |
| **Negative prompt** | Appended as "Avoid:" clause | Native support | Ignored |
| **Background control** | Supported (gpt-image-1 only) | Not supported (ignored) | Supported (RGBA PNG) |
| **Requires** | `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | Running A1111 WebUI + `IMAGE_GENERATION_MCP_A1111_HOST` | Nothing |

## Which provider should I use?

**Start with placeholder** if you're testing the setup or building automations. It generates instantly with zero cost.

**Use OpenAI** for:

- Text rendering, logos, and typography (OpenAI handles text best)
- General-purpose image generation when you need reliability
- When you don't have a GPU for local generation

**Use A1111** for:

- Photorealistic images (portraits, product shots, photography)
- Anime, manga, and illustration styles
- Fine-grained control over generation parameters
- When you have a local GPU and want unlimited generations

## Auto-selection

When `provider="auto"` (the default), the server analyzes your prompt using keyword matching and selects the best available provider:

| Prompt keywords | Preferred provider chain |
|----------------|--------------------------|
| realistic, photo, photography, portrait photo, product shot, headshot | a1111 -> openai |
| text, logo, typography, poster, banner, signage, lettering, font | openai |
| quick, draft, test, placeholder, mock | placeholder |
| art, painting, illustration, watercolor, oil painting, sketch, drawing | a1111 -> openai |
| anime, manga, kawaii, chibi | a1111 -> openai |
| *(no match)* | openai -> a1111 -> placeholder |

The first matching rule wins. Within a rule, the first available provider is selected. If no provider in the chain is available, any registered provider is returned as a fallback.

When `background="transparent"` is requested, providers with transparent background support are preferred within each selection rule. This is a secondary filter -- keyword heuristics still determine the rule.

## Provider registration

Providers are registered automatically at startup based on environment variables:

1. **Placeholder** -- always registered (zero cost, no configuration)
2. **OpenAI** -- registered when `IMAGE_GENERATION_MCP_OPENAI_API_KEY` is set
3. **A1111** -- registered when `IMAGE_GENERATION_MCP_A1111_HOST` is set
