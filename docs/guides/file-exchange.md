<<<<<<< before updating
# File Exchange
=======
# MCP File Exchange

Image Generation MCP participates in the **MCP File Exchange** convention,
a lightweight, spec-defined way for co-deployed MCP servers to pass
files to each other by reference instead of by base64-in-context.

The full specification lives in `fastmcp-pvl-core`'s docs:
[`docs/specs/file-exchange.md`](https://github.com/pvliesdonk/fastmcp-pvl-core/blob/main/docs/specs/file-exchange.md).
This page is the project-side guide: **what's wired by default, which
env vars to set, and how to publish, consume, or accept agent-uploaded
`FileRef` objects from your tool bodies.**

## What's wired by default

`make_server()` calls `register_file_exchange()` once during startup.
That single call:

1. Mounts an `/artifacts/{token}` HTTP route (HTTP transport only).
2. Advertises the `experimental.file_exchange` capability on the MCP
   `initialize` response.
3. Registers two MCP tools when the surrounding env permits:
    - `create_download_link` (producer-side): mints time-limited HTTP
      URLs for `FileRef`s this server has published.
    - `fetch_file` (consumer-side): resolves a `FileRef` (via
      `exchange://` or `https://`) and hands the bytes to your sink.

By default the feature is **on** for HTTP/SSE deployments and **off**
for stdio. See [Configuration → MCP File Exchange](../configuration.md#mcp-file-exchange)
for the env-var matrix.

The **upload direction** is opt-in and not wired by default; see
[Uploading files](#uploading-files-receiver) below for the
`register_file_exchange_upload(...)` pattern.

## The two patterns

### Augmented response (recommended)

The tool returns its normal output plus a `file_ref` field. Existing
clients ignore the field and keep working; file-exchange-aware
clients can use it.

```python
from fastmcp_pvl_core import FileRefPreview

result = await handle.publish(
    source=image_bytes,
    mime_type="image/png",
    preview=FileRefPreview(description=prompt, dimensions=(width, height)),
)
return {
    "image_id": image_id,
    "prompt": prompt,
    "dimensions": {"width": width, "height": height},
    "file_ref": result.to_dict(),
}
```
>>>>>>> after updating

Image-generation-mcp publishes generated images via the **MCP File Exchange** protocol. Other MCP-aware tools and hosts can discover, mint download URLs for, and fetch the bytes — without each tool inventing its own download mechanism.

<<<<<<< before updating
## What you get
=======
The tool returns just the `FileRef`, appropriate when the file is
large and you do not want to spend tokens on inline data:
>>>>>>> after updating

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

<<<<<<< before updating
To get an actual download URL, call the spec-compliant `create_download_link` tool with the `origin_id`:
=======
`register_file_exchange` returns a `FileExchangeHandle`. Capture it
in `make_server()` and stash it where your tool bodies can reach it.
The simplest pattern is a module-level singleton in `server.py`.
This stays well-typed under `mypy --strict` (the alternative,
attaching to the `FastMCP` instance, fails `attr-defined` because
`FastMCP` does not declare a `file_exchange` field):
>>>>>>> after updating

```text
create_download_link(origin_id="abc123", ttl_seconds=300)
→ {"url": "https://mcp.example.com/artifacts/<token>", "ttl_seconds": 300, "mime_type": "image/png"}
```

The URL is single-use and TTL-bounded; the bytes are served by the same server's `/artifacts/{token}` route.

## Configuration

<<<<<<< before updating
| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `IMAGE_GENERATION_MCP_BASE_URL` | str | (none) | Public base URL of the server. **Required for HTTP downloads** — without it, file_refs declare `transfer: {}` and the bot falls back to other transfer methods (or returns `transfer_failed`). |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_ENABLED` | bool | `true` on http/sse, `false` on stdio | Master switch for the producer side. Set to `false` to disable publishing entirely. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_TTL` | int | 3600 | Default TTL (seconds) for published file records. `create_download_link`'s `ttl_seconds` argument is clamped to this maximum. |
| `IMAGE_GENERATION_MCP_FILE_EXCHANGE_CONSUME` | bool | `true` | Master switch for the consumer side. Set to `false` for this server (we are producer-only) to silence the "consume is on but no consumer_sink wired" warning at startup. |
=======
def get_file_exchange() -> FileExchangeHandle:
    """Return the registered handle. Raises if make_server has not run."""
    if _file_exchange is None:
        raise RuntimeError("file exchange is not initialised; call make_server first")
    return _file_exchange
>>>>>>> after updating

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

<<<<<<< before updating
Each variant is its own published file in the registry — the URI's query string never gets smuggled through the create_download_link surface. Pass the `file_ref.origin_id` from the variant you want to download.

## Capability advertisement

`register_file_exchange` adds an `experimental.file_exchange` capability to this server's MCP `initialize` response. Hosts that understand the protocol can use that to decide whether to drive `create_download_link` themselves.

## Reference
=======
`publish()` returns a `FileRef`. Call `.to_dict()` (or let your
return type adapter serialise it) before sending it back through MCP.

## Consuming files (`consumer_sink`)

Pass a `consumer_sink` to enable the `fetch_file` tool. The sink
receives the resolved bytes and a `FetchContext`, and returns a
`FetchResult`:

```python
from fastmcp_pvl_core import FetchContext, FetchResult

async def _store_in_vault(data: bytes, ctx: FetchContext) -> FetchResult:
    path = await _vault.write(data, mime_type=ctx.mime_type, name=ctx.suggested_filename)
    return FetchResult(stored_at=str(path), bytes_written=len(data))

# Consume-only servers do not need to capture the handle; the facade
# wires `fetch_file` itself; the handle is only required to call
# `.publish()` from a tool body (see "Producing files" above).
register_file_exchange(
    mcp,
    namespace="image-generation-mcp",
    env_prefix=_ENV_PREFIX,
    transport="auto",
    consumes=("image/*", "application/pdf"),
    consumer_sink=_store_in_vault,
)
```

`consumes=` is advertised in the capability declaration; the LLM and
peer servers use it to pick a destination for `fetch_file` calls.

## Uploading files (`receiver=`)

The download direction is producer-driven: this server `publish()`es
a file, and a peer (or LLM tool) fetches it. The **upload direction**
is the inverse: an agent or peer pushes bytes into this server, and
a **receiver** in your code commits them.

Wire it by uncommenting the `register_file_exchange_upload(...)`
block in `src/image_generation_mcp/server.py` (inside the
`DOMAIN-FILE-EXCHANGE-START / END` sentinel) and supplying a
`receiver`:

```python
from typing import Any

from fastmcp_pvl_core import UploadRecord, register_file_exchange_upload


# _vault is illustrative; replace with your domain's storage helper.
def _upload_receiver(record: UploadRecord, body: bytes) -> dict[str, Any]:
    # record.target_id, record.extra, record.max_bytes available.
    path = _vault.write(record.target_id, body)
    return {"path": str(path), "size_bytes": len(body)}

register_file_exchange_upload(
    mcp,
    namespace="image-generation-mcp",
    env_prefix=_ENV_PREFIX,
    receiver=_upload_receiver,
)
```

Once registered, an LLM-visible `create_upload_link` tool appears.
The agent calls it with a `target_id` (and optional `extra`,
`ttl_seconds`, `max_bytes`); the helper mints a one-time HTTPS
`POST /<namespace>/uploads/{token}` URL and returns it. The agent
POSTs the bytes; the route hands them to your receiver.

### Pre-link validation

To reject bad `target_id`s **before** the token is minted (so an LLM
sees a clean tool error rather than wastes a round-trip), supply
`pre_link_validator`:

```python
def _validate_upload_target(target_id: str, extra: dict[str, Any] | None) -> None:
    if not target_id.startswith("inbox/"):
        raise ValueError(f"target_id must begin with 'inbox/': {target_id}")

register_file_exchange_upload(
    mcp,
    namespace="image-generation-mcp",
    env_prefix=_ENV_PREFIX,
    receiver=_upload_receiver,
    pre_link_validator=_validate_upload_target,
)
```

Raising `ValueError` surfaces the message verbatim to the caller.
Other exceptions also propagate but are logged at ERROR with a
`non-ValueError` marker so operators distinguish bugs from
caller-input errors. Sync validators run in `asyncio.to_thread`
automatically; `async def` validators run on the loop.

### Receiver error contract

The receiver runs **after** route-level checks pass. Oversized bodies
(over `UPLOAD_MAX_BYTES`) return `413` and expired or already-consumed
tokens return `404` before the receiver is invoked. Once the receiver
runs, exceptions translate to status codes as follows:

| Exception | Response | When to use |
|-----------|----------|-------------|
| `ValueError` | `400` Bad Request | Request body fails domain validation. |
| `FileExistsError` | `409` Conflict | `target_id` collides with existing data. |
| Anything else | `500` Internal Server Error | Server-side bug. Traceback is logged. |

For `400` and `409`, the exception's `str(exc)` becomes the response
body, so frame those messages as caller-facing diagnostics. The `500`
path returns a generic body and logs the traceback server-side. A
returned `dict[str, Any]` produces `200` and is JSON-encoded into the
response; non-dict returns are treated as receiver bugs (`500` with a
WARNING log). Sync receivers run in `asyncio.to_thread` (blocking I/O
does not stall the loop); `async def` receivers run on the loop.

Tokens are **one-time**: every non-2xx response burns the link;
retries call `create_upload_link` again. For uploads too large to
buffer, use `stream_receiver=` (`AsyncIterator[bytes]` shape; **`async
def` only**, since sync stream receivers cannot iterate the body).
Documented in the upstream `fastmcp-pvl-core` README; the template
scaffolds the buffered shape only.

See [Configuration → MCP File Exchange](../configuration.md#mcp-file-exchange)
for the env-var matrix.

## Co-deploying two servers (docker-compose)

The `exchange://` transfer method requires both servers to share a
volume mounted at `MCP_EXCHANGE_DIR`. Example:

```yaml
services:
  image-mcp:
    image: ghcr.io/example/image-mcp:latest
    environment:
      IMAGE_MCP_TRANSPORT: http
      IMAGE_MCP_BASE_URL: https://mcp.example.com/image
      MCP_EXCHANGE_DIR: /var/lib/mcp-exchange
    volumes:
      - mcp-exchange:/var/lib/mcp-exchange

  vault-mcp:
    image: ghcr.io/example/vault-mcp:latest
    environment:
      VAULT_MCP_TRANSPORT: http
      VAULT_MCP_BASE_URL: https://mcp.example.com/vault
      MCP_EXCHANGE_DIR: /var/lib/mcp-exchange
    volumes:
      - mcp-exchange:/var/lib/mcp-exchange

volumes:
  mcp-exchange:
```

Both containers see the same `.exchange-id` file, so they agree on
the exchange group automatically. When `image-mcp` publishes a file,
`vault-mcp` can fetch it via the `exchange://` URI without an HTTP
round-trip: the bytes never leave the shared volume.
>>>>>>> after updating

- Spec: [`fastmcp_pvl_core/docs/specs/file-exchange.md`](https://github.com/pvliesdonk/fastmcp-pvl-core/blob/main/docs/specs/file-exchange.md)
- Helper API: `fastmcp_pvl_core.register_file_exchange`, `FileExchangeHandle.publish`, `FileRef`, `FileRefPreview`
- Wired in this project at: `src/image_generation_mcp/server.py` (`make_server`)
