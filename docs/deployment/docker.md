# Docker Deployment

## Quick start

```bash
docker compose up -d
```

The server listens on port 8000 with HTTP transport by default.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GENERATION_MCP_READ_ONLY` | `true` | Disable write tools |
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | -- | OpenAI API key; enables OpenAI provider |
| `IMAGE_GENERATION_MCP_A1111_HOST` | -- | A1111 WebUI URL; enables A1111 provider |
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | `~/.image-generation-mcp/images/` | Image storage directory |
| `IMAGE_GENERATION_MCP_BEARER_TOKEN` | -- | Enable bearer token auth |
| `FASTMCP_LOG_LEVEL` | `INFO` | Log level for FastMCP internals; app loggers use `INFO` unless `-v` is used |
| `IMAGE_GENERATION_MCP_SERVER_NAME` | `image-generation-mcp` | Server name shown to clients |

See [Configuration](../configuration.md) for the full environment variable reference.

For OIDC auth variables, see [Authentication](../guides/authentication.md).

## Volumes

| Path | Purpose |
|------|---------|
| `/data/service` | Image scratch directory (bind-mount or named volume) |
| `/data/state` | State files (FastMCP OIDC state, etc.) |

## UID/GID

Set `PUID` and `PGID` in your `.env` file to match the owner of bind-mounted
directories (default 1000/1000).
