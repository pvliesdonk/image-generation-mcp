# OpenAI Provider

Image generation via OpenAI's Images API. Best for text rendering, logos, typography, and general-purpose generation.

## Setup

Set your OpenAI API key:

```bash
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
```

The provider registers automatically when this variable is set.

## Supported models

| Model | Status | Formats | Notes |
|-------|--------|---------|-------|
| `gpt-image-1` | Current (default) | PNG, JPEG, WebP | Best quality, native format selection |
| `dall-e-3` | Legacy | PNG only | Deprecated May 2026 |

## Aspect ratios and sizes

### gpt-image-1

| Aspect ratio | Size |
|-------------|------|
| `1:1` | 1024x1024 |
| `16:9` | 1536x1024 |
| `9:16` | 1024x1536 |
| `3:2` | 1536x1024 |
| `2:3` | 1024x1536 |

### dall-e-3

| Aspect ratio | Size |
|-------------|------|
| `1:1` | 1024x1024 |
| `16:9` | 1792x1024 |
| `9:16` | 1024x1792 |
| `3:2` | 1792x1024 |
| `2:3` | 1024x1792 |

## Quality levels

| Quality param | gpt-image-1 API value | dall-e-3 API value |
|---------------|----------------------|-------------------|
| `standard` | `high` | `standard` |
| `hd` | `high` | `hd` |

## Negative prompts

OpenAI does not have native negative prompt support. When a `negative_prompt` is provided, it is appended to the prompt as:

```
{prompt}

Avoid: {negative_prompt}
```

## Background transparency

The `background` parameter controls whether the generated image has a transparent or opaque background.

| Model | `background` support |
|-------|---------------------|
| `gpt-image-1` | Supported -- passed to the API as-is (`"opaque"` or `"transparent"`) |
| `dall-e-3` | Not supported -- parameter is ignored |

When `background="transparent"` is used with `gpt-image-1`, the output PNG includes an alpha channel.

## Revised prompt

`dall-e-3` may rewrite your prompt for better results. The rewritten prompt is included in the response metadata as `revised_prompt`. `gpt-image-1` does not rewrite prompts.

## Prompt style

OpenAI models work best with natural language descriptions:

```
A professional product photo of white sneakers on a clean white background,
studio lighting, sharp focus, commercial photography style
```

For text rendering:

```
A minimalist logo for "Acme Corp" with clean sans-serif typography,
blue and white color scheme, modern design
```

## Per-call model selection

The `model` parameter on `generate_image` overrides the provider's default model for a single request. Size table and format selection adjust automatically:

```
generate_image(prompt="...", provider="openai", model="dall-e-3")
```

When switching to `dall-e-3`, the larger DALL-E 3 size table is used and output format is forced to PNG (the only format DALL-E 3 supports). When switching to `gpt-image-1`, the standard size table and configured output format are used.

Use `list_providers` to discover available models.

## Capability discovery

At startup, the provider calls `client.models.list()` to discover which image models are available on your API key. It filters to known image models (`gpt-image-1`, `dall-e-3`, `dall-e-2`) and maps each to a capabilities object with model-specific defaults (supported sizes, formats, features).

If the API call fails (network error, invalid key), the provider is marked as **degraded** -- it remains available for generation but with an empty model list in the capabilities response.

## Cost

OpenAI charges per image generated. Pricing varies by model, size, and quality level. See the [OpenAI pricing page](https://openai.com/api/pricing/) for current rates.

`gpt-image-1` is generally more expensive than `dall-e-3` but produces higher quality output with more flexible format options.

## Error handling

| Error | Cause | Resolution |
|-------|-------|------------|
| Content policy rejection | Prompt violates OpenAI content policy | Modify the prompt to comply with OpenAI's usage policies |
| Connection error | Cannot reach OpenAI API | Check network connectivity and API key validity |
| API error (HTTP 429) | Rate limited | Wait and retry; consider reducing request frequency |
