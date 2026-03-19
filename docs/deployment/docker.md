# Docker Deployment

## Quick start

```bash
docker compose up -d
```

The server listens on port 8000 with HTTP transport by default.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_IMAGEGEN_READ_ONLY` | `true` | Disable write tools |
| `MCP_IMAGEGEN_OPENAI_API_KEY` | -- | OpenAI API key; enables OpenAI provider |
| `MCP_IMAGEGEN_A1111_HOST` | -- | A1111 WebUI URL; enables A1111 provider |
| `MCP_IMAGEGEN_SCRATCH_DIR` | `~/.mcp-imagegen/images/` | Image storage directory |
| `MCP_IMAGEGEN_BEARER_TOKEN` | -- | Enable bearer token auth |
| `MCP_IMAGEGEN_LOG_LEVEL` | `INFO` | Log level |
| `MCP_IMAGEGEN_SERVER_NAME` | `mcp-imagegen` | Server name shown to clients |

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
