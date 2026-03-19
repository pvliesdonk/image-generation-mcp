# Configuration

All configuration is via environment variables prefixed with `MCP_IMAGEGEN_`.

## Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_IMAGEGEN_SCRATCH_DIR` | Path | `~/.mcp-imagegen/images/` | Directory for saved generated images. Created automatically on first use. |
| `MCP_IMAGEGEN_READ_ONLY` | bool | `true` | When `true`, write-tagged tools (`generate_image`) are hidden from clients. Set to `false` to enable image generation. |
| `MCP_IMAGEGEN_DEFAULT_PROVIDER` | str | `auto` | Default provider selection. Options: `auto` (keyword-based selection), `openai`, `a1111`, `placeholder`. |

## Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_IMAGEGEN_OPENAI_API_KEY` | str | -- | OpenAI API key. Enables the OpenAI provider (gpt-image-1, dall-e-3) when set. |
| `MCP_IMAGEGEN_A1111_HOST` | str | -- | Automatic1111 WebUI base URL (e.g. `http://localhost:7860`). Enables the A1111 provider when set. |
| `MCP_IMAGEGEN_A1111_MODEL` | str | -- | A1111 checkpoint name. Used for model-aware preset detection (SD 1.5 vs SDXL vs Lightning) and checkpoint override. |

## Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_IMAGEGEN_BEARER_TOKEN` | str | -- | Static bearer token for HTTP authentication. Enables bearer auth when set. |
| `MCP_IMAGEGEN_BASE_URL` | str | -- | Public base URL of the server for OIDC redirects (e.g. `https://mcp.example.com`). Include subpath prefix if applicable. |
| `MCP_IMAGEGEN_OIDC_CONFIG_URL` | str | -- | OIDC discovery endpoint URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). |
| `MCP_IMAGEGEN_OIDC_CLIENT_ID` | str | -- | OIDC client ID registered with your identity provider. |
| `MCP_IMAGEGEN_OIDC_CLIENT_SECRET` | str | -- | OIDC client secret. |
| `MCP_IMAGEGEN_OIDC_JWT_SIGNING_KEY` | str | ephemeral | JWT signing key for session tokens. **Required on Linux/Docker** -- the default ephemeral key invalidates all tokens on restart. Generate with `openssl rand -hex 32`. |
| `MCP_IMAGEGEN_OIDC_AUDIENCE` | str | -- | Expected JWT audience claim. Leave unset if your provider does not set one. |
| `MCP_IMAGEGEN_OIDC_REQUIRED_SCOPES` | str | `openid` | Comma-separated required OIDC scopes. |
| `MCP_IMAGEGEN_OIDC_VERIFY_ACCESS_TOKEN` | bool | `false` | Set `true` to verify the upstream access token as JWT instead of the id token. Only needed when your provider issues JWT access tokens and you require audience-claim validation. |

!!! note
    All four OIDC variables (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) must be set to enable OIDC. If any is missing, OIDC is disabled.

!!! warning
    Authentication only works with HTTP transport (`--transport http` or `sse`). It has no effect with stdio transport.

## Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_IMAGEGEN_SERVER_NAME` | str | `mcp-imagegen` | Server name shown to MCP clients in the initialization response. |
| `MCP_IMAGEGEN_INSTRUCTIONS` | str | (dynamic) | System-level instructions injected into LLM context. Defaults to a description reflecting the read-only/read-write state. |
| `MCP_IMAGEGEN_LOG_LEVEL` | str | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `MCP_IMAGEGEN_HTTP_PATH` | str | `/mcp` | HTTP endpoint mount path for streamable-HTTP transport. |

## Example configurations

### Minimal (placeholder only)

```bash
MCP_IMAGEGEN_READ_ONLY=false
```

### OpenAI

```bash
MCP_IMAGEGEN_READ_ONLY=false
MCP_IMAGEGEN_OPENAI_API_KEY=sk-...
```

### All providers

```bash
MCP_IMAGEGEN_READ_ONLY=false
MCP_IMAGEGEN_OPENAI_API_KEY=sk-...
MCP_IMAGEGEN_A1111_HOST=http://localhost:7860
MCP_IMAGEGEN_A1111_MODEL=realisticVisionV60B1_v51VAE.safetensors
```

### Production (OIDC + OpenAI)

```bash
MCP_IMAGEGEN_READ_ONLY=false
MCP_IMAGEGEN_OPENAI_API_KEY=sk-...
MCP_IMAGEGEN_BASE_URL=https://mcp.example.com
MCP_IMAGEGEN_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
MCP_IMAGEGEN_OIDC_CLIENT_ID=mcp-imagegen
MCP_IMAGEGEN_OIDC_CLIENT_SECRET=your-client-secret
MCP_IMAGEGEN_OIDC_JWT_SIGNING_KEY=your-stable-hex-key
```
