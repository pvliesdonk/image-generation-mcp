# Authentication

This guide covers how to protect your image-generation-mcp server with authentication. Choose the mode that fits your deployment.

!!! warning "Transport requirement"
    Authentication only works with HTTP transport (`--transport http` or `sse`). It has no effect with `--transport stdio`.

## Auth modes

The server supports four authentication modes:

| Mode | When to use | Configuration |
|------|-------------|---------------|
| **Multi-auth** | Mixed clients — e.g. Claude web (OIDC) + Claude Code (bearer token) on the same server | Set `IMAGE_GENERATION_MCP_BEARER_TOKEN` + OIDC variables |
| **Bearer token** | Simple deployments behind a VPN, Docker compose stacks, development | Set `IMAGE_GENERATION_MCP_BEARER_TOKEN` only |
| **OIDC (remote)** | Production with user identity — recommended | Set `BASE_URL` + `OIDC_CONFIG_URL` |
| **OIDC (oidc-proxy)** | Production when IdP lacks DCR support and you need DCR emulation | Set `BASE_URL` + `OIDC_CONFIG_URL` + `OIDC_CLIENT_ID` + `OIDC_CLIENT_SECRET` |
| **No auth** | Local stdio usage, trusted networks | Default (nothing to configure) |

When both bearer token and OIDC are configured, the server accepts **either** credential — a valid bearer token or a valid OIDC session. This is useful when different clients require different authentication flows against the same vault instance.

### OIDC mode selection

Two OIDC modes are available via the `IMAGE_GENERATION_MCP_AUTH_MODE` env var:

- **`remote`** (recommended): The server validates tokens locally via JWKS. The client authenticates directly with the IdP. No client credentials, JWT signing key, or upstream token storage needed. Only requires `BASE_URL` + `OIDC_CONFIG_URL`.

- **`oidc-proxy`**: The server acts as an OAuth intermediary, emulating Dynamic Client Registration (DCR) for IdPs that don't support it natively. Requires `CLIENT_ID`, `CLIENT_SECRET`, and optionally `JWT_SIGNING_KEY`. Subject to the [session lifetime limitation](#known-limitations-oidc-session-lifetime).

When `AUTH_MODE` is not set, it auto-detects: `oidc-proxy` when client credentials are present, `remote` otherwise. See [OIDC deployment guide](../deployment/oidc.md) for setup details.

---

## Bearer token

The simplest way to protect your server. A single static token shared between server and clients.

### Setup

1. Generate a random token:

    ```bash
    openssl rand -hex 32
    ```

2. Set the environment variable:

    ```bash
    IMAGE_GENERATION_MCP_BEARER_TOKEN=your-generated-token
    ```

3. Start the server with HTTP transport:

    ```bash
    image-generation-mcp serve --transport http --port 8000
    ```

### Client usage

Clients must include the token in every request:

```
Authorization: Bearer your-generated-token
```

### When to use bearer token

- Deployments behind a VPN or firewall
- Docker compose stacks where services communicate internally
- Development and testing environments
- Any scenario where full OIDC is overkill

