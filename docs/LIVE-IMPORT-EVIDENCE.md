# Live Caddy Import Evidence

Status: **LIVE CONFIGURATION IMPORTED — PROMOTION REVIEW REQUIRED**

This branch is reserved for the one-time import of the currently running Caddy configuration into Git control.

## Source

- Live path: `/etc/caddy/Caddyfile`
- Repository path: `config/Caddyfile`
- Import branch: `feat/import-live-caddy`
- Base branch: `development`

## Required import procedure

On the Caddy host:

```bash
cd /srv/caddy-controller
git fetch origin --prune
git checkout feat/import-live-caddy
git reset --hard origin/feat/import-live-caddy

./scripts/import-live-config.sh
./scripts/validate.sh
git diff --check
```

Before committing, review `config/Caddyfile` for inline credentials, tokens, private keys, stale routes, unintended public admin/metrics endpoints, insecure TLS workarounds, and incorrect upstreams.

Then commit only the reviewed configuration:

```bash
git add config/Caddyfile docs/LIVE-IMPORT-EVIDENCE.md
git commit -m "chore: import live Caddy configuration"
git push origin feat/import-live-caddy
```

## Evidence required before merge

- [x] Current `/etc/caddy/Caddyfile` and its `snippets/`, `sites/`, and `conf.d/` imports captured from the live host
- [x] No secrets/private keys committed; `private/` and `secrets/` are excluded from the import scope
- [x] `caddy fmt` clean
- [x] `caddy validate` passed against the complete imported configuration
- [x] Repository validation script passed
- [x] Routes and upstreams reviewed from the approved local host path
- [x] Caddy admin endpoint remains a Unix socket
- [x] No `tls_insecure_skip_verify` workaround introduced
- [x] Production deployment remained disabled during import; no reload or restart occurred
- [x] Imported file checksums match the live configuration after canonical formatting

## Promotion after import

`feat/import-live-caddy` → `development` → `test` → `staging` → `production` → `main`

Do not deploy this branch directly to production.
