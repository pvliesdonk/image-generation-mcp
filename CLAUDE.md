# image-generation-mcp

FastMCP server scaffold. See [TEMPLATE.md](TEMPLATE.md) for customisation guide.

## Design
<!-- DOMAIN-START -->
<!-- Add image-generation-mcp design notes here. Kept across copier update. -->
<!-- DOMAIN-END -->

## Project Structure
<!-- DOMAIN-START -->

```
src/image_generation_mcp/
  server.py            -- FastMCP server factory (make_server) + auth wiring
  config.py            -- env var loading; add domain config fields here
  cli.py               -- CLI entry point (serve command)
  _server_deps.py      -- lifespan + Depends() DI; replace placeholder service
  _server_tools.py     -- MCP tools; replace example tools with domain tools
  _server_resources.py -- MCP resources; add domain resources here
  _server_prompts.py   -- MCP prompts; add domain prompts here
```
<!-- DOMAIN-END -->

<!-- ===== TEMPLATE-OWNED SECTIONS BELOW — DO NOT EDIT; CHANGES WILL BE OVERWRITTEN ON COPIER UPDATE ===== -->


## Conventions

- Python 3.11+
- `uv` for package management, `ruff` for linting/formatting (line length 88)
- `hatchling` build backend
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Google-style docstrings on all public functions
- `logging.getLogger(__name__)` throughout, no `print()`
- Type hints everywhere
- Tests: `pytest` with fixtures in `tests/fixtures/`

## Hard PR Acceptance Gates

Every PR must pass **all** of the following before merge. Do not open or push a PR until these are green locally:

1. **CI passes** — `uv run pytest -x -q` all tests pass
2. **Lint passes** — run in this exact order: `uv run ruff check --fix .` then `uv run ruff format .` then verify with `uv run ruff format --check .`. Always run format *after* check --fix because check --fix can leave files needing reformatting.
3. **Type-check passes** — `uv run mypy src/` reports no errors
4. **Patch coverage ≥ 80%** — Codecov measures only lines added/changed in the PR diff. Run `uv run pytest --cov=<changed_module> --cov-report=term-missing` and verify new code is exercised. Add tests for every uncovered branch before pushing.
5. **Docs updated** — `README.md` and `docs/**` reflect any user-facing changes in the same commit
6. **Manifest version lockstep** — `server.json`, `.claude-plugin/plugin/.claude-plugin/plugin.json`, and `.claude-plugin/plugin/.mcp.json` must all carry the same version. The release workflow bumps them atomically via PSR; manual touches require updating all three.

## GitHub Review Types

GitHub has two distinct review mechanisms — **both must be read and addressed**:

- **Inline review comments** (`get_review_comments`): attached to specific lines of the diff. Appear in the "Files changed" tab. Use `get_review_comments` to fetch these.
- **PR-level comments** (`get_comments`): posted on the Conversation tab, not tied to a line. Review summary posts, bot analysis, and blocking issues are often posted here. Use `get_comments` to fetch these.

Always fetch both before declaring a review round complete.

## Documentation Discipline

Every issue, PR, and code change must consider documentation impact. Before closing any issue or creating any PR, check whether the following need updating:

- **`docs/design.md`** — the authoritative spec. Any new feature, changed behavior, or architectural decision must be reflected here.
- **`README.md`** — user-facing documentation. New env vars, tools, resources, prompts, CLI flags, or configuration options must be documented here.
- **`docs/` site pages** — the published documentation site. New or changed MCP tools/resources/prompts, new env vars, new installation methods or deployment options.
- **`CHANGELOG.md`** — managed by semantic-release from conventional commits.
- **Inline docstrings** — new or changed public API methods need accurate Google-style docstrings.

**Rule: code without matching docs is incomplete.**

## Logging Standard

### Framework
- Standard library `logging` throughout. Every module: `logger = logging.getLogger(__name__)`.
- No `print()` for operational output. No third-party logging libraries.
- FastMCP middleware handles tool invocation, timing, and error logging automatically.
- All logging goes through FastMCP's `configure_logging()` for uniform output. `FASTMCP_LOG_LEVEL` is the single log level control; the `-v` CLI flag sets it to `DEBUG`. `FASTMCP_ENABLE_RICH_LOGGING=false` switches to plain/JSON output.

### Log Levels
| Level | Use for |
|-------|---------|
| `DEBUG` | Detailed internals: cache hits, parameter values, config resolution |
| `INFO` | Significant operations: service startup, configuration decisions (tool calls logged by middleware) |
| `WARNING` | Degraded but continuing: API errors with fallback, missing optional config, unexpected data |
| `ERROR` | Failures affecting the primary result. Use `logger.error(..., exc_info=True)` when traceback is needed |

