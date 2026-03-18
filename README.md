# image-gen-mcp

> **This is a template repository.** Click "Use this template" to create your own MCP server, then follow [TEMPLATE.md](TEMPLATE.md) to customise it.

A production-ready [FastMCP](https://gofastmcp.com) server scaffold with batteries included:

- **Auth** — bearer token, OIDC, and multi-auth (both simultaneously)
- **Read-only mode** — write tools hidden via `mcp.disable(tags={"write"})`
- **CI** — test matrix (Python 3.11–3.14), ruff, mypy, pip-audit, gitleaks, CodeQL
- **Release pipeline** — semantic-release → PyPI + Docker (GHCR), SBOM attestation
- **Docker** — multi-arch, `gosu` privilege dropping, configurable PUID/PGID
- **Docs** — MkDocs Material + GitHub Pages

## Quick start

```bash
# Install and run (stdio transport)
pip install image-gen-mcp[mcp]
image-gen-mcp serve

# Or with HTTP transport
image-gen-mcp serve --transport http --port 8000
```

## Configuration

All configuration is via environment variables prefixed with `IMAGE_GEN_MCP_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GEN_MCP_READ_ONLY` | `true` | Disable write tools |
| `IMAGE_GEN_MCP_BEARER_TOKEN` | — | Enable bearer token auth |
| `IMAGE_GEN_MCP_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `IMAGE_GEN_MCP_SERVER_NAME` | `image-gen-mcp` | Server name shown to clients |
| `IMAGE_GEN_MCP_INSTRUCTIONS` | (dynamic) | System instructions for LLM context |

## Authentication

The server supports four auth modes:

1. **Multi-auth** — both bearer token and OIDC configured; either credential accepted
2. **Bearer token** — set `IMAGE_GEN_MCP_BEARER_TOKEN` to a secret string
3. **OIDC** — full OAuth 2.1 flow via `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `BASE_URL`
4. **No auth** — server accepts all connections (default)

**Auth requires `--transport http` (or `sse`).** It has no effect with `--transport stdio`.

See [Authentication guide](docs/guides/authentication.md) for setup details.

## Docker

```bash
docker compose up -d
```

See [Docker deployment](docs/deployment/docker.md) for volumes, UID/GID, and Traefik setup.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## Using this template

See [TEMPLATE.md](TEMPLATE.md) for the step-by-step customisation guide, including the `rename.sh` bootstrap script.

## License

MIT