See also: [`examples/bearer-auth.env`](https://github.com/pvliesdonk/image-generation-mcp/blob/main/examples/bearer-auth.env) for a ready-to-use example.

---

## OIDC

Full OAuth 2.1 authentication using an external identity provider. Supports user login flows, SSO, and multi-user access control.

### How it works

The server uses FastMCP's built-in `OIDCProxy` — no external auth sidecar needed:

```
Client → image-generation-mcp (OIDCProxy) → OIDC Provider
```

1. Client connects to the server
2. Server redirects to the OIDC provider for login
3. Provider authenticates the user and returns a code
4. Server exchanges the code for tokens
5. Subsequent requests include the JWT

### Required variables

| Variable | Description |
|----------|-------------|
| `IMAGE_GENERATION_MCP_BASE_URL` | Public base URL for OIDC and artifact download links (e.g. `https://mcp.example.com`) |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | OIDC discovery endpoint |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | Client ID registered with your provider |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | Client secret |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | ephemeral | JWT signing key — **required on Linux/Docker** |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | — | Expected JWT audience claim; leave unset if your provider does not set one |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | Set `true` to verify the access token as a JWT instead of the id token; useful for audience-claim validation on JWT access tokens |

!!! danger "JWT signing key on Linux/Docker"
    Without `OIDC_JWT_SIGNING_KEY`, FastMCP generates an ephemeral key that invalidates all tokens on restart. Always set a stable key in production:

    ```bash
    openssl rand -hex 32
    ```

!!! tip "Long-running sessions"
    Current MCP clients do not reliably refresh tokens — see [Known Limitations](#known-limitations-oidc-session-lifetime). Configure **all** token lifetimes (access, id, refresh) on your identity provider to cover a full workday (8h+). For simpler deployments, bearer token auth is unaffected by these limitations.

### Full OIDC reference

For the full OIDC reference (env vars, Docker Compose, subpath deployments, architecture):

- [OIDC Authentication reference](../deployment/oidc.md)

---

## Troubleshooting

### "invalid client" error

The `client_id` and/or `redirect_uris` in your OIDC provider config don't match the values in your `.env` file. Verify both sides match exactly.

### Tokens invalidated after restart

You're missing `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY`. Without it, FastMCP generates an ephemeral key on each startup. Generate and set a stable key:

```bash
openssl rand -hex 32
```

### Auth has no effect

Authentication only works with HTTP transport. If you're using `--transport stdio`, auth is silently ignored. Switch to `--transport http`.

### Bearer token not working

- Verify the env var is set and non-empty (whitespace-only values are ignored)
- Check that clients send `Authorization: Bearer <token>` (not `Basic` or other schemes)
- If OIDC is also configured, multi-auth is active — both bearer and OIDC are accepted simultaneously

### OIDC redirect fails

- Verify `BASE_URL` matches your public URL exactly (including any subpath prefix)
- For subpath deployments, see the [subpath deployment guide](../deployment/oidc.md#subpath-deployments) — `BASE_URL` must include the prefix, `HTTP_PATH` must not
- Check that `redirect_uris` in your provider config includes your callback URL (e.g., `https://mcp.example.com/auth/callback`)

### Session drops after token expiry

**Symptom:** the MCP client works for a period (often ~1 hour), then starts returning 401 errors or stops responding. Restarting the client fixes it temporarily.

**Root cause:** this is almost always a token lifetime issue, not a server bug. Check three things:

1. **id_token lifetime** (most common): When using `verify_id_token` mode (the default for Authelia), the server re-validates the upstream `id_token` on every request. If your provider's `id_token` lifetime is shorter than the `access_token` lifetime, the session dies at the `id_token` expiry — even though the access token is still valid. Authelia defaults `id_token` to 1 hour. **Fix: set `id_token` lifetime to match `access_token`** in your provider config.

2. **access_token lifetime**: If both `id_token` and `access_token` are set correctly but sessions still drop, check that the provider's `expires_in` response matches your configured lifetime.

3. **No refresh token**: See [Known Limitations](#known-limitations-oidc-session-lifetime) below — current MCP clients cannot refresh tokens, so sessions are limited to the token lifetime.

**Workaround:** configure **all** token lifetimes on your identity provider to cover a full workday:

```yaml
# Authelia example
lifespans:
  custom:
    mcp_long_lived:
      access_token: '8h'
      id_token: '8h'        # must match access_token for verify_id_token mode
      refresh_token: '30d'
```

### Opaque access tokens (Authelia)

Authelia issues opaque (non-JWT) access tokens. This is handled automatically — the server verifies the `id_token` instead. No extra configuration needed.

---

## Known Limitations: OIDC session lifetime

### The problem

When using FastMCP's `OIDCProxy` (or `OAuthProxy`), sessions die when the upstream IdP access token expires — typically after 1 hour — even though the proxy has issued its own JWT with a longer lifetime.

### Root cause: OAuthProxy double-validation

FastMCP's `OAuthProxy.load_access_token()` performs **two** token validations on every request:

1. Verify the proxy's own JWT (signature, expiry, scopes) — **this succeeds**
2. Fetch and re-validate the upstream IdP token from the token store — **this fails after upstream expiry**

When the upstream token expires, step 2 returns `None`, causing a 401 — even though the proxy JWT is still valid. The client has no way to preemptively refresh because it only sees the proxy JWT's expiry, not the upstream token's shorter expiry.

This is tracked upstream: [PrefectHQ/fastmcp#3581](https://github.com/PrefectHQ/fastmcp/issues/3581)

!!! note "Not a client bug"
    Previous versions of this documentation attributed the problem to MCP client refresh bugs. Investigation confirmed the root cause is server-side: deployments using `mcp-auth-proxy` (which validates only its own JWT) do not exhibit the same session death, ruling out client-side refresh as the primary cause.

### Additional client-side limitations

These client issues are real but secondary — fixing them alone would not resolve the OAuthProxy double-validation problem:

| Layer | Issue | Impact |
|-------|-------|--------|
| **Claude Code** | Stores refresh tokens but never uses them ([claude-code#21333](https://github.com/anthropics/claude-code/issues/21333)) | Refresh tokens are obtained and saved but never sent back |
| **Claude Code** | Never requests `offline_access` scope ([claude-code#7744](https://github.com/anthropics/claude-code/issues/7744)) | Some providers won't issue a refresh token without this scope |
| **MCP Python SDK** | Token refresh deadlocks inside SSE streams ([python-sdk#1326](https://github.com/modelcontextprotocol/python-sdk/issues/1326)) | SDK hangs when attempting refresh during an active stream |

### Workarounds

**Use `remote` auth mode instead of `oidc-proxy`** (recommended). Set `AUTH_MODE=remote` — the server validates tokens locally via JWKS without storing or re-validating upstream tokens. This requires only `BASE_URL` + `OIDC_CONFIG_URL`. See [OIDC mode selection](#oidc-mode-selection) for setup details.

**Bearer token auth** is unaffected by all of the above. If your deployment allows it (e.g., Claude Code with env vars, or API clients), bearer tokens are the simplest and most reliable option.

**Long token lifetimes** mitigate the problem for OIDCProxy deployments. Set the upstream IdP's access token lifetime to cover your session duration:

- `access_token: '8h'` — covers a workday (this is the critical one)
- `id_token: '8h'` — must match access_token when using `verify_id_token` mode
- `refresh_token: '30d'` — ready for when clients support refresh

### Tracking

- [PrefectHQ/fastmcp#3581](https://github.com/PrefectHQ/fastmcp/issues/3581) — OAuthProxy double-validation (root cause)
- [#99](https://github.com/pvliesdonk/image-generation-mcp/issues/99) — auth refactoring to support RemoteAuthProvider
- [anthropics/claude-code#21333](https://github.com/anthropics/claude-code/issues/21333) — refresh tokens stored but never used
- [anthropics/claude-code#7744](https://github.com/anthropics/claude-code/issues/7744) — `offline_access` scope never requested
- [modelcontextprotocol/python-sdk#1326](https://github.com/modelcontextprotocol/python-sdk/issues/1326) — SSE refresh deadlock
