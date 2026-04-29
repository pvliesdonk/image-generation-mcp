<!-- mcp-name: io.github.pvliesdonk/image-generation-mcp -->
# Image Generation MCP

[![CI](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pvliesdonk/image-generation-mcp/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/pvliesdonk/image-generation-mcp/graph/badge.svg)](https://codecov.io/gh/pvliesdonk/image-generation-mcp) [![PyPI](https://img.shields.io/pypi/v/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/) [![Python](https://img.shields.io/pypi/pyversions/image-generation-mcp)](https://pypi.org/project/image-generation-mcp/) [![License](https://img.shields.io/github/license/pvliesdonk/image-generation-mcp)](LICENSE) [![Docker](https://img.shields.io/github/v/release/pvliesdonk/image-generation-mcp?label=ghcr.io&logo=docker)](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp) [![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://pvliesdonk.github.io/image-generation-mcp/) [![llms.txt](https://img.shields.io/badge/llms.txt-available-brightgreen)](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)

Multi-provider image generation [MCP](https://modelcontextprotocol.io) server built on [FastMCP](https://gofastmcp.com). Generate images from Claude Desktop, Claude Code, or any MCP client using OpenAI, Google Gemini, Stable Diffusion (SD WebUI), or a zero-cost placeholder provider.

**[Documentation](https://pvliesdonk.github.io/image-generation-mcp/)** | **[PyPI](https://pypi.org/project/image-generation-mcp/)** | **[Docker](https://github.com/pvliesdonk/image-generation-mcp/pkgs/container/image-generation-mcp)**

## Features

<!-- DOMAIN-START -->

- **Multi-provider** — OpenAI (`gpt-image-1.5`, `gpt-image-1`, `dall-e-3`), Google Gemini (`gemini-2.5-flash-image`, `gemini-3.x` previews), SD WebUI (Stable Diffusion / Forge / reForge), and a zero-cost placeholder for testing.
- **Per-model style metadata** — every model carries a `style_profile` (strengths, prompt grammar, lifecycle); `list_providers` includes a top-level `warnings` array for deprecated models. See [Model Catalog](https://pvliesdonk.github.io/image-generation-mcp/providers/model-catalog/).
- **Keyword-based auto-selection** — `provider="auto"` routes by prompt content (text/logo → OpenAI, photoreal/anime → SD WebUI, draft → placeholder).
- **CDN-style image transforms** — `image://{id}/view?format=webp&width=512&crop_x=...` resizes / re-encodes / crops on demand without re-generating.
- **Hybrid background tasks** — long-running SD generations run with `task=True` (poll for status); short OpenAI calls stream progress in the foreground.
- **MCP Apps gallery + viewer** — interactive UI surfaces (browse generated images, edit / crop / rotate) for clients that support `app:` resources.
- **Production deployment** — Docker (multi-arch), `.deb`/`.rpm` with hardened systemd, OIDC + bearer auth, persistent EventStore for HTTP session resumability.
<!-- DOMAIN-END -->

## What you can do with it

<!-- DOMAIN-START -->

With this server mounted in an MCP client, you can ask:

- **"Generate a coffee mug product photo on a worn oak table, 16:9, no text."** Routes to `gpt-image-1.5` for typography-aware photorealism.
- **"Create three concept-art variations of a cyberpunk alley at dusk."** Composes `generate_image` with `provider="sd_webui"` and a stylised checkpoint like `dreamshaperXL`.
- **"Crop this image to a 1:1 square centred on the subject and resize to 512px."** Uses `image://{id}/view?width=512&height=512&crop_x=...` resource transforms.
- **"Show me my recent generations."** Browses the gallery via the `image://list` resource and the MCP Apps gallery viewer.
- **"Save this style as 'cyberpunk-night' so I can apply it to future requests."** Uses the style library — markdown briefs the LLM interprets per-provider.
<!-- DOMAIN-END -->

<!-- ===== TEMPLATE-OWNED SECTIONS BELOW — DO NOT EDIT; CHANGES WILL BE OVERWRITTEN ON COPIER UPDATE ===== -->

## Installation

### From PyPI

```bash
pip install image-generation-mcp
```

If you add optional extras via the `PROJECT-EXTRAS-START` / `PROJECT-EXTRAS-END` sentinels in `pyproject.toml`, document them below:

<!-- DOMAIN-START -->

| Extra | Includes | Use when |
|-------|----------|----------|
| `mcp` | `fastmcp[tasks]>=3.0,<4` | Background-task support (`task=True`) — required for long SD generations. |
| `openai` | `openai>=1.0` | Enables the OpenAI provider. |
| `google-genai` | `google-genai>=1.0` | Enables the Gemini provider. |
| `all` | `fastmcp[tasks]` + `openai` + `google-genai` | Everything except SD WebUI (which is HTTP-only — no extra needed). |

Example: `pip install image-generation-mcp[all]`.
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

## Links

- [Documentation](https://pvliesdonk.github.io/image-generation-mcp/)
- [llms.txt](https://pvliesdonk.github.io/image-generation-mcp/llms.txt)
- [FastMCP](https://gofastmcp.com)
- [fastmcp-pvl-core](https://pypi.org/project/fastmcp-pvl-core/)

<!-- ===== TEMPLATE-OWNED SECTIONS END ===== -->

## Domain configuration

<!-- DOMAIN-START -->

All domain environment variables use the `IMAGE_GENERATION_MCP_` prefix.

### Core

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_SCRATCH_DIR` | `~/.image-generation-mcp/images/` | No | Directory for saved generated images. |
| `IMAGE_GENERATION_MCP_READ_ONLY` | `true` | No | Hide write-tagged tools (`generate_image`). Set to `false` to enable generation. |
| `IMAGE_GENERATION_MCP_DEFAULT_PROVIDER` | `auto` | No | Default provider: `auto`, `openai`, `gemini`, `sd_webui`, `placeholder`. |

### Providers

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_OPENAI_API_KEY` | — | No | OpenAI API key; enables OpenAI provider when set. |
| `IMAGE_GENERATION_MCP_GOOGLE_API_KEY` | — | No | Google API key with Gemini access; enables Gemini provider when set. |
| `IMAGE_GENERATION_MCP_SD_WEBUI_HOST` | — | No | SD WebUI URL (e.g. `http://localhost:7860`); enables SD WebUI provider when set. Deprecated alias: `A1111_HOST`. |
| `IMAGE_GENERATION_MCP_SD_WEBUI_MODEL` | — | No | SD WebUI checkpoint name for preset detection and override. Deprecated alias: `A1111_MODEL`. |

### Authentication

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_BEARER_TOKEN` | — | No | Static bearer token; enables bearer auth when set. |
| `IMAGE_GENERATION_MCP_BASE_URL` | — | No | Public base URL for OIDC and MCP File Exchange downloads (e.g. `https://mcp.example.com`). |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | — | No | OIDC discovery endpoint URL. |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | — | No | OIDC client ID. |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | — | No | OIDC client secret. |
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | ephemeral | **Yes on Linux/Docker** | JWT signing key. |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | — | No | Expected JWT audience claim. |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | `openid` | No | Comma-separated required scopes. |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | No | Verify access token as JWT instead of id token. |

### Cost control & performance

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_PAID_PROVIDERS` | `openai,gemini` | No | Comma-separated paid provider names. Triggers elicitation confirmation on capable clients. Set to empty to disable. |
| `IMAGE_GENERATION_MCP_TRANSFORM_CACHE_SIZE` | `64` | No | Max cached transforms. Set to `0` to disable caching. |

### File Exchange (MCP downloads)

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_ENABLED` | `true` on http/sse, `false` on stdio | No | Master switch for the file-exchange producer. Set `false` to suppress all `file_ref` publishing. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_TTL` | `3600` | No | Default and maximum TTL (seconds) for published files and download URLs. `create_download_link`'s `ttl_seconds` is clamped to this. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_CONSUME` | `true` | Recommended `false` | Master switch for the consumer side. This server is producer-only; set `false` to silence the upstream "consume on, no consumer_sink wired" startup warning. |

### Server identity

| Variable | Default | Required | Description |
|---|---|---|---|
| `IMAGE_GENERATION_MCP_SERVER_NAME` | `image-generation-mcp` | No | Server name shown to MCP clients. |
| `IMAGE_GENERATION_MCP_INSTRUCTIONS` | (dynamic) | No | System instructions for LLM context. |
| `IMAGE_GENERATION_MCP_HTTP_PATH` | `/mcp` | No | HTTP endpoint mount path. |
| `IMAGE_GENERATION_MCP_APP_DOMAIN` | (auto) | No | MCP Apps widget sandbox domain. Auto-computed from `BASE_URL` for Claude; override for other hosts. |

Domain-config fields are composed inside `src/image_generation_mcp/config.py` between the `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` sentinels; env reads go through `fastmcp_pvl_core.env(_ENV_PREFIX, "SUFFIX", default)` so naming stays consistent.

For the full MCP tool / resource / prompt surface and per-provider setup notes, see the [documentation site](https://pvliesdonk.github.io/image-generation-mcp/).
<!-- DOMAIN-END -->

## Key design decisions

<!-- DOMAIN-START -->

- **Multi-provider with capability discovery, not feature flags.** Each provider's `discover_capabilities()` reports its actual supported aspect ratios / qualities / formats / negative-prompt support at startup; routing logic asks the capability surface, not a hard-coded enum. New providers slot in by implementing the protocol — no router edits needed. (See `docs/decisions/0001-…`, `0002-…`, `0007-…`.)
- **Per-model `style_profile` metadata, surfaced via `list_providers`.** Closed-list providers (OpenAI, Gemini, placeholder) use exact-key lookup; SD WebUI uses a regex-ordered pattern table. Profiles include lifecycle flags (`current` / `legacy` / `deprecated`) and feed an auto-built top-level `warnings` array. (See `docs/decisions/0009-…`.)
- **Hybrid background tasks.** Short calls (OpenAI ~5 s) stream progress in-line; long calls (SD WebUI 30-180 s) run as background tasks with `check_generation_status` polling — clients pick the mode via `task=True`. (See `docs/decisions/0005-…`.)
- **Image asset model: content-addressed registry + sidecar JSON metadata + on-demand transforms.** Generated images keep their full-resolution original; `image://{id}/view?format=webp&width=512&crop_x=…` resources do format conversion / resize / crop on demand without re-generating. Transforms are cached. (See `docs/decisions/0006-…`.)
- **Style library.** User-saved markdown briefs (with YAML frontmatter for tags / aspect ratio / quality) that the LLM interprets per-provider — not copy-pasted verbatim. Distinct from per-model `style_profile`: style library is the brief; `style_profile` describes the model. (See `docs/decisions/0008-…` and `0009-…` for disambiguation.)
- **Composes `fastmcp_pvl_core.ServerConfig`, never inherits.** Domain config goes between `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` sentinels; env reads route through `fastmcp_pvl_core.env(...)` to keep prefix naming consistent.
<!-- DOMAIN-END -->
