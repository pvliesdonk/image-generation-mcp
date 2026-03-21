# Client Compatibility

image-generation-mcp works with any MCP client, but image display capabilities vary significantly across clients. This guide covers what works where and how to get the best experience on each platform.

## Image display strategies

The server provides multiple ways to deliver images, in order of richness:

| Strategy | How it works | Best for |
|----------|-------------|----------|
| **MCP Apps viewer** | Interactive HTML viewer in a sandboxed iframe (`ui://image-viewer/view.html`) | Claude Desktop, claude.ai |
| **ImageContent** | WebP thumbnail (max 512px) inline in the conversation | Claude Desktop, claude.ai |
| **Resource URIs** | `image://{id}/view` with on-demand transforms | Clients with resource support |
| **Download links** | One-time HTTP URL via `create_download_link` | All clients (universal fallback) |

## Client support matrix

| Client | ImageContent | MCP Apps | Resources | Download URLs |
|--------|-------------|----------|-----------|---------------|
| **Claude Desktop** | Yes | Yes | Yes | Yes |
| **Claude web (claude.ai)** | Yes | Yes | Yes | Yes |
| **Claude Mobile** | Unconfirmed | No (see below) | Limited | Yes |
| **Claude Code** | Partial | No | Yes | Yes |
| **ChatGPT** (dev mode) | No | No | Unknown | Yes |
| **Gemini CLI** | No | No | No | Yes |
| **Cursor / Windsurf** | Limited | No | Unknown | Yes |
| **Cline / Roo Code** | No | No | Unknown | Yes |
| **MCP Inspector** | Yes | No | Yes | Yes |

!!! note "ImageContent is not widely supported"
    As of March 2026, Claude Desktop and claude.ai are the only major MCP clients
    that reliably render `ImageContent` (base64 images) from tool results. Other
    clients either ignore the image data, show raw base64 text, or return empty
    objects.

## Recommendations by client

### Claude Desktop / claude.ai (full experience)

Everything works out of the box:

1. `generate_image` returns metadata + resource link
2. `show_image` displays a thumbnail preview inline **and** renders the interactive MCP Apps viewer with metadata
3. Full-resolution access via `image://` resource URIs

### Claude Code

`show_image` returns a thumbnail that Claude can see in context. The MCP Apps viewer is not supported. Use `create_download_link` when you need to save or share the full-resolution image.

### ChatGPT / Gemini CLI / other clients

These clients cannot display `ImageContent` from tool results. Use `create_download_link` to generate a one-time HTTP download URL that can be opened in a browser or passed to other tools.

```
1. generate_image(prompt="a sunset") → image_id
2. create_download_link(uri="image://abc123/view?format=jpeg")
   → {"download_url": "https://mcp.example.com/artifacts/..."}
```

!!! tip "`create_download_link` requires HTTP transport"
    Download links are only available when the server runs with `--transport http`
    (or `sse`). The stdio transport has no HTTP server to host the artifact
    endpoint. You also need `IMAGE_GENERATION_MCP_BASE_URL` configured.

## Known limitations

### Claude Mobile — MCP Apps viewer fails

The Claude mobile app has a bug in streamable-HTTP session recovery. After the server restarts or a session times out, the mobile app fails to re-establish the MCP session, causing "Failed to fetch app content" errors for the image viewer.

**Root cause:** The mobile app retries with a stale session ID (HTTP 404), then retries without the auth token (HTTP 401), then starts a new session but sends tool calls without completing the `initialize` handshake (HTTP 400). This cycle repeats indefinitely.

**Workaround:** Image generation itself still works — the `generate_image` tool returns metadata with resource URIs. Use `create_download_link` to get an HTTP URL for viewing the image in a browser.

**Status:** Upstream bug in the Claude mobile app. The server-side behavior is correct (verified by comparing with successful claude.ai web sessions on the same server).

### ImageContent size limit

Claude Desktop and claude.ai impose a ~1 MB limit on tool result content. To stay under this limit, `show_image` always returns a WebP thumbnail (max 512px) as `ImageContent`, regardless of the requested transforms. The metadata reports both the actual transformed dimensions (`dimensions`) and the preview dimensions (`thumbnail_dimensions`).

For full-resolution images, use:

- `image://{id}/view` resource URI (clients with resource support)
- `create_download_link` (all clients)
