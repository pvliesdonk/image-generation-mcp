# ADR-0005: Hybrid Background Tasks for Image Generation

## Status

Accepted

## Context

Image generation is inherently slow -- OpenAI takes 5-15 seconds, A1111 takes
10-60+ seconds on consumer GPUs. The current `generate_image` tool blocks until
completion with no feedback to the client.

MCP clients need either real-time progress updates (foreground) or the ability
to start generation and check back later (background). Different clients and
use cases benefit from different modes.

## Decision Drivers

- **Client flexibility** -- some clients want blocking + progress, others want
  fire-and-forget
- **Minimal complexity** -- one code path, not two divergent implementations
- **Forward compatibility** -- MCP background task protocol (SEP-1686) is
  gaining adoption
- **Zero mandatory infrastructure** -- should work out-of-the-box without Redis

## Considered Options

### Option 1: Foreground-only with progress reporting

Add `Context.report_progress()` calls but keep the tool blocking.

**Pros:** Simplest change, zero new dependencies.
**Cons:** Clients cannot do other work while waiting. 60s A1111 generations
block the entire MCP session.

### Option 2: Background-only with task polling

Add `task=True` and remove foreground support.

**Pros:** Non-blocking for all clients.
**Cons:** Forces all clients into polling mode. Clients that prefer streaming
progress lose that capability. Requires `fastmcp[tasks]` dependency.

### Option 3: Hybrid -- foreground progress + background tasks (chosen)

Add `task=True` to the decorator AND use `Context.report_progress()` in the
tool body. `report_progress()` adapts automatically to both execution modes.

**Pros:** Client chooses mode at call time. Single code path. Progress works
in both modes. In-memory Docket backend works without Redis.
**Cons:** Adds `fastmcp[tasks]` dependency.

## Decision

**Option 3: Hybrid.** The `generate_image` tool uses `task=True` on the
decorator and `Context.report_progress()` for progress updates. The client
controls execution mode:

- **Foreground** (default): Client calls normally, receives progress
  notifications, gets result when done.
- **Background**: Client calls with `task=True`, receives task ID immediately,
  polls for progress and result.

Progress stages:
1. Selecting provider (0/3)
2. Generating image (1/3)
3. Saving and processing (2/3)
4. Done (3/3)

**Critical constraint:** The tool function must contain zero conditional logic
based on execution mode. There must be no `if ctx.is_background_task:`
branching, no separate foreground vs. background return paths, and no
mode-detection code. `Context.report_progress()` handles the
foreground/background dispatch internally -- the tool is unaware of which mode
the client selected. If a future change requires mode-specific behavior, that
is a signal to revisit this ADR, not to add a conditional.

## Consequences

### Positive

- Clients choose the mode that fits their UX (streaming vs. polling)
- Single tool function serves both modes -- no code duplication
- In-memory Docket backend requires zero infrastructure beyond FastMCP
- Future: Redis backend enables persistence and horizontal scaling without
  code changes

### Negative

- Adds `fastmcp[tasks]` dependency (pulls in Docket)
- Clients that don't support MCP tasks fall back to foreground (acceptable --
  it's the default)
- Background mode returns task ID, not the image -- client must make a second
  call to retrieve result
