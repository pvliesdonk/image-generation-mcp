# MCP Prompts

image-gen-mcp provides two prompts that give LLM clients guidance on provider selection and prompt formatting.

## select_provider

Guidelines for selecting the best image generation provider based on the user's request.

### When to use

MCP clients (like Claude) can load this prompt to understand provider strengths before calling `generate_image`. It helps the client make informed decisions about which provider to use.

### Content summary

The prompt covers:

- **Provider strengths** -- what each provider (OpenAI, A1111, Placeholder) is best at
- **Selection rules** -- ordered decision logic:
    1. Text/logos/typography -> use OpenAI
    2. Photorealism/portraits/product shots -> prefer A1111 (fall back to OpenAI)
    3. Art/illustration/anime -> prefer A1111 (fall back to OpenAI)
    4. Quick test/placeholder -> use placeholder
    5. General requests -> default to OpenAI
- **Usage guidance** -- how to call `generate_image` with `provider="auto"` or a specific provider name

---

## sd_prompt_guide

Guide for writing effective Stable Diffusion prompts using the CLIP-based tag format.

### When to use

MCP clients should load this prompt when generating images with the A1111 provider. Stable Diffusion models respond better to comma-separated tags than natural language descriptions.

### Content summary

The prompt covers:

- **Tag format** -- comma-separated descriptive tags ordered by importance: `subject, medium, style, lighting, camera, quality tags`
- **Example prompts** -- portrait, landscape, and product shot examples
- **Quality tags** -- `masterpiece, best quality`, `highly detailed, sharp focus`, `8k, ultra high res`
- **Negative prompts** -- general-purpose negative prompt for avoiding common artifacts, plus photorealism and anime-specific additions
- **CLIP token limits** -- SD 1.5: 77 tokens per chunk, SDXL: 77 tokens per chunk with two encoders
- **BREAK syntax** -- how to separate concepts into different CLIP chunks
- **Aspect ratios** -- supported ratios: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`

### Example prompt format

```
1girl, long hair, blue eyes, school uniform, standing, cherry blossoms,
soft lighting, detailed face, masterpiece, best quality
```

See the [Prompt Writing Guide](guides/prompt-writing.md) for more detailed examples and tips.
