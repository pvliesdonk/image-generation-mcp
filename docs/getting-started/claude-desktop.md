# Claude Desktop

Connect mcp-imagegen to Claude Desktop as an MCP server.

## Configuration

Edit your Claude Desktop MCP configuration file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

### Placeholder only (no API keys)

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "mcp-imagegen",
      "args": ["serve"],
      "env": {
        "MCP_IMAGEGEN_READ_ONLY": "false"
      }
    }
  }
}
```

### With OpenAI

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "mcp-imagegen",
      "args": ["serve"],
      "env": {
        "MCP_IMAGEGEN_READ_ONLY": "false",
        "MCP_IMAGEGEN_OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### With OpenAI + A1111

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "mcp-imagegen",
      "args": ["serve"],
      "env": {
        "MCP_IMAGEGEN_READ_ONLY": "false",
        "MCP_IMAGEGEN_OPENAI_API_KEY": "sk-...",
        "MCP_IMAGEGEN_A1111_HOST": "http://localhost:7860"
      }
    }
  }
}
```

### HTTP transport

For HTTP transport (required for authentication):

```json
{
  "mcpServers": {
    "image-gen": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Start the server separately:

```bash
MCP_IMAGEGEN_READ_ONLY=false \
MCP_IMAGEGEN_OPENAI_API_KEY=sk-... \
mcp-imagegen serve --transport http --port 8000
```

## Verify

After restarting Claude Desktop:

1. Look for the MCP server icon in the chat input area
2. Ask Claude: "List the available image generation providers"
3. Ask Claude: "Generate a test image of a sunset"

## Troubleshooting

### Server not showing in Claude Desktop

- Verify the JSON syntax is valid (no trailing commas)
- Ensure `mcp-imagegen` is on your PATH (try running it in a terminal first)
- Restart Claude Desktop completely (quit and reopen)

### Tools not visible

- Check that `MCP_IMAGEGEN_READ_ONLY` is set to `"false"` -- the `generate_image` tool is hidden in read-only mode (the default)
- `list_providers` is always visible regardless of read-only mode

### Generation fails

- Check the provider is available: ask Claude to run `list_providers`
- For OpenAI: verify your API key is valid and has image generation access
- For A1111: verify the WebUI is running and accessible at the configured host
