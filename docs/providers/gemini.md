# Gemini Provider

Image generation via Google's Gemini native `generateContent` API with `responseModalities=["IMAGE"]`. Good for general-purpose generation with a generous free tier.

## Setup

Set your Google API key:

```bash
IMAGE_GENERATION_MCP_GOOGLE_API_KEY=AIza...
```

The provider registers automatically when this variable is set. Get a key at [Google AI Studio](https://aistudio.google.com/apikey).

## Supported models

| Model | Notes |
|-------|-------|
| `gemini-2.5-flash-image` | Default — fast, high-volume, stable |

Use `list_providers` to see which models are available on your API key.

## Aspect ratios and sizes

All five project aspect ratios are natively supported:

| Aspect ratio | Gemini parameter |
|-------------|-----------------|
| `1:1` | `1:1` |
| `16:9` | `16:9` |
| `9:16` | `9:16` |
| `3:2` | `3:2` |
| `2:3` | `2:3` |

## Quality levels

The `quality` parameter is accepted and recorded in metadata, but Gemini's
`generateContent` API does not expose a resolution or quality parameter (unlike
the Imagen API). All images are generated at Gemini's default resolution.

## Negative prompts

Gemini does not have native negative prompt support. When a `negative_prompt` is provided, it is appended to the prompt as:

```
{prompt}

Avoid: {negative_prompt}
```

## Background transparency

Not supported. The `background` parameter is silently ignored — all images are generated with an opaque background.

## Prompt style

Gemini works best with natural language descriptions:

```
A professional product photo of white sneakers on a clean white background,
studio lighting, sharp focus, commercial photography style
```

Avoid CLIP-style tag lists (those work better with Stable Diffusion).

## Per-call model selection

The `model` parameter on `generate_image` overrides the provider's default model for a single request:

```
generate_image(prompt="...", provider="gemini", model="gemini-2.5-flash-image")
```

Use `list_providers` to discover available models and their capabilities.

## Capability discovery

At startup, the provider returns a static list of known image-capable Gemini models. Unlike OpenAI, the Gemini `models.list()` API does not reliably filter to image-generation models, so the known model list is maintained in the provider code.

## Cost

Gemini has a generous free tier (check [Google AI pricing](https://ai.google.dev/pricing) for current limits). The provider is not in `paid_providers` by default — no confirmation prompt is shown before use. Set `IMAGE_GENERATION_MCP_PAID_PROVIDERS=gemini,openai` if you want cost confirmation for Gemini.

## SynthID watermark

All Gemini-generated images include an invisible SynthID watermark added by Google. This is automatic and cannot be disabled.

## Error handling

| Error | Cause | Resolution |
|-------|-------|------------|
| Content policy rejection | Prompt violates Gemini safety policy | Modify the prompt to comply with Google's usage policies |
| Connection error | Cannot reach Gemini API | Check network connectivity and API key validity |
| No image in response | Model returned text instead of image | Try rephrasing the prompt or use a different model |
| API error (HTTP 429) | Rate limited | Wait and retry; consider reducing request frequency |
