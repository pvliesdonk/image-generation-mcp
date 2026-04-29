# File Exchange

Image-generation-mcp publishes generated images via the **MCP File Exchange** protocol. Other MCP-aware tools and hosts can discover, mint download URLs for, and fetch the bytes — without each tool inventing its own download mechanism.

## What you get

`show_image` is the producer: every variant it renders (the default URI plus any `?format=…&width=…&height=…&quality=…` transform) publishes a `file_ref` in its JSON metadata:

```json
{
  "image_id": "abc123",
  "file_ref": {
    "origin_server": "image-generation-mcp",
    "origin_id": "abc123",
    "transfer": {"http": {"tool": "create_download_link"}},
    "mime_type": "image/png",
    "size_bytes": 524288,
    "preview": {"description": "blue sky over hills"}
  }
}
```

To get an actual download URL, call the spec-compliant `create_download_link` tool with the `origin_id`:

```text
create_download_link(origin_id="abc123", ttl_seconds=300)
→ {"url": "https://mcp.example.com/artifacts/<token>", "ttl_seconds": 300, "mime_type": "image/png"}
```

The URL is single-use and TTL-bounded; the bytes are served by the same server's `/artifacts/{token}` route.

## Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_BASE_URL` | str | (none) | Public base URL of the server. **Required for HTTP downloads** — without it, file_refs declare `transfer: {}` and the bot falls back to other transfer methods (or returns `transfer_failed`). |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_ENABLED` | bool | `true` on http/sse, `false` on stdio | Master switch for the producer side. Set to `false` to disable publishing entirely. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_TTL` | int | 3600 | Default TTL (seconds) for published file records. `create_download_link`'s `ttl_seconds` argument is clamped to this maximum. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_CONSUME` | bool | `true` | Master switch for the consumer side. Set to `false` for this server (we are producer-only) to silence the "consume is on but no consumer_sink wired" warning at startup. |

## Transport behavior

| Transport | `file_ref` published? | `download_url` populated? | `create_download_link` registered? |
|-----------|----------------------|---------------------------|-----------------------------------|
| `stdio` | No (`http_enabled=False`) | No | No |
| `http` / `sse` | Yes (when BASE_URL is set) | Yes (auto-minted in `show_image` for gallery UI compat) | Yes |

`show_image` publishes eagerly (with `source=` bytes already in memory) because it has just rendered them for the inline thumbnail. `generate_image` does **not** publish at return time: bytes don't exist yet (the background task hasn't run), and the provider-chosen `mime_type` (`image/png` / `image/webp` / `image/jpeg`) isn't known until the provider returns. The flow is:

1. Call `generate_image` → get back `image_id` + `status: "generating"`.
2. Poll `check_generation_status(image_id)` until `status: "completed"`.
3. Call `show_image(uri="image://{image_id}/view")` (optionally with transform params) — this publishes the file_ref.
4. Pass `file_ref.origin_id` to `create_download_link` to mint a URL.

## Transform variants

Each combination of `format` / `width` / `height` / `quality` parameters in a `show_image` URI produces its own opaque `origin_id`:

```text
show_image(uri="image://abc/view")                     → origin_id="abc"
show_image(uri="image://abc/view?format=webp")         → origin_id="abc-<hash1>"
show_image(uri="image://abc/view?format=webp&width=128")→ origin_id="abc-<hash2>"
```

Each variant is its own published file in the registry — the URI's query string never gets smuggled through the create_download_link surface. Pass the `file_ref.origin_id` from the variant you want to download.

## Capability advertisement

`register_file_exchange` adds an `experimental.file_exchange` capability to this server's MCP `initialize` response. Hosts that understand the protocol can use that to decide whether to drive `create_download_link` themselves.

## Reference

- Spec: [`fastmcp_pvl_core/docs/specs/file-exchange.md`](https://github.com/pvliesdonk/fastmcp-pvl-core/blob/main/docs/specs/file-exchange.md)
- Helper API: `fastmcp_pvl_core.register_file_exchange`, `FileExchangeHandle.publish`, `FileRef`, `FileRefPreview`
- Wired in this project at: `src/image_generation_mcp/server.py` (`make_server`)
