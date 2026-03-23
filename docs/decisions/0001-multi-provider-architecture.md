# ADR-0001: Multi-Provider Image Generation Architecture

## Status

Accepted

## Context

We need an MCP server that generates images via multiple backends (OpenAI,
Stable Diffusion WebUI, and more in the future). The server must:

- Support providers with fundamentally different APIs (REST, SDK, workflow-based)
- Allow providers to be conditionally registered based on available credentials
- Select the best provider automatically based on prompt content
- Return images as both MCP `ImageContent` (base64) and saved files

### Prior Art

- **questfoundry** — Python image generation with `ImageBrief` + `PromptDistiller`
  pipeline. Providers generate images but prompts are distilled by an LLM first.
- **claude-skills** (TypeScript) — Multi-provider image generation as a Claude
  skill with keyword-based provider selection.

## Decision Drivers

- **Simplicity** — MCP clients (Claude) are capable of writing good prompts
  directly; an intermediate distillation step adds complexity without clear value.
- **Extensibility** — New providers should be addable without modifying core code.
- **Conditional availability** — Providers should only be active when their
  credentials/services are configured.
- **Testability** — Each provider should be independently testable.

## Considered Options

### Option 1: Port questfoundry's ImageBrief + PromptDistiller

Port the full pipeline: user intent → ImageBrief → PromptDistiller → provider.
The distiller rewrites prompts for each provider's optimal format.

**Pros:** Provider-optimized prompts, consistent quality.
**Cons:** Requires an LLM call per generation (adds latency and cost), complex
dependency on LangChain/LiteLLM, the MCP client is already an LLM that can
write good prompts if guided.

### Option 2: Direct generation with MCP prompt guidance (chosen)

Remove the distillation pipeline entirely. Providers receive prompts directly.
MCP prompts (`select_provider`, `sd_prompt_guide`) guide the MCP client on
writing provider-optimized prompts.

**Pros:** Simpler architecture, lower latency, no extra LLM cost, leverages
the MCP client's native capabilities.
**Cons:** Relies on the MCP client reading and following prompt guidance.

### Option 3: Client-side prompt rewriting

Expose a `rewrite_prompt` tool that reformats a natural language prompt into
SD-optimized tags. Client calls it before `generate_image`.

**Pros:** Explicit prompt optimization step, client controls when to use it.
**Cons:** Extra round-trip, still needs an LLM or complex rules, adds tool
complexity.

## Decision

**Option 2: Direct generation with MCP prompt guidance.**

The MCP client (Claude) is already a capable LLM. Rather than adding an LLM
distillation layer, we provide MCP prompts that guide the client on:
- When to use each provider (selection criteria)
- How to write SD-optimized prompts (CLIP tag format, BREAK syntax, negative prompts)

This removes the questfoundry dependency on LangChain/LiteLLM for prompt
distillation and eliminates per-generation LLM calls.

## Consequences

### Positive

- Simpler architecture — no LangChain/LiteLLM dependency for prompt processing
- Lower latency — no intermediate LLM call before image generation
- Lower cost — no extra API calls for prompt distillation
- Easier testing — providers are pure HTTP/SDK clients, no mocked LLM chains

### Negative

- Prompt quality depends on the MCP client reading and following the guidance prompts
- SD-specific tag formatting may be suboptimal compared to a dedicated distiller
- Clients that don't support MCP prompts won't benefit from the guidance

### Risks

- If prompt quality proves insufficient, we can add a `rewrite_prompt` tool
  (Option 3) as a non-breaking enhancement later.
