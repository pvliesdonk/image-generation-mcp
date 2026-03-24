# Configuration

All configuration is via environment variables prefixed with `IMAGE_GENERATION_MCP_`.

## Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | Path | `~/.image-generation-mcp/images/` | Directory for saved generated images. Created automatically on first use. |
| `IMAGE_GENERATION_MCP_READ_ONLY` | bool | `true` | When `true`, write-tagged tools (`generate_image`) are hidden from clients. Set to `false` to enable image generation. |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | str | `auto` | Default provider selection. Options: `auto` (keyword-based selection), `openai`, `sd_webui`, `placeholder`. |

## Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | str | -- | OpenAI API key. Enables the OpenAI provider (gpt-image-1, dall-e-3) when set. |
| `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` | str | -- | SD WebUI base URL (e.g. `http://localhost:7860`). Enables the SD WebUI provider when set. Compatible with AUTOMATIC1111, Forge, reForge, and Forge-neo. Deprecated alias: `IMAGE_GENERATION_MCP_A1111_HOST`. |
| `IMAGE_GENERATION_MCP_SD_WEBUI_MODEL` | str | -- | SD WebUI checkpoint name. Used for model-aware preset detection (SD 1.5 vs SDXL vs Lightning) and checkpoint override. Deprecated alias: `IMAGE_GENERATION_MCP_A1111_MODEL`. |

## Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_AUTH_MODE` | str | auto | OIDC auth mode: `remote` (local JWT validation) or `oidc-proxy` (DCR emulation). Auto-detected from env vars when not set — see below. |
| `IMAGE_GENERATION_MCP_BEARER_TOKEN` | str | -- | Static bearer token for HTTP authentication. Enables bearer auth when set. |
| `IMAGE_GENERATION_MCP_BASE_URL` | str | -- | Public base URL of the server (e.g. `https://mcp.example.com`). Required for OIDC and for `create_download_link` / `show_image` auto-download URLs. Also used to derive the MCP Apps widget domain (hostname extracted). Include subpath prefix if applicable. |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | str | -- | OIDC discovery endpoint URL (e.g. `https://auth.example.com/.well-known/openid-configuration`). |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | str | -- | OIDC client ID registered with your identity provider. Required for `oidc-proxy` mode only. |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | str | -- | OIDC client secret. Required for `oidc-proxy` mode only. |
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | str | ephemeral | JWT signing key for session tokens. **Required on Linux/Docker for `oidc-proxy` mode** -- the default ephemeral key invalidates all tokens on restart. Generate with `openssl rand -hex 32`. Not needed for `remote` mode. |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | str | -- | Expected JWT audience claim. Leave unset if your provider does not set one. |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | str | -- | Comma-separated required OIDC scopes. For `oidc-proxy` mode, defaults to `openid`. |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | bool | `false` | Set `true` to verify the upstream access token as JWT instead of the id token. Only applies to `oidc-proxy` mode. |

!!! note "Auth mode auto-detection"
    When `AUTH_MODE` is not set explicitly, the mode is auto-detected:

    - **`oidc-proxy`**: when all four OIDC variables (`BASE_URL`, `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) are set. Backward compatible with existing deployments.
    - **`remote`**: when `BASE_URL` + `OIDC_CONFIG_URL` are set but `CLIENT_ID`/`CLIENT_SECRET` are not. Recommended for new deployments — avoids the [OIDCProxy session lifetime issue](guides/authentication.md#known-limitations-oidc-session-lifetime).

    Set `AUTH_MODE` explicitly to override auto-detection (e.g., `AUTH_MODE=remote` even when client credentials are present).

!!! warning
    Authentication only works with HTTP transport (`--transport http` or `sse`). It has no effect with stdio transport.

## Cost Control

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_PAID_PROVIDERS` | str | `openai` | Comma-separated list of provider names that cost money. When the MCP client supports [elicitation](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/elicitation), `generate_image` asks for confirmation before using these providers. Set to empty string to disable confirmation. |

## Performance

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE` | int | `64` | Maximum number of transformed image results (resize/crop/convert) to keep in memory. Repeated requests for the same transform parameters are served from cache. Set to `0` to disable caching. |

## Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SERVER_NAME` | str | `image-generation-mcp` | Server name shown to MCP clients in the initialization response. |
| `IMAGE_GENERATION_MCP_INSTRUCTIONS` | str | (dynamic) | System-level instructions injected into LLM context. Defaults to a description reflecting the read-only/read-write state. |
| `FASTMCP_LOG_LEVEL` | str | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Controls FastMCP internals (auth, transport) directly; app loggers use `INFO` unless overridden by `--verbose`. |
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
IMAGE_GENERATION_MCP_SD_WEBUI_HOST=http://localhost:7860
IMAGE_GENERATION_MCP_SD_WEBUI_MODEL=realisticVisionV60B1_v51VAE.safetensors
```

### Production — remote mode (recommended)

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
```

### Production — oidc-proxy mode (DCR emulation)

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-...
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
IMAGE_GENERATION_MCP_OIDC_CLIENT_ID=image-generation-mcp
IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET=your-client-secret
IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY=your-stable-hex-key
```
