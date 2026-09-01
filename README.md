# Codestra Caddy Edge

This repository is the principal Git source for Codestra Caddy edge configuration, validation, promotion, deployment controls, and release evidence.

## Authority and request path

The governed shared API path is:

```text
client -> Caddy -> Kong -> Middleware -> owned downstream service
```

Caddy owns TLS termination, public host selection, reverse-proxy configuration, shared edge policy, security headers, and access-log redaction. Kong owns gateway authentication and route policy. Keycloak owns identity and token issuance. Middleware owns privileged cross-system commands and provider orchestration.

Repository ownership remains separated:

- `appolon1908-hue/Caddy` — Caddy source and edge policy.
- `appolon1908-hue/Kong` — gateway services, routes, plugins, scope and request policy.
- `appolon1908-hue/Keycloak` — clients, scopes, roles, and token issuance.
- `appolon1908-hue/Middleware-` — integration control plane and provider-effect policy.
- `appolon1908-hue/codestra-production-platform` — protected release tuples and historical deployment evidence; not Caddy source authority.

## Configuration states

There is one deployable configuration authority:

- `config/Caddyfile` plus `config/snippets/`, `config/sites/`, and `config/conf.d/` is the complete imported production configuration. Its files were formatted, secret-scanned, and checksum-matched to the running host before promotion. Deployment tooling reads only this tree.

The future Caddy-to-Kong convergence contract is deliberately non-deployable:

- `candidate/Caddyfile`, `candidate/snippets/`, and `candidate/sites/` contain reviewed migration candidates and are validated in CI, but deployment tooling never reads them. They may replace the deployable tree only after route parity and exact-digest staging certification pass.

This distinction prevents the incomplete migration candidate from replacing the complete live configuration.

## Branch model

Promotion is pull-request-only:

`feature/*` -> `development` -> `test` -> `staging` -> `production` -> `main`

- `development` — active integration.
- `test` — automated and integration testing.
- `staging` — pre-production certification source.
- `production` — approved live-configuration source.
- `main` — reviewed canonical history.

## Safety rules

1. Never commit TLS private keys, API tokens, credentials, passwords, `.env` files, ACME account data, or Caddy data-directory contents.
2. Validate the complete deployable configuration before a reload.
3. Keep the Caddy admin API private; never expose it publicly.
4. Caddy must not manufacture trusted application-identity headers.
5. Shared API routes move to Caddy -> Kong only after Kong parity is proven.
6. Back up the active configuration before replacement.
7. Failed validation or reload must preserve or restore the previous configuration.
8. A source merge does not authorize a live reload, DNS/TLS cutover, or capability activation.
9. Production deployment uses the exact reviewed production commit and never a dirty server worktree.
10. SSH configuration is outside this repository and must not be changed.

Before runtime cutover, capture live checksums, certify Caddy -> Kong -> Middleware in isolated staging, verify negative authentication cases, create a current backup, and rehearse rollback.
