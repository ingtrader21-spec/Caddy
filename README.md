# Codestra Caddy Edge

Canonical Git source for Codestra shared Caddy edge configuration and release policy.

## Principal authority

This repository is the **principal source** for shared Caddy TLS termination, public host selection, reverse-proxy configuration, shared edge request policy, security-header imports, access-log redaction, validation, and Caddy release evidence.

For the shared API edge, the required ownership chain is:

```text
client
  -> Caddy
  -> Kong
  -> Middleware
  -> owned downstream service
```

Caddy does not authenticate application users/services, does not issue identity, and does not create trusted application identity headers. It preserves the bearer token and canonical host so Kong can apply Keycloak OIDC/JWT, scope, route, rate, and request policy. Middleware then revalidates privileged authorization and remains the cross-system write boundary.

Each system keeps its own source authority:

- `appolon1908-hue/Caddy` — shared Caddy TLS/reverse-proxy edge source and policy.
- `appolon1908-hue/Kong` — Kong gateway services, routes, plugins, OIDC/scope policy and gateway reconciliation.
- `appolon1908-hue/Keycloak` — identity, clients, scopes and token issuance.
- `appolon1908-hue/Middleware-` — cross-system command/event control plane and privileged provider orchestration.
- product/provider repositories — their own application and runtime source.
- `appolon1908-hue/codestra-production-platform` — historical runtime/deployment/reconciliation/rollback evidence only. It is a migration reference, not principal source for future Caddy changes.

## Canonical source layout

- `Caddyfile` — complete root source; Caddy admin API is loopback-only.
- `snippets/security_headers.caddy` — shared security-header snippet owned here.
- `sites/api.codestra.co.caddy` — shared API-edge routing source.
- `config/caddy-kong-contract.v1.json` — machine-readable Caddy/Kong/Keycloak/Middleware boundary.
- `config/runtime-values.example` — non-secret runtime variable names and repository-backed reference listeners.
- `docs/CADDY_KONG_INTEGRATION.md` — migration and validation gates.
- `sites/n8n-editor.community.caddy` — Keycloak/oauth2-proxy boundary for the community-edition editor.
- `deploy/community-n8n/` — fail-closed node and outbound-network policy overlay.
- `config/community-n8n-credentials.v1.json` — metadata-only ownership and rotation contract.

The runtime identity remains the canonical Keycloak-managed `n8n-automation`
client. The editor gateway uses the existing `n8n_operator` and `n8n_admin`
roles. Until OpenBao is commissioned, its client and cookie material is supplied
as root-owned Docker secret files; only paths and rotation metadata belong here.

## Caddy -> Kong integration

The reviewed Kong repository exposes host-bound `api.codestra.co` route contracts and exercises the Kong data plane on loopback port `8000`. The Caddy source therefore uses `CADDY_KONG_UPSTREAM` for path families already represented in Kong source and preserves `Host: api.codestra.co` on that handoff.

The historical `codestra-production-platform` Caddy source used loopback listeners `18101` and `18102`. They are retained only as explicit environment-controlled migration fallbacks for paths that do not yet have proven Kong parity. They are **not** principal source authority and must be removed after the equivalent Kong routes pass staging acceptance.

No new shared API route should be added as a direct Caddy -> Middleware or Caddy -> provider path. The owning repository must add the service contract, Kong must own the gateway route/security policy, and Caddy then owns the outer edge handoff.

## Branch model

- `development` — active integration branch.
- `test` — configuration promoted after validation.
- `production` — release-candidate source for a live Caddy host.
- `main` — reviewed canonical baseline and release history.

Promotion flow: `feature/*` -> `development` -> `test` -> `production` -> `main`.

The repository may use short-lived authority or migration branches for source-convergence work, but accepted shared-edge source must end on reviewed `main` before an immutable release is created.

## Historical reference

The first `api.codestra.co` source was imported from:

`appolon1908-hue/codestra-production-platform:release/production-activation:operations/caddy/api.codestra.co.caddy`

That repository is reference/evidence only. Its historical source does not prove a live host currently matches this repository.

Before any Caddy cutover:

1. inventory the live runtime read-only;
2. record active config/listener checksums;
3. compare live behavior with this repository;
4. validate Caddy -> Kong -> Middleware in write-disabled staging;
5. prove invalid identity is rejected at Kong;
6. rehearse rollback;
7. build/accept an immutable Caddy source artifact;
8. obtain explicit deployment approval;
9. reload using the reviewed artifact/config only;
10. perform post-change read-back.

## Safety rules

1. Never commit TLS private keys, API tokens, credentials, passwords, `.env` files, ACME account data, or Caddy data-directory contents.
2. Validate the complete root `Caddyfile` before a reload.
3. Keep the Caddy admin API on `127.0.0.1:2019`; never expose it publicly.
4. Caddy must not manufacture `X-Authenticated-*` or gateway-secret headers.
5. Caddy must preserve the bearer token for Kong; Authorization is redacted from logs only.
6. Shared API paths represented in Kong source must route Caddy -> Kong, never directly to Middleware.
7. Back up active runtime configuration before replacement.
8. A failed validation must leave the running configuration untouched.
9. A merge does not automatically authorize a production reload, DNS/TLS change, or traffic cutover.
10. `codestra-production-platform` may be consulted for historical evidence, but new Caddy source changes belong here.
