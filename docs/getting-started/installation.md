# Installation

## Prerequisites

- Python 3.11 or later
- `pip` or [`uv`](https://docs.astral.sh/uv/) package manager

## From PyPI

=== "pip"

    ```bash
    # Core + MCP server
    pip install image-gen-mcp[mcp]

    # With OpenAI provider
    pip install image-gen-mcp[all]
    ```

=== "uv"

    ```bash
    # Core + MCP server
    uv pip install image-gen-mcp[mcp]

    # With OpenAI provider
    uv pip install image-gen-mcp[all]
    ```

### Available extras

| Extra | Includes | When to use |
|-------|----------|-------------|
| `mcp` | `fastmcp[tasks]>=3.0,<4` | Minimal MCP server (A1111 + placeholder) |
| `openai` | `openai>=1.0` | OpenAI provider only (no MCP server) |
| `all` | `fastmcp[tasks]` + `openai` | Full installation with all providers |
| `dev` | All above + pytest, ruff, mypy, pip-audit | Development and testing |

## From source

```bash
git clone https://github.com/pvliesdonk/image-gen-mcp.git
cd image-gen-mcp
uv sync --extra all --extra dev
```

## Docker

```bash
docker pull ghcr.io/pvliesdonk/image-gen-mcp:latest
```

See [Docker deployment](../deployment/docker.md) for Docker Compose setup.

## Verify installation

```bash
# Check the CLI is available
image-gen-mcp --help

# Start with placeholder provider (no API keys needed)
IMAGE_GEN_MCP_READ_ONLY=false image-gen-mcp serve
```

The server starts in stdio mode by default. Press Ctrl+C to stop.
