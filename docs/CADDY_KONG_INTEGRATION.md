# Caddy -> Kong integration authority

## Permanent ownership

`appolon1908-hue/Caddy` is the principal Git source for the shared Caddy edge. It owns TLS termination, public host selection, reverse-proxy handoff, shared edge headers, access-log redaction, Caddy validation, and Caddy release evidence.

`appolon1908-hue/Kong` remains principal for Kong services, routes, plugins, Keycloak OIDC/JWT validation, scopes, rate limits, request-size policy, and the gateway-to-Middleware handoff.

`appolon1908-hue/Keycloak` is the identity/token issuer. `appolon1908-hue/Middleware-` is the cross-system write/command boundary. `appolon1908-hue/codestra-production-platform` is historical runtime/deployment/reconciliation/rollback evidence only.

## Required request path

For every route already represented in accepted Kong source, the shared public API path is:

```text
client
  -> Caddy (TLS / host / outer request boundary)
  -> Kong (OIDC/JWT / scopes / route and gateway policy)
  -> Middleware (tenant/actor revalidation / durable commands)
  -> owned downstream repository/runtime
```

Caddy must not call Middleware directly for Kong-managed shared API routes. Caddy must not validate Keycloak tokens itself and must not create `X-Authenticated-Client`, `X-Authenticated-Tenant`, `X-Authenticated-Role`, or `X-Codestra-Gateway-Secret`. Those trusted application identity values are produced by the authenticated gateway boundary and revalidated by Middleware.

The incoming `Authorization` header is forwarded to Kong. It is redacted only from Caddy access logs.

Kong's accepted route contracts then forward to the approved Middleware
integration services (`codestra-middleware-integration-api-1:8095` and
`appolon-middleware-integration-api:8080`). Kong preserves the bearer
authorization header, and Middleware revalidates the gateway identity before
handling commands or writes. This handoff is recorded in
`config/caddy-kong-contract.v1.json` and is validated fail-closed; Caddy still
has no direct route to either service.

## Canonical source files

- `Caddyfile` — complete root source and private admin-listener policy.
- `snippets/security_headers.caddy` — shared edge header source owned here.
- `sites/api.codestra.co.caddy` — canonical shared API host.
- `config/caddy-kong-contract.v1.json` — machine-readable ownership and route-handoff contract.
- `config/runtime-values.example` — non-secret runtime variable names/reference listeners.

## Kong handoff

`CADDY_KONG_UPSTREAM` is the only canonical upstream for routes already represented in Kong source. The current repository-backed reference listener is `127.0.0.1:8000`; a deployment may supply another reviewed listener through the environment without changing the Caddy source contract.

The Caddy reverse proxy explicitly preserves `Host: api.codestra.co` because Kong has host-bound routes for that canonical host. Caddy also forwards the real client address, while normal reverse-proxy forwarding preserves the original scheme and bearer token for Kong policy enforcement.

## Transitional paths

The historical production-platform Caddy reference routed a realtime/health group to `127.0.0.1:18102` and other API traffic to `127.0.0.1:18101`. The principal Caddy source now routes all currently known Kong-managed path families to Kong first, while retaining explicit environment-controlled fallbacks for paths that do not yet have proven Kong route parity.

These fallbacks are migration compatibility, not a competing authority. They may be removed only after:

1. the Kong repository contains accepted equivalent route contracts;
2. write-disabled staging proves Caddy -> Kong -> Middleware for those paths;
3. live runtime inventory and checksums are recorded;
4. rollback is rehearsed;
5. an immutable Caddy source/artifact is accepted;
6. explicit production cutover approval is obtained.

## Validation gates

Caddy CI must fail when any of these become true:

- the principal repository is no longer `appolon1908-hue/Caddy`;
- `codestra-production-platform` becomes principal again;
- a Kong-managed path is removed from the Caddy -> Kong contract without an explicit contract-version change;
- Caddy creates trusted application identity headers;
- Caddy directly targets the Middleware integration listener for a Kong-managed route;
- Authorization access-log redaction disappears;
- the root Caddyfile, shared security-header snippet, or runtime variable contract is missing;
- a possible secret/private key is committed.

A green source PR does not authorize a live Caddy reload, DNS/TLS change, Kong reconciliation apply, or production traffic cutover.

## n8n editor host (automation.codestra.co)

n8n Community Edition has no enterprise SSO, so the editor cannot authenticate
against Keycloak by itself. The reviewed community-compatible strategy is
`verified-gateway-oidc-and-native-auth`, recorded in
`appolon1908-hue/N8N` at `config/n8n-policy.json`:

1. Caddy terminates TLS for `automation.codestra.co` and refuses any source
   outside `CADDY_EDITOR_ADMIN_CIDRS` before anything else runs.
2. Kong performs the Keycloak authorization-code browser flow and owns session
   policy for the host. This is a browser flow, not the bearer-only method used
   for the service routes in `kong/plugins/oidc/keycloak.yml`.
3. n8n's own native owner login stays enabled behind the gateway, so a gateway
   bypass alone does not yield editor access.

Caddy's identity boundary is unchanged: it authenticates nothing and mints no
identity headers. That is why this host has no direct upstream to n8n — removing
the Kong hop would remove the only OIDC enforcement point.

The editor is not directly publicly routable, which is the condition the N8N
policy asserts through `editor_access.publicly_routable = false`.
