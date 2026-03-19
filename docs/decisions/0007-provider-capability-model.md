# ADR-0007: Provider Capability Model

## Status

Accepted

## Context

Providers have hardcoded capabilities (supported sizes, quality mappings,
format support) buried in implementation files. The LLM client has no way to
discover what each provider can do at runtime -- `list_providers` returns only
`{available: True, description: str}`.

Competitor analysis (simonChoi034/image-gen-mcp) demonstrated a dynamic
capability model where each provider reports its capabilities at startup. Our
project needs the same: a structured data model that lets clients query what
each provider supports before choosing one.

Key requirements:

- Per-model capability reporting (a provider may offer multiple models with
  different capabilities)
- Runtime discovery at startup via provider-specific API introspection
- Graceful degradation when introspection APIs fail
- Staleness detection via discovery timestamps

## Decision Drivers

- **Client intelligence** -- LLM clients need capability data to make informed
  provider/model choices
- **Provider heterogeneity** -- OpenAI, A1111, and Placeholder have very
  different capability profiles
- **Startup resilience** -- a single failing provider must not block the server
- **Zero runtime cost** -- capabilities are discovered once at startup, not per
  request

## Considered Options

### Option 1: Hardcoded capability constants per provider

Each provider exposes a static `CAPABILITIES` dict at module level.

**Pros:** Simple, no API calls, no failure modes.
**Cons:** Stale when provider adds/removes models. Cannot reflect API key
access level (e.g. which OpenAI models are available to the user).

### Option 2: Dynamic discovery via protocol method (chosen)

Each provider implements `discover_capabilities()` which queries the
provider's API at startup and returns a structured dataclass.

**Pros:** Reflects actual runtime state. Handles provider-specific discovery
(OpenAI models.list, A1111 sd-models endpoint). Graceful degradation on
failure.
**Cons:** Adds startup latency (one API call per provider). Discovery can fail.

### Option 3: Hybrid static + dynamic

Static base capabilities enriched with dynamic model list.

**Pros:** Always has some capabilities even if discovery fails.
**Cons:** Two sources of truth. Unclear which wins on conflict.

## Decision

**Option 2: Dynamic discovery via protocol method.**

### Data Model

Two frozen dataclasses model the capability hierarchy:

**`ProviderCapabilities`** -- provider-level summary:

| Field | Type | Description |
|-------|------|-------------|
| `provider_name` | `str` | Registry key (e.g. `"openai"`) |
| `models` | `tuple[ModelCapabilities, ...]` | Per-model capability details |
| `supports_background` | `bool` | Any model supports background control |
| `supports_negative_prompt` | `bool` | Any model supports negative prompts |
| `discovered_at` | `float` | Unix timestamp of discovery completion |
| `degraded` | `bool` | `True` if discovery failed (empty model list) |

**`ModelCapabilities`** -- per-model detail:

| Field | Type | Description |
|-------|------|-------------|
| `model_id` | `str` | Model identifier (e.g. `"gpt-image-1"`) |
| `display_name` | `str` | Human-readable name |
| `can_generate` | `bool` | Supports text-to-image generation |
| `can_edit` | `bool` | Supports image editing (future) |
| `supports_mask` | `bool` | Supports inpainting masks (future) |
| `supported_aspect_ratios` | `tuple[str, ...]` | e.g. `("1:1", "16:9")` |
| `supported_qualities` | `tuple[str, ...]` | e.g. `("standard", "hd")` |
| `supported_formats` | `tuple[str, ...]` | e.g. `("png", "jpeg", "webp")` |
| `supports_negative_prompt` | `bool` | Supports negative prompt parameter |
| `supports_background` | `bool` | Supports background transparency |
| `max_resolution` | `int \| None` | Max dimension in pixels |
| `default_steps` | `int \| None` | Default inference steps (A1111) |
| `default_cfg` | `float \| None` | Default CFG scale (A1111) |

Both dataclasses are frozen (immutable after construction). Fields like
`can_edit` and `supports_mask` are defined now but not yet used -- they
establish the schema for future image editing support.

### Protocol Extension

`ImageProvider` gains one new method:

```python
async def discover_capabilities(self) -> ProviderCapabilities: ...
```

This is a protocol method, not an abstract method -- providers that don't
implement it will fail at registration time if capability discovery is
attempted (duck typing enforcement via `hasattr` check in `ImageService`).

### Discovery Timing and Caching

- **When:** Called during server lifespan, after provider construction and
  registration, via `ImageService.discover_all_capabilities()`.
- **Caching:** Capabilities are immutable for the server lifetime. No refresh
  mechanism -- restart the server to re-discover.
- **Storage:** `ImageService._capabilities: dict[str, ProviderCapabilities]`
  keyed by provider name.

### Failure Mode

If a provider's `discover_capabilities()` raises any exception:

1. Log a warning with the exception details
2. Register the provider with `degraded=True` and an empty model list
3. Server startup continues normally
4. The degraded provider remains available for generation -- only its
   capability metadata is incomplete

This ensures a transient API failure (e.g. OpenAI rate limit at startup) does
not prevent the server from starting. The provider still works for generation;
it just can't report its capabilities to clients.

### Per-Provider Introspection Strategy

| Provider | API Endpoint | Discovery Logic |
|----------|-------------|-----------------|
| OpenAI | `client.models.list()` | Filter to known image models (`gpt-image-1`, `dall-e-3`). Map each to `ModelCapabilities` using existing hardcoded knowledge of sizes, formats, qualities. |
| A1111 | `GET /sdapi/v1/sd-models` | List installed checkpoints. Detect architecture per checkpoint using keyword matching (same logic as `_resolve_preset`). Map to `ModelCapabilities` with architecture-specific defaults. |
| Placeholder | (none) | Return static capabilities: one model, `can_generate=True`, sizes from `_ASPECT_RATIO_TO_SIZE`. |

### Integration Points

- **`list_providers` tool:** Return value enriched with serialized
  `ProviderCapabilities` per provider (backward-compatible -- `available` and
  `description` fields still present).
- **`info://providers` resource:** Returns full capability data as structured
  JSON.
- **Provider selector:** Gains optional capability-aware filtering (e.g.
  deprioritize providers without `supports_background` when transparency is
  requested).

## Consequences

### Positive

- Clients can discover provider capabilities at runtime
- Auto-selector can make capability-aware routing decisions
- Degraded mode prevents startup failures from transient API issues
- Per-model granularity supports multi-model providers (OpenAI)
- Schema is extensible for future capabilities (editing, masks)

### Negative

- Adds startup latency (one API call per provider with API introspection)
- Capability data can become stale during long-running server instances
  (mitigated: restart to refresh)
- Degraded providers report incomplete capability data (acceptable: generation
  still works)

### Future Extensions

- `model` parameter on `generate_image` to target a specific discovered model
- Capability-based validation (reject unsupported aspect ratios before calling
  provider)
- Periodic capability refresh for long-running deployments
- Image editing capabilities (`can_edit`, `supports_mask`)
