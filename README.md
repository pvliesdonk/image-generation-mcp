<!-- mcp-name: io.github.pvliesdonk/image-generation-mcp -->
# image-generation-mcp

<<<<<<< before updating
[![CI](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pvliesdonk/image-generation-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/image-generation-mcp)
[![PyPI](https://img.shields.io/pypi/v/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/image-generation-mcp/)
[![llms.txt](https://img.shields.io/badge/llms-llms.txt-blue)](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)

Multi-provider image generation [MCP](https://modelcontextprotocol.io) server built on [FastMCP](https://gofastmcp.com). Generate images from Claude Desktop, Claude Code, or any MCP client using OpenAI, Stable Diffusion (SD WebUI), or a zero-cost placeholder provider.

[Documentation](https://pvliesdonk.github.io/image-generation-mcp/) | [PyPI](https://pypi.org/project/image-generation-mcp/) | [Docker](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)

## Features

- **Multi-provider architecture** -- OpenAI (gpt-image-1, dall-e-3), SD WebUI (Stable Diffusion WebUI, compatible with AUTOMATIC1111/Forge/reForge), and a zero-cost placeholder provider
- **Keyword-based auto-selection** -- automatically picks the best provider for your prompt (text/logo -> OpenAI, photorealism/anime -> SD WebUI, test/draft -> placeholder)
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
=======
[![CI](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/pvliesdonk/image-generation-mcp/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/image-generation-mcp) [![PyPI](https://img.shields.io/pypi/v/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/) [![Python](https://img.shields.io/pypi/pyversions/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/) [![License](https://img.shields.io/github/license/pvliesdonk/image-generation-mcp)](LICENSE) [![Docker](https://img.shields.io/github/v/release/pvliesdonk/image-generation-mcp?label=ghcr.io&logo=docker)](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp) [![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/image-generation-mcp/) [![llms.txt](https://img.shields.io/badge/llms.txt-available-brightgreen)](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)

MCP server for AI image generation via OpenAI, Google GenAI, or Stable Diffusion WebUI
>>>>>>> after updating

**[Documentation](https://pvliesdonk.github.io/image-generation-mcp/)** | **[PyPI](https://pypi.org/project/image-generation-mcp/)** | **[Docker](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)**

## Features

<!-- DOMAIN-START -->
<!-- Replace with 3-7 bullets describing what this MCP server does. Kept across copier update. -->

- **[Capability 1]** — one-sentence description of a user-visible feature.
- **[Capability 2]** — one-sentence description of another capability.
- **MCP tools** — N LLM-visible tools exposed; see `src/image_generation_mcp/tools.py`.
- **MCP resources** — M resources exposing domain state; see `src/image_generation_mcp/resources.py`.
- **MCP prompts** — K prompt templates; see `src/image_generation_mcp/prompts.py`.
<!-- DOMAIN-END -->

## What you can do with it

<!-- DOMAIN-START -->
<!-- Replace with 3-5 concrete "you can ask Claude to X" examples. Kept across copier update. -->

With this server mounted in an MCP client (Claude, etc.), you can:

- **[Task 1]** — "[example user request]." Composes tools `[tool_a]` + `[tool_b]`.
- **[Task 2]** — "[another example request]." Uses resource `[resource_x]`.
- **[Task 3]** — "[third example]."

Short, concrete prompts beat abstract feature lists — replace the
`[Task N]` placeholders with prompts that actually work against your
server's tool surface.
<!-- DOMAIN-END -->

<!-- ===== TEMPLATE-OWNED SECTIONS BELOW — DO NOT EDIT; CHANGES WILL BE OVERWRITTEN ON COPIER UPDATE ===== -->

## Installation

### From PyPI

### As MCP server (stdio)

```bash
<<<<<<< before updating
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
=======
pip install image-generation-mcp
>>>>>>> after updating
```

If you add optional extras via the `PROJECT-EXTRAS-START` / `PROJECT-EXTRAS-END` sentinels in `pyproject.toml`, document them below:

<!-- DOMAIN-START -->
<!-- List optional extras and their purpose here (e.g. `pip install image-generation-mcp[embeddings]`). Kept across copier update. -->
<!-- DOMAIN-END -->

### From source

```bash
git clone https://github.com/pvliesdonk/image-generation-mcp.git
cd image-generation-mcp
uv sync --all-extras --dev
```

### Docker

```bash
docker pull ghcr.io/pvliesdonk/image-generation-mcp:latest
```

A `compose.yml` ships at the repo root as a starting point — copy `.env.example` to `.env`, edit, and `docker compose up -d`.

### Linux packages (.deb / .rpm)

Download `.deb` or `.rpm` packages from the [GitHub Releases](https://github.com/pvliesdonk/image-generation-mcp/releases) page. Both install a hardened systemd unit; env configuration is sourced from `/etc/image-generation-mcp/env` (copy from the shipped `/etc/image-generation-mcp/env.example`).

### Claude Desktop (.mcpb bundle)

Download the `.mcpb` bundle from the [GitHub Releases](https://github.com/pvliesdonk/image-generation-mcp/releases) page and double-click to install, or run:

```bash
mcpb install image-generation-mcp-<version>.mcpb
```

Claude Desktop prompts for required env vars via a GUI wizard — no manual JSON editing needed.

## Quick start

```bash
image-generation-mcp serve                                # stdio transport
image-generation-mcp serve --transport http --port 8000   # streamable HTTP
```

For library usage (embedding the domain logic without the MCP transport), import from the `image_generation_mcp` package directly — see `src/image_generation_mcp/domain.py` for the entry point scaffold.

## Configuration

<<<<<<< before updating
All environment variables use the `IMAGE_GENERATION_MCP_` prefix.

### Core

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | Path | `~/.image-generation-mcp/images/` | Directory for saved generated images |
| `IMAGE_GENERATION_MCP_READ_ONLY` | bool | `true` | Hide write-tagged tools (`generate_image`) |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | str | `auto` | Default provider: `auto`, `openai`, `sd_webui`, `placeholder` |

### Providers

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | str | -- | OpenAI API key; enables OpenAI provider when set |
| `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` | str | -- | SD WebUI URL (e.g. `http://localhost:7860`); enables SD WebUI provider when set. Deprecated alias: `A1111_HOST`. |
| `IMAGE_GENERATION_MCP_SD_WEBUI_MODEL` | str | -- | SD WebUI checkpoint name for preset detection and override. Deprecated alias: `A1111_MODEL`. |

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

### Cost Control

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_PAID_PROVIDERS` | str | `openai` | Comma-separated paid provider names. Triggers elicitation confirmation on capable clients. Set to empty to disable. |

### Performance

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE` | int | `64` | Max cached transforms. Set to `0` to disable caching. |

### Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_EVENT_STORE_URL` | str | `file:///data/state/events` | EventStore backend: `file:///path` (persistent, survives restarts) or `memory://` (dev only) |
| `IMAGE_GENERATION_MCP_SERVER_NAME` | str | `image-generation-mcp` | Server name shown to MCP clients |
| `IMAGE_GENERATION_MCP_INSTRUCTIONS` | str | (dynamic) | System instructions for LLM context |
| `FASTMCP_LOG_LEVEL` | str | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` (controls FastMCP internals; use `-v` to set app loggers to DEBUG) |
| `IMAGE_GENERATION_MCP_HTTP_PATH` | str | `/mcp` | HTTP endpoint mount path |
| `IMAGE_GENERATION_MCP_APP_DOMAIN` | str | (auto) | MCP Apps widget sandbox domain. Auto-computed from `BASE_URL` for Claude; override for other hosts (see [docs](https://pvliesdonk.github.io/image-generation-mcp/configuration/)) |

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
| `generate_image` | `write` | `task=True` | `prompt` (str), `provider` (str, default `"auto"`), `negative_prompt` (str, optional), `aspect_ratio` (str, default `"1:1"`), `quality` (str, default `"standard"`) | Generate an image, returns metadata + resource URIs |
| `show_image` | -- | -- | `uri` (str) | Display an image as inline thumbnail preview with metadata |
| `list_providers` | -- | -- | *(none)* | List available providers with availability info |

`generate_image` returns JSON metadata as `TextContent` with `image_id`, `original_uri`, `resource_template`, sizes, and provider, plus a `ResourceLink` to the image. Call `show_image` with the image URI to display it.

`show_image` returns a WebP thumbnail (max 512px, always under 1 MB) as `ImageContent` for inline display, plus JSON metadata. Full-resolution images are available via `image://` resource URIs or `create_download_link`.

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
| **SD WebUI** | Photorealism, portraits, anime, artistic styles | Running SD WebUI + `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` |
| **Placeholder** | Testing, drafts, CI | Nothing (always available) |

### OpenAI

Best for text rendering, logos, typography, and general-purpose generation.

- **Models:** `gpt-image-1` (default), `dall-e-3`
- **Formats:** PNG (all models), JPEG and WebP (`gpt-image-1` only)
- **Quality levels:** `standard` (mapped to `high` for gpt-image-1), `hd` (mapped to `high`)
- **Negative prompt:** Appended as `"Avoid: {negative_prompt}"` to the prompt
- **Requires:** `IMAGE_GENERATION_MCP_OPENAI_API_KEY`

### SD WebUI (Stable Diffusion WebUI)

Best for photorealism, portraits, anime, and artistic styles. Compatible with AUTOMATIC1111, Forge, reForge, and Forge-neo.

- **API:** HTTP POST to `/sdapi/v1/txt2img`
- **Model presets:** Auto-detected from checkpoint name:
  - **SD 1.5** (default): 768px base, 30 steps, CFG 7.0, DPM++ 2M sampler, Karras scheduler
  - **SDXL**: 1024px base, 35 steps, CFG 7.5, DPM++ 2M sampler, Karras scheduler
  - **SDXL Lightning/Turbo**: 1024px base, 6 steps, CFG 2.0, DPM++ SDE sampler, Karras scheduler
- **Negative prompt:** Native support via `negative_prompt` field
- **Checkpoint override:** Specify `model` to override `sd_model_checkpoint`
- **Timeout:** 180s (SDXL at high res on consumer GPUs)
- **Requires:** `IMAGE_GENERATION_MCP_SD_WEBUI_HOST`

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
=======
Core environment variables shared across all `fastmcp-pvl-core`-based services:

| Variable | Default | Description |
|---|---|---|
| `FASTMCP_LOG_LEVEL` | `INFO` | Log level for FastMCP internals and app loggers (`DEBUG` / `INFO` / `WARNING` / `ERROR`). The `-v` CLI flag overrides to `DEBUG`. |
| `FASTMCP_ENABLE_RICH_LOGGING` | `true` | Set to `false` for plain / structured JSON log output. |
| `IMAGE_GENERATION_MCP_EVENT_STORE_URL` | `memory://` | Event store backend for HTTP session persistence — `memory://` (dev), `file:///path` (survives restarts). |

Domain-specific variables go below under [Domain configuration](#domain-configuration).

## Post-scaffold checklist

After `copier copy` and `gh repo create --push`:

1. **Fill in the DOMAIN blocks** in this README (Features, What you can do with it, Domain configuration, Key design decisions) and in `CLAUDE.md`.
2. Configure GitHub secrets — see below.
3. Install dev dependencies: `uv sync --all-extras --dev`.
4. Install pre-commit hooks: `uv run pre-commit install`.
5. Run the gate locally: `uv run pytest -x -q && uv run ruff check --fix . && uv run ruff format . && uv run mypy src/ tests/`.
6. Push the first commit — CI should be green.

## GitHub secrets

CI workflows reference three repository secrets. Configure them via **Settings → Secrets and variables → Actions** or with `gh secret set`:

| Secret | Used by | How to generate |
|---|---|---|
| `RELEASE_TOKEN` | `release.yml`, `copier-update.yml` | Fine-grained PAT at <https://github.com/settings/personal-access-tokens/new> with `contents: write` and `pull_requests: write` (the `copier-update` cron opens PRs). Scoped to this repo. |
| `CODECOV_TOKEN` | `ci.yml` | <https://codecov.io> — sign in with GitHub, add the repo, copy the upload token from the repo settings page. |
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude.yml`, `claude-code-review.yml` | Run `claude setup-token` locally and paste the result. |

```bash
gh secret set RELEASE_TOKEN
gh secret set CODECOV_TOKEN
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

`GITHUB_TOKEN` is auto-provided — no action needed.

## Local development

The PR gate (matches CI):

```bash
uv run pytest -x -q                                  # tests
uv run ruff check --fix . && uv run ruff format .    # lint + format
uv run mypy src/ tests/                              # type-check
```

Pre-commit runs a subset of the gate on each commit; see `.pre-commit-config.yaml` for details, or [`CLAUDE.md`](CLAUDE.md) for the full Hard PR Acceptance Gates.

## Troubleshooting

### Moving a scaffolded project

`uv sync` creates `.venv/bin/*` scripts with absolute shebangs pointing at the venv Python. If you move the repo after scaffolding (`mv /old/path /new/path`), `uv run pytest` fails with `ModuleNotFoundError: No module named 'fastmcp'` because the stale shebang resolves to a different interpreter than the venv's site-packages.

**Fix:**

```bash
rm -rf .venv
uv sync --all-extras --dev
```

`uv run python -m pytest` also works as a one-shot workaround (bypasses the stale entry-script shim).

### `uv.lock` refresh after `copier update`

When `copier update` introduces new dependencies (e.g. a new extra added to `pyproject.toml.jinja`), CI runs `uv sync --frozen` which fails against a stale lockfile. Run `uv lock` locally and commit the refreshed `uv.lock` alongside accepting the copier-update PR.
>>>>>>> after updating

## License

<<<<<<< before updating
MIT
=======
- [Documentation](https://pvliesdonk.github.io/image-generation-mcp/)
- [llms.txt](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)
- [FastMCP](https://gofastmcp.com)
- [fastmcp-pvl-core](https://pypi.org/project/fastmcp-pvl-core/)

<!-- ===== TEMPLATE-OWNED SECTIONS END ===== -->

## Domain configuration

<!-- DOMAIN-START -->
<!-- Replace with a table of domain-specific env vars. Kept across copier update. -->

Domain environment variables use the `IMAGE_GENERATION_MCP_` prefix:

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_EXAMPLE_VAR` | — | **Yes** | Replace this row with your first required setting. |
| `IMAGE_GENERATION_MCP_ANOTHER_VAR` | `default` | No | Replace with an optional setting. |

Domain-config fields are composed inside `src/image_generation_mcp/config.py` between the `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` sentinels; env reads go through `fastmcp_pvl_core.env(_ENV_PREFIX, "SUFFIX", default)` so naming stays consistent.
<!-- DOMAIN-END -->

## Key design decisions

<!-- DOMAIN-START -->
<!-- Replace with 3-6 bullets describing non-obvious architectural decisions. Kept across copier update. -->

_Replace this placeholder with a short list of the non-obvious design calls this service makes — e.g. "writes are append-only", "embeddings cached in SQLite", "auth uses OIDC bearer tokens". Three to six bullets is typically enough; link out to longer ADRs under `docs/decisions/` if you maintain any._
<!-- DOMAIN-END -->
>>>>>>> after updating
