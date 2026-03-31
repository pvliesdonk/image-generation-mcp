# ADR-0005: Inline-Wait Image Generation with Background Fallback

## Status

Accepted — supersedes the original fire-and-forget decision.

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

The previous fire-and-forget approach returned immediately and required the
LLM to poll via `show_image`.  In practice this created multiple visible
tool-call cards in the UI (e.g. "Generating (22s)", "Generating (25s)")
which was disruptive to the user experience.

## Decision Drivers

- **Minimal visible tool calls** -- one tool call should produce the result
- **Universal compatibility** -- must work on all MCP clients without configuration
- **Respect client timeouts** -- must not exceed the ~45s hard limit
- **Zero mandatory infrastructure** -- no Redis, no message queue

## Decision

**Inline wait with background fallback.** The `generate_image` tool:

1. Validates inputs and resolves the provider (synchronous, <1s)
2. Pre-allocates an `image_id` and registers a `PendingGeneration`
3. Spawns the provider call as a background `asyncio.create_task`
4. **Waits up to 40 seconds** for the task to complete (using
   `asyncio.wait_for(asyncio.shield(task), timeout=40)`)
5. If the task completes in time, returns the **completed image inline**
   (thumbnail + metadata) in a single tool response
6. If the task times out, returns `{"status": "generating"}` and the
   background task continues -- client can poll via `show_image`

### Key properties

- **Most providers complete within 40s** -- OpenAI (5-15s), placeholder
  (instant), SD WebUI standard quality (<30s) all return inline
- **Only very slow generations fall back to polling** -- HD SD WebUI
  with complex prompts may exceed 40s
- **Single tool call for the common case** -- no visible polling cards
- **Background tasks are in-process `asyncio.Task`s** -- no external
  infrastructure
- **`asyncio.shield` prevents task cancellation on timeout** -- the task
  continues running even when the wait times out
- **`image://list` includes pending generations** -- clients can discover
  in-progress work
- **Cleanup is automatic** -- completed/failed entries expire after TTL
  (10 min)

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
is ready. Only the MCP tool layer adds the timeout wrapper. Direct callers of
the service (tests, CLI) get synchronous behavior unchanged.

## Consequences

### Positive

- One tool call = one result for the vast majority of generations
- No visible polling cards cluttering the conversation UI
- Works on every MCP client without timeout issues (40s < 45s limit)
- Errors from fast providers surface directly in the tool response
- Progress info (from SD WebUI `/sdapi/v1/progress`) is still stored in
  `PendingGeneration` for the rare polling fallback case

### Negative

- For very slow generations (>40s), client must still call `show_image`
  to retrieve the result (two tool calls minimum)
- In-process tasks are lost on server restart (acceptable -- no persistence
  needed for ephemeral image generation)
- The `task=True` decorator is retained for forward compatibility but the
  tool's inline wait handles most cases before MCP task mode activates
