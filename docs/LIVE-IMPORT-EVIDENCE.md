# Live Caddy Import Evidence

Status: **AWAITING LIVE SERVER CONFIGURATION**

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

- [ ] Current `/etc/caddy/Caddyfile` captured from the live host
- [ ] No secrets/private keys committed
- [ ] `caddy fmt` clean
- [ ] `caddy validate` passed
- [ ] Repository validation script passed
- [ ] Routes and upstreams manually reviewed
- [ ] Caddy admin endpoint remains private
- [ ] No `tls_insecure_skip_verify` workaround introduced
- [ ] Production deployment remains disabled during import
- [ ] Git diff matches the intended live configuration

## Promotion after import

`feat/import-live-caddy` → `development` → `test` → `staging` → `production` → `main`

Do not deploy this branch directly to production.
