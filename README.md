<!-- mcp-name: io.github.pvliesdonk/image-generation-mcp -->
# image-generation-mcp

[![CI](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pvliesdonk/image-generation-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/image-generation-mcp)
[![PyPI](https://img.shields.io/pypi/v/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/image-generation-mcp/)
[![llms.txt](https://img.shields.io/badge/llms-llms.txt-blue)](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)

Multi-provider image generation [MCP](https://modelcontextprotocol.io) server built on [FastMCP](https://gofastmcp.com). Generate images from Claude Desktop, Claude Code, or any MCP client using OpenAI, Stable Diffusion (A1111 WebUI), or a zero-cost placeholder provider.

[Documentation](https://pvliesdonk.github.io/image-generation-mcp/) | [PyPI](https://pypi.org/project/image-generation-mcp/) | [Docker](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)

## Features

- **Multi-provider architecture** -- OpenAI (gpt-image-1, dall-e-3), A1111 (Stable Diffusion WebUI), and a zero-cost placeholder provider
- **Keyword-based auto-selection** -- automatically picks the best provider for your prompt (text/logo -> OpenAI, photorealism/anime -> A1111, test/draft -> placeholder)
- **MCP tools** -- `generate_image` (with background task support) and `list_providers`
- **MCP resources** -- `info://providers`, `image://{id}/view` with CDN-style transforms (format, resize, crop), `image://{id}/metadata`, `image://list`
- **MCP prompts** -- `select_provider` (provider selection guidance) and `sd_prompt_guide` (CLIP tag format, negative prompts, BREAK syntax)
- **Image asset model** -- content-addressed image registry with sidecar JSON metadata, thumbnail previews, and resource URI-based transforms
- **Background tasks** -- hybrid foreground (streaming progress) and background (polling) execution via `task=True`
- **Read-only mode** -- write tools hidden via `mcp.disable(tags={"write"})` for safe read-only deployments
- **Authentication** -- bearer token, OIDC (OAuth 2.1), and multi-auth (both simultaneously)
- **Docker** -- multi-arch image with `gosu` privilege dropping, configurable PUID/PGID
- **CI/CD** -- test matrix (Python 3.11-3.14), ruff, mypy, pip-audit, gitleaks, CodeQL, semantic-release

## Installation

### From PyPI

```bash
# Core + MCP server
pip install image-generation-mcp[mcp]

# With OpenAI provider
pip install image-generation-mcp[all]
```

Available extras:

| Extra | Includes |
|-------|----------|
| `mcp` | `fastmcp[tasks]>=3.0,<4` |
| `openai` | `openai>=1.0` |
| `all` | `fastmcp[tasks]>=3.0,<4` + `openai>=1.0` |
| `dev` | All above + pytest, ruff, mypy, pip-audit |
| `docs` | mkdocs-material, mkdocstrings, mkdocs-llmstxt |

### From source

```bash
git clone https://github.com/pvliesdonk/image-generation-mcp.git
cd image-generation-mcp
uv sync --extra all --extra dev
```

### Docker

```bash
docker pull ghcr.io/pvliesdonk/image-generation-mcp:latest
```

### Linux packages (.deb / .rpm)

Native packages with a hardened systemd service are available from [GitHub Releases](https://github.com/pvliesdonk/image-generation-mcp/releases). See the [systemd deployment guide](https://pvliesdonk.github.io/image-generation-mcp/deployment/systemd/) for details.

## Quick start

### As MCP server (stdio)

```bash
# Placeholder only -- no API keys needed
IMAGE_GENERATION_MCP_READ_ONLY=false image-generation-mcp serve

# Generate your first image -- ask Claude or call via MCP client:
#   generate_image(prompt="a sunset over the ocean", provider="placeholder")

# With OpenAI
IMAGE_GENERATION_MCP_READ_ONLY=false \
IMAGE_GENERATION_MCP_OPENAI_API_KEY=sk-... \
image-generation-mcp serve
```

### As MCP server (HTTP)

```bash
IMAGE_GENERATION_MCP_READ_ONLY=false \
image-generation-mcp serve --transport http --port 8000
```

### With Docker Compose

```bash
docker compose up -d
```

See [Docker deployment](https://pvliesdonk.github.io/image-generation-mcp/deployment/docker/) for volumes, UID/GID, and Traefik setup.

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false",
        "IMAGE_GENERATION_MCP_OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-generation-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GENERATION_MCP_READ_ONLY": "false"
      }
    }
  }
}
```

## Configuration

All environment variables use the `IMAGE_GENERATION_MCP_` prefix.

### Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | Path | `~/.image-generation-mcp/images/` | Directory for saved generated images |
| `IMAGE_GENERATION_MCP_READ_ONLY` | bool | `true` | Hide write-tagged tools (`generate_image`) |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | str | `auto` | Default provider: `auto`, `openai`, `a1111`, `placeholder` |

### Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | str | -- | OpenAI API key; enables OpenAI provider when set |
| `IMAGE_GENERATION_MCP_A1111_HOST` | str | -- | A1111 WebUI URL (e.g. `http://localhost:7860`); enables A1111 provider when set |
| `IMAGE_GENERATION_MCP_A1111_MODEL` | str | -- | A1111 checkpoint name for preset detection and override |

### Authentication

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_BEARER_TOKEN` | str | -- | Static bearer token; enables bearer auth when set |
| `IMAGE_GENERATION_MCP_BASE_URL` | str | -- | Public base URL for OIDC and artifact download links (e.g. `https://mcp.example.com`) |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | str | -- | OIDC discovery endpoint URL |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | str | -- | OIDC client ID |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | str | -- | OIDC client secret |
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | str | ephemeral | JWT signing key; **required on Linux/Docker** |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | str | -- | Expected JWT audience claim |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | str | `openid` | Comma-separated required scopes |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | bool | `false` | Verify access token as JWT instead of id token |

### Performance

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE` | int | `64` | Max cached transforms. Set to `0` to disable caching. |

### Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SERVER_NAME` | str | `image-generation-mcp` | Server name shown to MCP clients |
| `IMAGE_GENERATION_MCP_INSTRUCTIONS` | str | (dynamic) | System instructions for LLM context |
| `FASTMCP_LOG_LEVEL` | str | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` (controls FastMCP internals; use `-v` to set app loggers to DEBUG) |
| `IMAGE_GENERATION_MCP_HTTP_PATH` | str | `/mcp` | HTTP endpoint mount path |

## CLI reference

```
image-generation-mcp serve [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--transport` | `stdio` | MCP transport: `stdio`, `sse`, or `http` (streamable-http) |
| `--host` | `0.0.0.0` | Host to bind to (HTTP transport only) |
| `--port` | `8000` | Port to listen on (HTTP transport only) |
| `--path` | `/mcp` | HTTP endpoint mount path (HTTP transport only) |
| `-v`, `--verbose` | -- | Enable debug logging |

## MCP tools

| Tool | Tags | Task | Parameters | Description |
|------|------|------|------------|-------------|
| `generate_image` | `write` | `task=True` | `prompt` (str), `provider` (str, default `"auto"`), `negative_prompt` (str, optional), `aspect_ratio` (str, default `"1:1"`), `quality` (str, default `"standard"`) | Generate an image, returns thumbnail preview + resource URIs |
| `list_providers` | -- | -- | *(none)* | List available providers with availability info |

`generate_image` returns a thumbnail (~256px WebP) as `ImageContent` plus JSON metadata as `TextContent` with `image_id`, `original_uri`, `resource_template`, sizes, provider, and file path.

Supported aspect ratios: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`.
Supported quality levels: `standard`, `hd`.

## MCP resources

| URI | MIME Type | Description |
|-----|-----------|-------------|
| `info://providers` | `application/json` | Provider capabilities and supported features |
| `image://{id}/view{?format,width,height,quality}` | varies | Image with optional transforms (format conversion, resize, crop) |
| `image://{id}/metadata` | `application/json` | Sidecar JSON with generation provenance |
| `image://list` | `application/json` | All registered images |

The `image://{id}/view` resource template supports CDN-style transforms:

- No parameters -- original bytes unchanged
- `format` -- convert to `png`, `webp`, or `jpeg`
- `width` + `height` -- center-crop to exact dimensions
- `width` only or `height` only -- proportional resize
- `quality` -- compression quality for lossy formats (default 90)

## MCP prompts

| Prompt | Parameters | Description |
|--------|------------|-------------|
| `select_provider` | *(none)* | Provider selection guidance -- strengths, use cases, and selection rules for each provider |
| `sd_prompt_guide` | *(none)* | Stable Diffusion prompt writing guide -- CLIP tag format, quality tags, negative prompts, BREAK syntax, aspect ratios |

## Providers

| Provider | Best for | Requires |
|----------|----------|----------|
| **OpenAI** | Text, logos, typography, general-purpose | `IMAGE_GENERATION_MCP_OPENAI_API_KEY` |
| **A1111** | Photorealism, portraits, anime, artistic styles | Running A1111 WebUI + `IMAGE_GENERATION_MCP_A1111_HOST` |
| **Placeholder** | Testing, drafts, CI | Nothing (always available) |

### OpenAI

Best for text rendering, logos, typography, and general-purpose generation.

- **Models:** `gpt-image-1` (default), `dall-e-3`
- **Formats:** PNG (all models), JPEG and WebP (`gpt-image-1` only)
- **Quality levels:** `standard` (mapped to `high` for gpt-image-1), `hd` (mapped to `high`)
- **Negative prompt:** Appended as `"Avoid: {negative_prompt}"` to the prompt
- **Requires:** `IMAGE_GENERATION_MCP_OPENAI_API_KEY`

### A1111 (Stable Diffusion WebUI)

Best for photorealism, portraits, anime, and artistic styles.

- **API:** HTTP POST to `/sdapi/v1/txt2img`
- **Model presets:** Auto-detected from checkpoint name:
  - **SD 1.5** (default): 768px base, 30 steps, CFG 7.0, DPM++ 2M sampler, Karras scheduler
  - **SDXL**: 1024px base, 35 steps, CFG 7.5, DPM++ 2M sampler, Karras scheduler
  - **SDXL Lightning/Turbo**: 1024px base, 6 steps, CFG 2.0, DPM++ SDE sampler, Karras scheduler
- **Negative prompt:** Native support via `negative_prompt` field
- **Checkpoint override:** Specify `model` to override `sd_model_checkpoint`
- **Timeout:** 180s (SDXL at high res on consumer GPUs)
- **Requires:** `IMAGE_GENERATION_MCP_A1111_HOST`

### Placeholder

Zero-cost solid-color PNG generation for testing and drafts.

- **No dependencies:** Pure Python PNG encoder (zlib + struct)
- **Color:** Deterministic from MD5 hash of prompt
- **Always available** -- no API key or service needed

## Authentication

The server supports four auth modes:

1. **Multi-auth** -- both bearer token and OIDC configured; either credential accepted
2. **Bearer token** -- set `IMAGE_GENERATION_MCP_BEARER_TOKEN`
3. **OIDC** -- full OAuth 2.1 flow via OIDC environment variables
4. **No auth** -- default; server accepts all connections

Auth requires `--transport http` (or `sse`). It has no effect with `--transport stdio`.

See [Authentication guide](https://pvliesdonk.github.io/image-generation-mcp/guides/authentication/) for setup details.

## Development

```bash
git clone https://github.com/pvliesdonk/image-generation-mcp.git
cd image-generation-mcp
uv sync --extra all --extra dev
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

## License

MIT
