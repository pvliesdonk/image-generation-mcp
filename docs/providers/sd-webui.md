# SD WebUI (Stable Diffusion WebUI)

Image generation via the [Stable Diffusion WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) REST API. Best for photorealism, portraits, anime, and artistic styles.

> **Compatible with** AUTOMATIC1111, Forge, reForge, and Forge-neo.

## Setup

1. Install and start one of the compatible WebUI forks with API access enabled:

    ```bash
    # Start WebUI with API enabled
    python launch.py --api
    ```

2. Set the host URL:

    ```bash
    IMAGE_GENERATION_MCP_SD_WEBUI_HOST=http://localhost:7860
    ```

The provider registers automatically when `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` is set.

> **Compatibility:** SD WebUI version 1.6 (or equivalent Forge/reForge version) or later is required. The split `sampler_name` + `scheduler` API was introduced in 1.6; earlier versions do not support the `scheduler` field.

## Model-aware presets

The provider auto-detects the SD architecture from the checkpoint name and applies optimized generation parameters:

### SD 1.5 (default)

Used when no XL/Lightning/Turbo tag is found in the checkpoint name.

| Parameter | Value |
|-----------|-------|
| Base resolution | 768px |
| Steps | 30 |
| CFG scale | 7.0 |
| Sampler | DPM++ 2M |
| Scheduler | Karras |

| Aspect ratio | Size |
|-------------|------|
| `1:1` | 768x768 |
| `16:9` | 912x512 |
| `9:16` | 512x912 |
| `3:2` | 768x512 |
| `2:3` | 512x768 |

### SDXL

Used when checkpoint name contains `sdxl`, `xl_`, `_xl`, or `-xl`.

| Parameter | Value |
|-----------|-------|
| Base resolution | 1024px |
| Steps | 35 |
| CFG scale | 7.5 |
| Sampler | DPM++ 2M |
| Scheduler | Karras |

| Aspect ratio | Size |
|-------------|------|
| `1:1` | 1024x1024 |
| `16:9` | 1344x768 |
| `9:16` | 768x1344 |
| `3:2` | 1216x832 |
| `2:3` | 832x1216 |

### SDXL Lightning/Turbo

Used when checkpoint name contains XL tags AND `lightning` or `turbo`.

| Parameter | Value |
|-----------|-------|
| Base resolution | 1024px |
| Steps | 6 |
| CFG scale | 2.0 |
| Sampler | DPM++ SDE |
| Scheduler | Karras |

Sizes are the same as standard SDXL.

### Flux Dev

Used when checkpoint name contains `flux` (without `schnell`). Requires [Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) or compatible fork with Flux support.

| Parameter | Value |
|-----------|-------|
| Base resolution | 1024px |
| Steps | 20 |
| CFG scale | 1.0 |
| Distilled CFG scale | 3.5 (Forge-specific) |
| Sampler | Euler |
| Scheduler | Simple |
| Negative prompt | Not supported |

Sizes are the same as SDXL.

### Flux Schnell

Used when checkpoint name contains both `flux` and `schnell`. Optimized for fast inference.

| Parameter | Value |
|-----------|-------|
| Base resolution | 1024px |
| Steps | 4 |
| CFG scale | 1.0 |
| Distilled CFG scale | 3.5 (Forge-specific) |
| Sampler | Euler |
| Scheduler | Simple |
| Negative prompt | Not supported |

Sizes are the same as SDXL.

## Checkpoint override

### Server default (env var)

To set a default checkpoint for all generation requests:

```bash
IMAGE_GENERATION_MCP_SD_WEBUI_MODEL=realisticVisionV60B1_v51VAE.safetensors
```

When `SD_WEBUI_MODEL` is set, the provider sends `override_settings.sd_model_checkpoint` in the API payload and uses the checkpoint name for preset detection.

### Per-call override (model parameter)

The `model` parameter on `generate_image` overrides the server default for a single request. Preset detection (steps, CFG, sampler, sizes) uses the per-call model name, not the constructor default:

```
generate_image(prompt="...", provider="sd_webui", model="dreamshaperXL_v21.safetensors")
```

Use `list_providers` to discover available checkpoints and their model IDs.

## Background transparency

The `background` parameter is **not supported** by SD WebUI. When `background="transparent"` is passed, it is silently ignored (a debug log is emitted). Stable Diffusion does not natively support transparent background generation.

## Capability discovery

At startup, the provider calls:

- `GET /sdapi/v1/sd-models` -- lists all installed checkpoints
- `GET /sdapi/v1/options` -- identifies the currently active checkpoint

Each checkpoint is mapped to a `ModelCapabilities` object with architecture-specific defaults (resolution, steps, CFG, sampler) based on the same name detection used for generation presets.

If the SD WebUI server is unreachable (connection error or timeout), the provider is marked as **degraded** -- it remains available for generation but with an empty model list in the capabilities response. This prevents a slow or offline SD WebUI instance from blocking server startup.

## Negative prompts

SD WebUI has native negative prompt support via the `negative_prompt` field in the API payload. This is more effective than OpenAI's "Avoid:" workaround.

> **Note:** Flux models do not support negative prompts. When a Flux checkpoint is detected, the `negative_prompt` field is omitted from the API payload entirely. If a negative prompt is provided, it is silently ignored with a debug log.

See the [Prompt Writing Guide](../guides/prompt-writing.md) for recommended negative prompts.

## Metadata

The provider extracts from the SD WebUI response:

- **seed** -- the random seed used for generation (useful for reproducibility)
- **model name** -- the active checkpoint name (from response `info` JSON)
- **size** -- pixel dimensions used
- **steps** -- number of diffusion steps

## Timeout

The default timeout is **180 seconds**. SDXL at high resolution on consumer GPUs can take 30-60+ seconds. If you experience timeouts, ensure your WebUI is responding.

## Deprecated env var aliases

The previous `A1111_HOST` and `A1111_MODEL` env var names are still accepted as deprecated aliases:

| Deprecated | Current |
|------------|---------|
| `IMAGE_GENERATION_MCP_A1111_HOST` | `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` |
| `IMAGE_GENERATION_MCP_A1111_MODEL` | `IMAGE_GENERATION_MCP_SD_WEBUI_MODEL` |

## Troubleshooting

| Error | Cause | Resolution |
|-------|-------|------------|
| Connection error | Cannot reach SD WebUI | Verify WebUI is running with `--api` flag at the configured host |
| Timeout (180s) | Generation too slow | Check GPU utilization; consider a faster model or lower resolution |
| HTTP 404 | Wrong API endpoint | Verify the WebUI version supports `/sdapi/v1/txt2img` |
