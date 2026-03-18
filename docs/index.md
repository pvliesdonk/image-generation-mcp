# Image Gen MCP Server

Multi-provider image generation MCP server built on FastMCP. Supports OpenAI
(gpt-image-1, dall-e-3), A1111 (Stable Diffusion WebUI), and a zero-cost
placeholder provider for testing.

## Quick start

```bash
# Install
uv sync --extra mcp --extra dev

# Start server (stdio mode, placeholder only — no API keys needed)
IMAGE_GEN_MCP_READ_ONLY=false uv run image-gen-mcp serve

# Start server (HTTP mode, with OpenAI)
IMAGE_GEN_MCP_READ_ONLY=false \
IMAGE_GEN_MCP_OPENAI_API_KEY=sk-... \
uv run image-gen-mcp serve --transport http --port 8000
```

## Design

- [Provider System Design](design/provider-system.md) — architecture, provider
  protocol, selection logic, configuration reference

## Architecture Decisions

- [ADR-0001: Multi-Provider Architecture](decisions/0001-multi-provider-architecture.md) —
  direct generation with MCP prompt guidance (no prompt distillation)
- [ADR-0002: Provider Protocol and Registry](decisions/0002-provider-protocol-and-registry.md) —
  runtime-checkable Protocol with registry pattern
- [ADR-0003: A1111 Model-Aware Presets](decisions/0003-a1111-model-aware-presets.md) —
  auto-detect SD architecture from checkpoint name
- [ADR-0004: Keyword-Based Provider Selection](decisions/0004-keyword-based-provider-selection.md) —
  word-boundary keyword matching with fallback chain

## Deployment

- [Docker](deployment/docker.md)
- [OIDC](deployment/oidc.md)

## Guides

- [Authentication](guides/authentication.md) — bearer token, OIDC, multi-auth setup
