# Configuration

All configuration is via environment variables prefixed with `IMAGE_GENERATION_MCP_`.

## Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | Path | `~/.image-generation-mcp/images/` | Directory for saved generated images. Created automatically on first use. |
| `IMAGE_GENERATION_MCP_READ_ONLY` | bool | `true` | When `true`, write-tagged tools (`generate_image`) are hidden from clients. Set to `false` to enable image generation. |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | str | `auto` | Default provider selection. Options: `auto` (keyword-based selection), `openai`, `a1111`, `placeholder`. |

## Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | str | -- | OpenAI API key. Enables the OpenAI provider (gpt-image-1, dall-e-3) when set. |
| `IMAGE_GENERATION_MCP_A1111_HOST` | str | -- | Automatic1111 WebUI base URL (e.g. `http://localhost:7860`). Enables the A1111 provider when set. |
| `IMAGE_GENERATION_MCP_A1111_MODEL` | str | -- | A1111 checkpoint name. Used for model-aware preset detection (SD 1.5 vs SDXL vs Lightning) and checkpoint override. |

## Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_BEARER_TOKEN` | str | -- | Static bearer token for HTTP authentication. Enables bearer auth when set. |
| `IMAGE_GENERATION_MCP_BASE_URL` | str | -- | Public base URL of the server (e.g. `https://mcp.example.com`). Required for OIDC redirects and for constructing artifact download links via `create_download_link`. Include subpath prefix if applicable. |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | str | -- | OIDC discovery endpoint URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | str | -- | OIDC client ID registered with your identity provider. |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | str | -- | OIDC client secret. |
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | str | ephemeral | JWT signing key for session tokens. **Required on Linux/Docker** -- the default ephemeral key invalidates all tokens on restart. Generate with `openssl rand -hex 32`. |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | str | -- | Expected JWT audience claim. Leave unset if your provider does not set one. |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | str | `openid` | Comma-separated required OIDC scopes. |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | bool | `false` | Set `true` to verify the upstream access token as JWT instead of the id token. Only needed when your provider issues JWT access tokens and you require audience-claim validation. |

!!! note
    All four OIDC variables (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) must be set to enable OIDC. If any is missing, OIDC is disabled.

!!! warning
    Authentication only works with HTTP transport (`--transport http` or `sse`). It has no effect with stdio transport.

## Performance

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE` | int | `64` | Maximum number of transformed image results (resize/crop/convert) to keep in memory. Repeated requests for the same transform parameters are served from cache. Set to `0` to disable caching. |

## Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SERVER_NAME` | str | `image-generation-mcp` | Server name shown to MCP clients in the initialization response. |
| `IMAGE_GENERATION_MCP_INSTRUCTIONS` | str | (dynamic) | System-level instructions injected into LLM context. Defaults to a description reflecting the read-only/read-write state. |
| `IMAGE_GENERATION_MCP_LOG_LEVEL` | str | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `IMAGE_GENERATION_MCP_HTTP_PATH` | str | `/mcp` | HTTP endpoint mount path for streamable-HTTP transport. |

## Example configurations

### Minimal (placeholder only)

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
```

### OpenAI

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
```

### All providers

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
IMAGE_GENERATION_MCP_A1111_HOST=http://localhost:7860
IMAGE_GENERATION_MCP_A1111_MODEL=realisticVisionV60B1_v51VAE.safetensors
```

### Production (OIDC + OpenAI)

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
IMAGE_GENERATION_MCP_OIDC_CLIENT_ID=image-generation-mcp
IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET=your-client-secret
IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY=your-stable-hex-key
```
