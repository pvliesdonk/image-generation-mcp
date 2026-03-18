# Claude Code

Connect image-gen-mcp to Claude Code as an MCP server.

## Configuration

Add a `.mcp.json` file to your project root:

### Placeholder only (no API keys)

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-gen-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GEN_MCP_READ_ONLY": "false"
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
      "command": "image-gen-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GEN_MCP_READ_ONLY": "false",
        "IMAGE_GEN_MCP_OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### With all providers

```json
{
  "mcpServers": {
    "image-gen": {
      "command": "image-gen-mcp",
      "args": ["serve"],
      "env": {
        "IMAGE_GEN_MCP_READ_ONLY": "false",
        "IMAGE_GEN_MCP_OPENAI_API_KEY": "sk-...",
        "IMAGE_GEN_MCP_A1111_HOST": "http://localhost:7860"
      }
    }
  }
}
```

## Verify

After adding the configuration, restart Claude Code (or run `/mcp` to reload MCP servers). Then:

1. Ask Claude: "List the available image generation providers"
2. Ask Claude: "Generate a test image using the placeholder provider"

## Tips

- Use `provider="auto"` (the default) to let the server pick the best provider based on your prompt
- The `select_provider` prompt gives Claude guidance on provider strengths
- The `sd_prompt_guide` prompt helps Claude write effective Stable Diffusion prompts
- Generated images are saved to `~/.image-gen-mcp/images/` by default (configurable via `IMAGE_GEN_MCP_SCRATCH_DIR`)
