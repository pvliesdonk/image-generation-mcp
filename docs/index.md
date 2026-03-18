# image-gen-mcp

Multi-provider image generation [MCP](https://modelcontextprotocol.io) server built on [FastMCP](https://gofastmcp.com). Generate images from Claude Desktop, Claude Code, or any MCP client using OpenAI, Stable Diffusion (A1111 WebUI), or a zero-cost placeholder provider.

## Features

- **Multi-provider** -- OpenAI (gpt-image-1, dall-e-3), A1111 (Stable Diffusion WebUI), and placeholder
- **Auto-selection** -- keyword-based routing picks the best provider for your prompt
- **Image assets** -- content-addressed registry with thumbnail previews and resource URI-based transforms
- **Background tasks** -- hybrid foreground (progress streaming) and background (polling) execution
- **MCP native** -- tools, resources, and prompts following the MCP specification
- **Authentication** -- bearer token, OIDC, and multi-auth support
- **Docker ready** -- multi-arch image with privilege dropping

## Architecture

```
MCP Client (Claude Desktop / Claude Code)
    |
    v
+---------------------------------------------+
|  MCP Layer                                   |
|  Tools:     generate_image, list_providers   |
|  Resources: info://providers                 |
|             image://{id}/view{?transforms}   |
|             image://{id}/metadata            |
|             image://list                     |
|  Prompts:   select_provider, sd_prompt_guide |
+------------------+---+----------------------+
                   |   |
  Depends(service) |   | processing.py
                   v   v
+---------------------------------------------+
|  ImageService                                |
|  - Provider registry (name -> instance)      |
|  - Image registry (content-addressed IDs)    |
|  - generate() -> dispatches to provider      |
|  - register_image() -> saves + indexes       |
+------+----------+----------+----------------+
       |          |          |
       v          v          v
  +---------+ +--------+ +--------------+
  | OpenAI  | | A1111  | | Placeholder  |
  |Provider | |Provider| | Provider     |
  +---------+ +--------+ +--------------+
```

## Quick start

```bash
# Install
pip install image-gen-mcp[all]

# Run with placeholder (no API keys needed)
IMAGE_GEN_MCP_READ_ONLY=false image-gen-mcp serve

# Run with OpenAI
IMAGE_GEN_MCP_READ_ONLY=false \
IMAGE_GEN_MCP_OPENAI_API_KEY=sk-... \
image-gen-mcp serve
```

## Navigation

<div class="grid cards" markdown>

-   **Getting Started**

    ---

    Install, configure, and connect to Claude Desktop or Claude Code.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   **Providers**

    ---

    Compare providers, set up OpenAI or A1111, use the placeholder.

    [:octicons-arrow-right-24: Provider overview](providers/index.md)

-   **Configuration**

    ---

    All environment variables with types, defaults, and descriptions.

    [:octicons-arrow-right-24: Configuration reference](configuration.md)

-   **MCP Interface**

    ---

    Tools, resources, and prompts exposed to MCP clients.

    [:octicons-arrow-right-24: Tools](tools.md) | [:octicons-arrow-right-24: Resources](resources.md) | [:octicons-arrow-right-24: Prompts](prompts.md)

</div>
