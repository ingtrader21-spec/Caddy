# Canonical Caddy configuration

The active configuration path in this repository is:

`config/Caddyfile`

The branch defines the environment (`development`, `test`, `staging`, or `production`). Do not create separate environment Caddyfiles in this directory. Promote the same reviewed configuration through the branch chain.

The file is intentionally absent during controller bootstrap. Use `scripts/import-live-config.sh` for the first import from the existing Caddy server.
