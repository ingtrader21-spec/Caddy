# Codestra Caddy Controller

This repository is the Git-controlled source of truth for Caddy configuration and release operations.

## Branch model

- `development` — active integration branch; feature branches target this branch first.
- `test` — configuration promoted from development after validation.
- `production` — release candidate state for the live Caddy server.
- `main` — governance, release history, and the canonical reviewed baseline.

## Promotion flow

`feature/*` → `development` → `test` → `production` → `main`

No direct production deployment should be performed from an unreviewed feature branch.

## Safety rules

1. Never commit TLS private keys, API tokens, credentials, passwords, `.env` files, or Caddy data-directory contents.
2. Validate and format Caddy configuration before a reload.
3. Prefer `caddy reload` / `systemctl reload caddy` over process restarts.
4. Keep the Caddy admin API private; do not expose port 2019 publicly.
5. Back up the active configuration before replacing it.
6. A failed validation must leave the currently running configuration untouched.
7. Production changes require a pull request and successful validation checks.

The current live server configuration must be imported before this repository is allowed to deploy to production. Until that import is reviewed, the repository contains controller scaffolding only and must not replace `/etc/caddy/Caddyfile`.
