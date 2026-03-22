# OIDC Authentication

Optional token-based authentication for HTTP deployments. Two OIDC modes are available:

| Mode | Env var | Use case | Required vars |
|------|---------|----------|---------------|
| **`remote`** (recommended) | `AUTH_MODE=remote` | Local JWT validation — no upstream token re-validation | `BASE_URL` + `OIDC_CONFIG_URL` |
| **`oidc-proxy`** | `AUTH_MODE=oidc-proxy` | DCR emulation for non-DCR IdPs | `BASE_URL` + `OIDC_CONFIG_URL` + `OIDC_CLIENT_ID` + `OIDC_CLIENT_SECRET` |

The mode is auto-detected when `AUTH_MODE` is not set: `oidc-proxy` when client credentials are present, `remote` otherwise. For an overview of all authentication modes (bearer token, OIDC, no auth), see the [Authentication guide](../guides/authentication.md).

!!! warning "Transport requirement"
    OIDC requires `--transport http` (or `sse`). It has no effect with `--transport stdio`.

!!! tip "Prefer remote mode"
    `remote` mode avoids the [OIDCProxy session lifetime issue](../guides/authentication.md#known-limitations-oidc-session-lifetime) by validating tokens locally via JWKS without storing or re-validating upstream tokens. Use `oidc-proxy` only when your IdP does not support Dynamic Client Registration and you need DCR emulation.

## Remote Mode (recommended)

### Required Variables

| Variable | Description |
|----------|-------------|
| `IMAGE_GENERATION_MCP_BASE_URL` | Public base URL of the server (e.g. `https://mcp.example.com`) |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | OIDC discovery endpoint (e.g. `https://auth.example.com/.well-known/openid-configuration`) |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | — | Expected JWT audience claim; leave unset if your provider does not set one |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | — | Comma-separated required scopes |

### Example

```bash
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
# Optional:
# IMAGE_GENERATION_MCP_OIDC_AUDIENCE=image-generation-mcp
```

The server fetches the OIDC discovery document at startup to obtain `jwks_uri` and `issuer`, then validates incoming JWTs locally. No client credentials, JWT signing key, or upstream token storage needed.

## OIDCProxy Mode

### Required Variables

| Variable | Description |
|----------|-------------|
| `IMAGE_GENERATION_MCP_BASE_URL` | Public base URL of the server (e.g. `https://mcp.example.com`; include prefix when mounted under subpath, e.g. `https://mcp.example.com/vault`) |
| `IMAGE_GENERATION_MCP_OIDC_CONFIG_URL` | OIDC discovery endpoint (e.g. `https://auth.example.com/.well-known/openid-configuration`) |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_ID` | OIDC client ID registered with your provider |
| `IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET` | OIDC client secret |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` | ephemeral | JWT signing key. **Required on Linux/Docker** — the default is ephemeral and invalidates tokens on restart |
| `IMAGE_GENERATION_MCP_OIDC_AUDIENCE` | — | Expected JWT audience claim; leave unset if your provider does not set one |
| `IMAGE_GENERATION_MCP_OIDC_REQUIRED_SCOPES` | `openid` | Comma-separated required scopes |
| `IMAGE_GENERATION_MCP_OIDC_VERIFY_ACCESS_TOKEN` | `false` | Set `true` to verify the upstream access token as JWT instead of the id token. Only needed when your provider issues JWT access tokens and you require audience-claim validation on that token |

## JWT Signing Key

The FastMCP default signing key is ephemeral (regenerated on startup), which forces clients to re-authenticate after every restart. Set a stable random secret to avoid this:

```bash
# Generate once, store in your .env file
openssl rand -hex 32
```

!!! danger "Linux / Docker"
    On Linux (including Docker), the ephemeral key is especially problematic because it does not persist across process restarts. Always set `IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY` in production.

## Setup with Authelia

!!! note
    Authelia does not support Dynamic Client Registration (RFC 7591). Clients must be registered manually in `configuration.yml`.

!!! warning "Opaque vs JWT access tokens"
    Authelia issues **opaque** (non-JWT) access tokens by default. This affects which OIDC mode you can use:

    - **Remote mode** validates tokens locally via JWKS and **requires JWT access tokens**. Set `access_token_signed_response_alg: 'RS256'` on the client registration (see below).
    - **OIDCProxy mode** verifies the `id_token` (always a standard JWT) instead of the access token, so opaque tokens work without extra configuration. However, oidc-proxy is subject to the [session lifetime limitation](#known-limitations-oidc-session-lifetime).

### Remote mode (recommended)

Remote mode requires only `BASE_URL` + `OIDC_CONFIG_URL` on the MCP server — no client credentials needed server-side. The client authenticates directly with Authelia; the server validates the resulting JWT access token via JWKS.

!!! note "Client credentials are IdP-side only"
    In remote mode, `CLIENT_ID` and `CLIENT_SECRET` are configured in the **Authelia client registration** (so Authelia knows which client is connecting), but they are **not** set as MCP server environment variables. The MCP server only needs the OIDC discovery URL to fetch JWKS keys for token validation.

#### 1. Register the client in Authelia

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: image-generation-mcp
        client_secret: '$pbkdf2-sha512$...'   # authelia crypto hash generate
        redirect_uris:
          - https://mcp.example.com/callback
        grant_types: [authorization_code]
        response_types: [code]
        pkce_challenge_method: S256
        scopes: [openid, profile, email]
        # Required for remote mode — enables JWT access tokens (RFC 9068)
        # Without this, Authelia issues opaque tokens that cannot be
        # validated locally via JWKS
        access_token_signed_response_alg: 'RS256'
        # Claude Code (and some other MCP clients) sends credentials via
        # POST body rather than HTTP Basic auth during token exchange
        token_endpoint_auth_method: 'client_secret_post'
```

!!! tip "Why `access_token_signed_response_alg`?"
    Remote mode's `JWTVerifier` decodes the access token as a JWT and validates its signature against the IdP's JWKS keys. Authelia's default opaque tokens are random strings with no JWT structure — they cannot be validated locally. Setting `access_token_signed_response_alg: 'RS256'` tells Authelia to issue RFC 9068 JWT access tokens for this client.

!!! tip "Why `token_endpoint_auth_method`?"
    During the OAuth token exchange, the MCP client sends `client_id` and `client_secret` in the POST body (`client_secret_post`). Authelia defaults to `client_secret_basic` (HTTP Basic auth header). If these don't match, the token exchange fails with a `token_endpoint_auth_method` error. Setting `client_secret_post` explicitly ensures compatibility with Claude Code and other MCP clients.

#### 2. Set environment variables

```bash
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
```

No `CLIENT_ID`, `CLIENT_SECRET`, or `JWT_SIGNING_KEY` needed — the server only validates tokens, it does not participate in the OAuth flow.

#### 3. Start with HTTP transport

```bash
image-generation-mcp serve --transport http --port 8000
```

### OIDCProxy mode (fallback)

Use oidc-proxy only when remote mode is not viable (e.g., your IdP cannot issue JWT access tokens). Be aware of the [session lifetime limitation](../guides/authentication.md#known-limitations-oidc-session-lifetime).

#### 1. Register the client in Authelia

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: image-generation-mcp
        client_secret: '$pbkdf2-sha512$...'   # authelia crypto hash generate
        redirect_uris:
          - https://mcp.example.com/auth/callback
        grant_types: [authorization_code]
        response_types: [code]
        pkce_challenge_method: S256
        scopes: [openid, profile, email]
        # Claude Code sends credentials via POST body
        token_endpoint_auth_method: 'client_secret_post'
```

No `access_token_signed_response_alg` needed — oidc-proxy verifies the `id_token` (always a JWT) instead of the access token.

#### 2. Set environment variables

```bash
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
IMAGE_GENERATION_MCP_OIDC_CLIENT_ID=image-generation-mcp
IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET=your-client-secret
IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY=$(openssl rand -hex 32)
```

#### 3. Start with HTTP transport

```bash
image-generation-mcp serve --transport http --port 8000
```

For subpath deployments (e.g., public URL `https://mcp.example.com/vault/mcp`), see [Subpath Deployments](#subpath-deployments) below.

## Architecture

### Remote mode

The server acts as a Resource Server (RFC 9728). The client authenticates directly with the IdP; the server validates tokens locally via JWKS.

```
Client → OIDC Provider (authenticate) → Client → image-generation-mcp (validate JWT)
```

1. Client authenticates with the OIDC provider independently
2. Client sends requests to the MCP server with the JWT token
3. Server validates the token locally using the IdP's JWKS keys
4. No upstream token storage or re-validation

### OIDCProxy mode

The server uses FastMCP's built-in `OIDCProxy` auth provider to act as an OAuth intermediary with DCR emulation.

```
Client → image-generation-mcp (with OIDCProxy) → OIDC Provider (Authelia/Keycloak)
```

1. Client connects to the MCP server
2. Server redirects to the OIDC provider for authentication
3. Provider authenticates the user and returns a code
4. Server exchanges the code for tokens and issues its own proxy JWT
5. Subsequent requests include the proxy JWT

!!! warning "Session lifetime"
    OIDCProxy re-validates upstream tokens on every request. When the upstream token expires (typically 1h), sessions die even though the proxy JWT is still valid. See [Known Limitations](../guides/authentication.md#known-limitations-oidc-session-lifetime).

## Docker Compose with OIDC

```yaml
services:
  image-generation-mcp:
    image: ghcr.io/pvliesdonk/image-generation-mcp:latest
    env_file: .env
    volumes:
      - images-data:/data/service
      - state-data:/data/state
    environment:
      IMAGE_GENERATION_MCP_SCRATCH_DIR: /data/service
      FASTMCP_HOME: /data/state/fastmcp
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.image-generation-mcp.rule=Host(`mcp.example.com`)"
      - "traefik.http.routers.image-generation-mcp.tls.certresolver=letsencrypt"
      - "traefik.http.services.image-generation-mcp.loadbalancer.server.port=8000"
    networks:
      - traefik

volumes:
  images-data:
  state-data:

networks:
  traefik:
    external: true
```

With the corresponding `.env`:

```bash
IMAGE_GENERATION_MCP_READ_ONLY=true
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com
IMAGE_GENERATION_MCP_OIDC_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
IMAGE_GENERATION_MCP_OIDC_CLIENT_ID=image-generation-mcp
IMAGE_GENERATION_MCP_OIDC_CLIENT_SECRET=your-client-secret
IMAGE_GENERATION_MCP_OIDC_JWT_SIGNING_KEY=your-stable-hex-key
```

For a prefixed deployment (e.g., `https://mcp.example.com/vault/mcp`), see [Subpath Deployments](#subpath-deployments) below.

## Subpath Deployments

When OIDC is enabled behind a reverse-proxy subpath, `BASE_URL` and `HTTP_PATH` serve different roles:

| Variable | Purpose | Example |
|----------|---------|---------|
| `BASE_URL` | Public URL of the server, **including the subpath prefix** | `https://mcp.example.com/vault` |
| `HTTP_PATH` | Internal MCP endpoint mount point — **no subpath prefix** | `/mcp` |

The reverse proxy strips the subpath prefix before forwarding to the application. FastMCP concatenates `BASE_URL + HTTP_PATH` to build the public resource URL, so including the prefix in both produces broken URLs with duplicated path segments.

!!! danger "Do not duplicate the subpath"
    Setting `BASE_URL=https://mcp.example.com/vault` **and** `HTTP_PATH=/vault/mcp` produces a duplicated resource URL: `https://mcp.example.com/vault/vault/mcp`. The subpath belongs in `BASE_URL` only.

### Configuration

Environment variables:

```bash
IMAGE_GENERATION_MCP_BASE_URL=https://mcp.example.com/vault
IMAGE_GENERATION_MCP_HTTP_PATH=/mcp
```

Register this callback URI in your OIDC provider:

```text
https://mcp.example.com/vault/auth/callback
```

### Reverse proxy routing

The reverse proxy must:

1. **Strip the prefix** (`/vault`) from operational routes before forwarding to the app
2. **Forward OAuth discovery routes** to this service (without stripping prefixes):
    - `/.well-known/oauth-authorization-server` — authorization server metadata
    - `/.well-known/oauth-protected-resource/vault/mcp` — protected resource metadata

Example Traefik configuration:

```yaml
labels:
  # Operational routes: strip /vault prefix before forwarding
  - "traefik.http.routers.vault-app.rule=Host(`mcp.example.com`) && PathPrefix(`/vault`)"
  - "traefik.http.middlewares.strip-vault.stripprefix.prefixes=/vault"
  - "traefik.http.routers.vault-app.middlewares=strip-vault"
  - "traefik.http.services.vault-app.loadbalancer.server.port=8000"
  # OAuth discovery routes: forward without stripping
  - "traefik.http.routers.vault-wellknown.rule=Host(`mcp.example.com`) && (PathPrefix(`/.well-known/oauth-authorization-server`) || PathPrefix(`/.well-known/oauth-protected-resource/vault/mcp`))"
  - "traefik.http.routers.vault-wellknown.service=vault-app"
```

!!! note
    This configuration requires that no other OAuth service claims `/.well-known/oauth-authorization-server` on this hostname. See [Shared-hostname limitation](#shared-hostname-limitation) below.

### Shared-hostname limitation

!!! warning "Shared-hostname subpath with native OIDC is not supported"
    When multiple OAuth-capable services share a hostname (e.g., `mcp-auth-proxy` at the root and `image-generation-mcp` at `/vault`), native OIDC on a subpath does not work.

    **Why:** FastMCP serves the OAuth authorization-server metadata at `/.well-known/oauth-authorization-server` (host root), regardless of the subpath in `BASE_URL`. The FastMCP codebase contains an RFC 8414 path-aware override (`OIDCProxy.get_well_known_routes()`) that would serve it at `/.well-known/oauth-authorization-server/vault`. However, this method is not wired into the route mounting flow and is effectively dead code.

    The protected-resource metadata (`/.well-known/oauth-protected-resource/vault/mcp`) is correctly path-namespaced and does not collide. Only the authorization-server discovery route is the problem.

    This works when `image-generation-mcp` is the **only** OAuth service on the hostname — the host-root `/.well-known/oauth-authorization-server` does not collide with anything. It breaks when another service already owns that route.

**Recommendations for shared-hostname scenarios:**

- **Dedicated hostname** (preferred): give `image-generation-mcp` its own hostname (e.g., `vault.example.com`) so discovery routes do not collide.
- **External auth gateway**: use `mcp-auth-proxy` as a sidecar instead of native OIDC. The MCP server runs unauthenticated behind the proxy, and the proxy handles OAuth discovery at its own routes.
