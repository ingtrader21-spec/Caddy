# Caddy Prometheus metrics contract

Caddy owns metric collection and its private listener. `appolon1908-hue/Codestra-Prometheus` owns scraping, target labels, recording rules, alerts, and retention.

## Runtime contract

After the live Caddyfile is imported, `scripts/import-live-config.sh` invokes `scripts/ensure-observability-metrics.py`. The resulting canonical file contains:

```caddyfile
{
	admin 127.0.0.1:2019
	metrics
}

:2020 {
	metrics /metrics
	respond /healthz 200
}
```

The script is idempotent. It blocks an admin listener that is not `127.0.0.1:2019`, an existing conflicting `:2020` server, an incomplete generated block, and any canonical file missing the observability contract.

## Network policy

The deployment authority must:

1. create or reuse the external private network `codestra-observability`;
2. attach Caddy with network alias `caddy`;
3. expose port 2020 only to containers on that network;
4. never add a host `ports:` mapping for 2020;
5. never route `/metrics` or `/healthz` through a public Caddy site or Kong;
6. allow Prometheus to scrape `http://caddy:2020/metrics`.

## Validation

```bash
python3 scripts/test_observability_metrics.py
python3 scripts/ensure-observability-metrics.py --check config/Caddyfile
scripts/validate.sh
```

## Promotion evidence

Before promotion from staging, capture: formatted/validated Caddyfile; private network membership; a successful scrape from Prometheus; confirmation that public requests to port 2020 are refused; the Prometheus target labels `environment`, `server`, `application=edge`, `service=caddy`, and `tenant_scope=aggregate`; and a rollback test that restores the previous Caddy config without exposing the admin API.
