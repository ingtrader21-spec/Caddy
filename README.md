# Codestra Caddy Controller

This repository is the Git-controlled source of truth for Caddy configuration, validation, promotion, deployment, and release evidence.

## Branch model

- `development` — active integration environment; feature/fix branches target this branch first.
- `test` — automated and integration-test environment.
- `staging` — pre-production environment used for smoke, TLS, routing, WebSocket, and upstream checks.
- `production` — approved live configuration source for the Caddy server.
- `main` — canonical reviewed release history and governance baseline.

## Promotion flow

`feature/*` / `fix/*` → `development` → `test` → `staging` → `production` → `main`

Every promotion is performed by pull request. No feature branch is allowed to deploy directly to production.

## Configuration layout

- `config/Caddyfile` — canonical Caddy configuration at the commit checked out on the current environment branch.
- `snippets/` — optional reusable Caddy snippets when introduced.
- `scripts/` — validation, initial import, deployment, rollback/drift support.
- `.github/workflows/` — validation and promotion-chain enforcement.

The branch is the environment boundary. Do not maintain duplicate development/test/staging/production Caddyfiles in the same commit; promotion must move one reviewed configuration forward through the branch chain.

## Controller rule

After the initial live configuration is imported, GitHub becomes the configuration authority. Direct/manual edits to the server Caddyfile are treated as configuration drift and must be reconciled back through a pull request.

## Safety rules

1. Never commit TLS private keys, API tokens, credentials, passwords, `.env` files, or Caddy data-directory contents.
2. Validate and format Caddy configuration before a reload.
3. Prefer `caddy reload` / `systemctl reload caddy` over process restarts.
4. Keep the Caddy admin API private; do not expose port 2019 publicly.
5. Back up the active configuration before replacing it.
6. A failed validation or reload must leave or restore the previously working configuration.
7. Production changes require a pull request and successful validation checks.
8. Production deployment must use the exact reviewed commit; do not deploy an uncommitted server-side edit.

## Initial migration state

The current live server configuration still needs to be imported into `config/Caddyfile`. Until that import is reviewed and promoted through the branch chain, this repository contains controller scaffolding only and must not replace `/etc/caddy/Caddyfile`.