### Exception Handling
- All exceptions must be caught and handled. No bare `except:`. Always specify the exception type.
- Expected errors (HTTP 4xx, missing data): catch, log, return user-facing error string.
- Optional enrichment failures: catch, log at `DEBUG` with `exc_info=True`, continue.
- Primary result errors: catch, log at `WARNING` or `ERROR`, return error string.
- `ErrorHandlingMiddleware` is a safety net. If it catches something, that's a bug to fix.

### Message Format
- Pseudo-structured: `logger.info("event_name key=%s", value)`
- Event name as first token (snake_case), then key=value pairs via `%s` formatting.
- Never use f-strings in log calls (defeats lazy evaluation).

## Config & Customization Contract

Domain configuration composes `fastmcp_pvl_core.ServerConfig` inside your domain config class (see `src/image_generation_mcp/config.py`).  Add domain fields between the `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` sentinels and populate them in `from_env` between the `CONFIG-FROM-ENV-START` / `CONFIG-FROM-ENV-END` sentinels.  Never inherit from `ServerConfig`; always compose.

Env var prefix is `IMAGE_GENERATION_MCP_` — all env reads go through `fastmcp_pvl_core.env(_ENV_PREFIX, "SUFFIX", default)` so naming stays consistent.

## Shared Infrastructure

Shared infrastructure (auth providers, middleware stack, logging bootstrap, event store factory, CLI scaffolding, release pipeline, Docker entrypoint, nfpm packaging, mcpb bundle) lives upstream in two places:

- [`fastmcp-pvl-core`](https://github.com/pvliesdonk/fastmcp-pvl-core) — the Python library that provides `ServerConfig`, auth builders, middleware helpers, artifact store, and the `make_serve_parser` / `configure_logging_from_env` / `normalise_http_path` CLI helpers.
- [`fastmcp-server-template`](https://github.com/pvliesdonk/fastmcp-server-template) — the copier template this project was generated from. Ships the CI/release workflows, `Dockerfile`, `packaging/nfpm.yaml`, `packaging/mcpb/*`, `scripts/bump_manifests.py`, server.py skeleton, and this very section of CLAUDE.md.

Fixes and improvements to shared code land in those repos and propagate here via `copier update` against the template's latest tag — run manually or via the weekly `.github/workflows/copier-update.yml` cron. Starter files listed in `_skip_if_exists` (e.g. `scripts/bump_manifests.py`, `packaging/mcpb/*`, the `tools.py` / `resources.py` / `prompts.py` / `domain.py` scaffolds, `README.md`, `CHANGELOG.md`, `LICENSE`, `.env.example`) are written once and require manual reconciliation on template updates — review `_skip_if_exists` in the template's `copier.yml` if you need to force-sync a file. Domain-specific code (tools, resources, prompts, and the fields and logic inside the `CONFIG-FIELDS-START` / `CONFIG-FIELDS-END` and `CONFIG-FROM-ENV-START` / `CONFIG-FROM-ENV-END` sentinels) stays in this repo.

<!-- ===== TEMPLATE-OWNED SECTIONS END ===== -->

## Key Patterns
<!-- DOMAIN-START -->

- Library is sync; MCP layer uses `asyncio.to_thread()` for blocking calls
- Write tools tagged `tags={"write"}`, hidden via `mcp.disable(tags={"write"})` in read-only mode
- Auth: composed via `fastmcp_pvl_core.build_auth()` inside `make_server()`; MultiAuth assembled automatically when both bearer + OIDC are configured
- `_ENV_PREFIX` in `config.py` controls all env var names — change once, affects everything
<!-- DOMAIN-END -->

## Documentation
<!-- DOMAIN-START -->

Every PR that changes user-facing behavior must update the corresponding documentation:

- **New/changed tools or resources** → update `docs/tools.md` and `docs/resources.md`
- **New/changed env vars** → update `docs/configuration.md` AND the README config table
- **New/changed provider behavior** → update the provider's page in `docs/providers/`
- **New MCP client configuration** → update `docs/getting-started/claude-desktop.md` or `claude-code.md`

The architect-reviewer conformance check includes documentation currency. A PR that adds a tool without documenting it is incomplete.

Internal design docs (`docs/design/`, `docs/decisions/`) are developer reference — they are NOT part of the mkdocs site. ADRs are created/updated as part of implementation issues, not documentation issues.
<!-- DOMAIN-END -->
