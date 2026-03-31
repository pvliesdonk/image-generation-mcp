# ADR-0005: Fire-and-Forget Image Generation

## Status

Accepted — supersedes the original hybrid background task decision.

## Context

Image generation is inherently slow -- OpenAI takes 5-15 seconds, SD WebUI takes
10-60+ seconds on consumer GPUs. MCP clients enforce hard tool-execution timeouts
that no server-side mechanism can extend:

| Client | Tool timeout | Progress resets it? |
|--------|-------------|---------------------|
| Claude.ai | ~45s hard | No |
| Claude Desktop | 60s hard | No |
| Claude Code | Configurable, `resetTimeoutOnProgress=True` | **Yes** |
| Claude Android | ~45s hard tool + ~25s SSE idle | No / Yes (keepalive) |

The original Option 3 (hybrid foreground progress + background tasks) was
implemented but live testing on 2026-03-23 confirmed that progress notifications
do not reset the timeout on any client except Claude Code. Both SD WebUI
(Flux/60-120s) and OpenAI gpt-image-1 (consistently >45s) time out every time
on Claude.ai, Claude Desktop, and Claude Android.

## Decision Drivers

- **Universal compatibility** -- must work on all MCP clients without configuration
- **Sub-second tool response** -- tool must return before the shortest client timeout
- **Zero mandatory infrastructure** -- no Redis, no message queue
- **Polling via existing tools** -- clients poll with `show_image`, no new protocol

## Decision

**Fire-and-forget with polling.** The `generate_image` tool:

1. Validates inputs and resolves the provider (synchronous, <1s)
2. Pre-allocates an `image_id` and registers a `PendingGeneration`
3. Spawns the provider call as a background `asyncio.create_task`
4. Returns immediately with `{"status": "generating", "image_id": "..."}`

The client then polls with `show_image(uri="image://{image_id}/view")`:

- `{"status": "generating", "progress": 0.3, ...}` -- still in progress
- `{"status": "failed", "error": "..."}` -- generation failed
- Image thumbnail + metadata -- generation complete (normal `show_image` response)

### Key properties

- **All providers use the same path** -- no provider-specific branching
- **The tool function returns in <1s** -- well within all client timeouts
- **Background tasks are in-process `asyncio.Task`s** -- no external infrastructure
- **`image://list` includes pending generations** -- clients can discover in-progress work
- **Cleanup is automatic** -- completed/failed entries expire after TTL (10 min)

### Service layer API

```python
service.allocate_image_id() -> str           # pre-allocate before spawning
service.register_pending(image_id, ...)      # track the background task
service.get_pending(image_id)                # poll status (None if unknown)
service.complete_pending(image_id)           # mark done after register_image
service.fail_pending(image_id, error)        # capture background failures
service.cleanup_pending(image_id)            # remove after client reads it
service.register_image(..., image_id=...)    # accepts pre-allocated ID
```

### Synchronous callers

`service.generate()` remains a normal async method that blocks until the image
is ready. Only the MCP tool layer uses fire-and-forget. Direct callers of the
service (tests, CLI) get synchronous behavior unchanged.

## Consequences

### Positive

- Works on every MCP client without timeout issues
- Single code path for all providers
- `show_image` doubles as both display tool and polling endpoint -- no new tools
- Progress info (from SD WebUI `/sdapi/v1/progress`) can be stored in
  `PendingGeneration` and returned via `show_image` polling
- Background failures are captured and surfaced, not silently lost

### Negative

- Client must call `show_image` at least once to see the result (not automatic)
- Two tool calls minimum (generate + show) vs. one in the old foreground mode
- In-process tasks are lost on server restart (acceptable -- no persistence needed
  for ephemeral image generation)
- The `task=True` decorator is retained for forward compatibility but the tool
  no longer blocks long enough for MCP background task mode to be useful
