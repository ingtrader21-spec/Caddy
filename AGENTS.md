# Caddy Repository Operating Rules

## Authority

This repository is the configuration authority for Caddy. The live server is not allowed to become the undocumented source of truth after the initial import.

## Branch contract

- Work starts on `feat/*`, `fix/*`, or `chore/*` branches based on `development`.
- Feature/fix PRs target `development`.
- Promote `development` to `test` only by PR.
- Promote `test` to `staging` only by PR after automated validation.
- Promote `staging` to `production` only by PR after smoke, TLS, routing, WebSocket, and upstream evidence.
- Promote `production` to `main` only after deployment evidence is recorded.
- Never force-push `main`, `production`, `staging`, or `test`.
- Never deploy a feature branch directly to a live server.

## Configuration rules

- Do not invent, rename, remove, or redirect domains/upstreams without evidence from the current configuration or an approved change.
- The initial live `/etc/caddy/Caddyfile` must be imported and reviewed before production deployment is enabled.
- Keep environment-specific configuration under `config/<environment>/`.
- Run `scripts/validate.sh` before every PR update.
- Prefer reload over restart.
- A failed validation or reload must leave or restore the previously working configuration.
- Production deployment must use the exact reviewed Git commit.
- Manual server edits are drift; reconcile them through Git before the next release.

## Secret rules

Never commit:

- TLS private keys or certificate state
- `.env` files
- API tokens
- DNS provider credentials
- passwords or bearer tokens
- Caddy `/data` or `/config` runtime state
- SSH private keys

Use environment variables or the deployment host's secret store for runtime credentials.

## Network/security rules

- Caddy admin API must remain local/private.
- Do not expose port 2019 publicly.
- Do not use `tls_insecure_skip_verify` as a workaround.
- Do not widen trusted proxy ranges without an explicit network requirement.
- Preserve HTTP/3/UDP 443 only where intentionally supported.

## Required PR evidence

Every configuration PR must identify:

1. changed hosts/routes/upstreams;
2. validation result;
3. expected HTTP/TLS behavior;
4. rollback impact;
5. whether the change affects authentication, API ingress, WebSockets, or internal services;
6. environment promotion source and destination.
