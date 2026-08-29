# Canonical Caddy configuration

The active configuration path in this repository is:

`config/Caddyfile`

The branch defines the environment (`development`, `test`, `staging`, or `production`). Do not create separate environment Caddyfiles in this directory. Promote the same reviewed configuration through the branch chain.

The file is intentionally absent during controller bootstrap. Use `scripts/import-live-config.sh` for the first import from the existing Caddy server. Import applies and validates the mandatory observability contract:

- the Caddy admin API remains bound to `127.0.0.1:2019`;
- global metrics collection is enabled;
- metrics are exposed only on the container/private-network listener `:2020/metrics`;
- `:2020/healthz` is available for private readiness checks;
- port 2020 must not be published through the host firewall, public Caddy sites, or Kong.

The runtime/deployment authority must attach Caddy to the external private Docker network `codestra-observability` with alias `caddy`. Prometheus owns scraping and labels; this repository owns the Caddy listener. See `docs/PROMETHEUS_METRICS.md`.
