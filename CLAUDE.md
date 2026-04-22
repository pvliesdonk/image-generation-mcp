# image-generation-mcp

FastMCP server scaffold. See [TEMPLATE.md](TEMPLATE.md) for customisation guide.

## Project Structure

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

## Conventions

- Python 3.11+
- `uv` for package management, `ruff` for linting/formatting (line length 88)
- `hatchling` build backend
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Google-style docstrings on all public functions
- `logging.getLogger(__name__)` throughout, no `print()`
- Type hints everywhere

## Key Patterns

- Library is sync; MCP layer uses `asyncio.to_thread()` for blocking calls
- Write tools tagged `tags={"write"}`, hidden via `mcp.disable(tags={"write"})` in read-only mode
- Auth: composed via `fastmcp_pvl_core.build_auth()` inside `make_server()`; MultiAuth assembled automatically when both bearer + OIDC are configured
- `_ENV_PREFIX` in `config.py` controls all env var names — change once, affects everything

## Documentation

Every PR that changes user-facing behavior must update the corresponding documentation:

- **New/changed tools or resources** → update `docs/tools.md` and `docs/resources.md`
- **New/changed env vars** → update `docs/configuration.md` AND the README config table
- **New/changed provider behavior** → update the provider's page in `docs/providers/`
- **New MCP client configuration** → update `docs/getting-started/claude-desktop.md` or `claude-code.md`

The architect-reviewer conformance check includes documentation currency. A PR that adds a tool without documenting it is incomplete.

Internal design docs (`docs/design/`, `docs/decisions/`) are developer reference — they are NOT part of the mkdocs site. ADRs are created/updated as part of implementation issues, not documentation issues.
