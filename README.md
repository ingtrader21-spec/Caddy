# Codestra Caddy Edge

Canonical Git source for Codestra shared Caddy edge configuration and release policy.

## Principal authority

This repository is the principal source for shared Caddy TLS termination, reverse-proxy configuration, edge request policy, security-header imports, access-log redaction, and the Caddy-to-Kong or Caddy-to-service handoff.

Each system keeps its own source authority:

- `appolon1908-hue/Caddy` — shared Caddy edge source and policy.
- `appolon1908-hue/Kong` — Kong gateway services, routes, plugins, OIDC and gateway reconciliation.
- `appolon1908-hue/Keycloak` — identity, clients, scopes and token issuance.
- `appolon1908-hue/Middleware-` — cross-system command/event control plane and privileged provider orchestration.
- product/provider repositories — their own application and runtime source.
- `appolon1908-hue/codestra-production-platform` — historical runtime/deployment/reconciliation evidence only. It is a migration reference, not principal source for future Caddy changes.

## Branch model

- `development` — active integration branch.
- `test` — configuration promoted after validation.
- `production` — release candidate state for a live Caddy host.
- `main` — reviewed canonical baseline and release history.

Promotion flow: `feature/*` → `development` → `test` → `production` → `main`.

## Reference import

`sites/api.codestra.co.caddy` is imported without behavior changes from the reviewed historical reference:

`appolon1908-hue/codestra-production-platform:release/production-activation:operations/caddy/api.codestra.co.caddy`

That provenance does not prove a live host currently matches this repository. Before any cutover, perform read-only runtime inventory, compare checksums, validate the complete Caddy configuration in staging, rehearse rollback, and require explicit deployment approval.

## Safety rules

1. Never commit TLS private keys, API tokens, credentials, passwords, `.env` files, ACME account data, or Caddy data-directory contents.
2. Validate and format Caddy configuration before a reload.
3. Prefer controlled reload over process restart.
4. Keep the Caddy admin API private; never expose port 2019 publicly.
5. Back up the active runtime configuration before replacement.
6. A failed validation must leave the currently running configuration untouched.
7. A merge does not automatically authorize production reload or deployment.
8. `codestra-production-platform` may be consulted for historical runtime evidence, but new Caddy source changes belong here.
