# Monitoring Boundary v1

## Boundary

Caddy may emit telemetry for monitoring consumption by systems such as:

- Prometheus
- Grafana
- Loki
- Alloy / OpenTelemetry

## Non-goals

- Caddy does not require Grafana to run.
- Caddy does not require Loki to run.
- Caddy does not require Prometheus to run.
- Caddy does not become the monitoring authority or business policy layer.

## Operational model

Monitoring consumes Caddy telemetry. Monitoring does not route traffic, enforce gateway policy, or alter business authorization rules.
