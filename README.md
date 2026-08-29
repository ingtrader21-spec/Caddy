# Codestra Caddy Controller

This repository is the Git-controlled source of truth for Caddy configuration, validation, promotion, deployment, and release evidence.

## Branch model

- `development` — active integration branch; feature/fix branches target this branch first.
- `test` — automated and integration-test promotion branch.
- `staging` — pre-production environment used for smoke, TLS, routing, WebSocket, and upstream checks.
- `production` — approved live configuration candidate.
- `main` — canonical reviewed release history and governance baseline.

## Promotion flow

`feature/*` / `fix/*` → `development` → `test` → `staging` → `production` → `main`

Every promotion is performed by pull request. No feature branch is allowed to deploy directly to production.

## Environment layout

- `config/development/`
- `config/test/`
- `config/staging/`
- `config/production/`

Each environment owns its explicit Caddy configuration. Environment-specific differences must be visible in Git rather than hidden on a server.

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

The current live server configuration still needs to be imported into this repository. Until that import is reviewed and promoted through the branch chain, this repository contains controller scaffolding only and must not replace `/etc/caddy/Caddyfile`.
