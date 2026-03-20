# ADR-0003: A1111 Model-Aware Generation Presets

## Status

Accepted

## Context

Stable Diffusion models have fundamentally different optimal generation
parameters. SD 1.5, SDXL, and SDXL Lightning/Turbo each need different:

- **Resolution** — SD 1.5 at 768px, SDXL at 1024px
- **Steps** — SD 1.5 needs 30, SDXL needs 35, Lightning needs only 6
- **CFG scale** — SD 1.5/SDXL at 7.0-7.5, Lightning at 2.0
- **Sampler** — Lightning works better with DPM++ SDE vs DPM++ 2M

Using wrong parameters causes artifacts, blurry images, or wasted compute.

## Decision

Auto-detect the SD architecture from the checkpoint name and apply the
appropriate preset. Detection uses string matching on the model name:

1. Check for Lightning/Turbo tags (`lightning`, `turbo`) + XL → `_SDXL_LIGHTNING_PRESET`
2. Check for XL tags (`sdxl`, `xl_`, `_xl`, `-xl`) → `_SDXL_PRESET`
3. Fallback → `_SD15_PRESET`

Each preset is a frozen dataclass (`_A1111Preset`) containing:
- `sizes` — aspect ratio → (width, height) mapping
- `steps`, `sampler`, `scheduler`, `cfg_scale` — generation parameters
- `quality_tier` — metadata label ("medium" or "high")

### Preset Values

| Preset | Base Size | Steps | CFG | Sampler | Scheduler |
|--------|-----------|-------|-----|---------|-----------|
| SD 1.5 | 768px | 30 | 7.0 | DPM++ 2M | Karras |
| SDXL | 1024px | 35 | 7.5 | DPM++ 2M | Karras |
| SDXL Lightning | 1024px | 6 | 2.0 | DPM++ SDE | Karras |

## Consequences

### Positive

- Users get good results without needing to know optimal parameters per model
- Checkpoint override (`override_settings.sd_model_checkpoint`) ensures the
  right model is loaded
- Preset detection is purely string-based — no API call to A1111 needed

### Negative

- New model architectures (SD 3, Flux) will need new presets
- Checkpoint naming is not standardized — detection may misclassify uncommon names
- Detection falls back to SD 1.5, which may produce suboptimal results for
  unrecognized XL models

### Future Considerations

- ComfyUI will need a different approach (workflow-based, not parameter-based)
- Could add an `a1111_preset` config option to force a specific preset
