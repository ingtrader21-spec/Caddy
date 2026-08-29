# Observability and Secrets Edge Routing

## Scope

This document governs the `codestra.media` observability/security host family after DNS creation. DNS resolution alone does not authorize reverse-proxy exposure, authentication changes, certificate issuance, or service deployment.

All 14 A records resolve to `37.27.128.39` with TTL 600:

```text
graf  prom  aler  loki  temp  otel  supe
node  cadv  pgex  rdex  blac  allo  bao
```

## Exposure decision

### Browser-facing through Caddy

| Host | Service | Required protection |
|---|---|---|
| `graf.codestra.media` | Grafana | Native Keycloak OIDC, service RBAC, private upstream |
| `supe.codestra.media` | Superset | Native Keycloak OIDC, service RBAC, curated read-only data sources |
| `bao.codestra.media` | OpenBao UI/API | Network allowlist, native Keycloak OIDC, OpenBao policy enforcement, private upstream |

Caddy terminates TLS and proxies only to loopback/private listeners. The corresponding native service ports must not be open publicly.

### Private-only

The following hostnames may have public DNS but must not expose their native services through Caddy:

```text
prom.codestra.media
aler.codestra.media
loki.codestra.media
temp.codestra.media
otel.codestra.media
node.codestra.media
cadv.codestra.media
pgex.codestra.media
rdex.codestra.media
blac.codestra.media
allo.codestra.media
```

Public HTTPS requests receive a controlled `403`. Approved private clients should reach the native service over the private VLAN, loopback, or a private Docker network.

## Authentication boundary

Caddy does not manufacture trusted user headers and does not replace application authorization.

- Grafana authenticates through its reviewed Keycloak client.
- Superset authenticates through its reviewed Keycloak client.
- OpenBao authenticates through its reviewed Keycloak OIDC method and retains OpenBao policy enforcement.
- Keycloak client secrets are injected externally and never committed here.
- Authorization and cookies are removed from Caddy access logs.

## Runtime values

Required non-secret environment variables:

```text
CADDY_GRAFANA_UPSTREAM
CADDY_SUPERSET_UPSTREAM
CADDY_OPENBAO_UPSTREAM
CADDY_OPENBAO_ALLOWED_CIDR_1
CADDY_OPENBAO_ALLOWED_CIDR_2
```

The source includes fail-closed defaults for local/private listeners. Review live listeners before deployment; do not assume the defaults match the server.

## Validation before any reload

1. Check out the exact accepted commit.
2. Set non-secret upstream values for the target environment.
3. Run `caddy fmt --diff Caddyfile` and format any changed Caddy source.
4. Run `caddy validate --config Caddyfile --adapter caddyfile`.
5. Verify `graf`, `supe`, and `bao` upstreams bind only to loopback/private interfaces.
6. Verify ports for Prometheus, Alertmanager, Loki, Tempo, OpenTelemetry, exporters, and Alloy are unreachable from the Internet.
7. Verify Keycloak clients exist but do not reveal credentials.
8. Verify unauthenticated Grafana/Superset requests enter their OIDC flows.
9. Verify OpenBao requests outside the approved source networks receive `403`.
10. Back up the active Caddy configuration and rehearse rollback.

## Smoke-test matrix

```text
https://graf.codestra.media  -> valid TLS, OIDC login, Grafana only
https://supe.codestra.media  -> valid TLS, OIDC login, Superset only
https://bao.codestra.media   -> valid TLS; unapproved source receives 403
private hostnames            -> valid TLS and controlled 403; no native UI/API
```

Also confirm:

- host confusion does not route one service to another;
- security headers are present;
- authorization/cookie values do not appear in logs;
- certificate names match each hostname;
- a failed validation leaves the running Caddy process unchanged.

## Activation gate

A merge does not authorize a Caddy reload. Production activation requires exact-source validation, accepted Keycloak configuration, firewall evidence, upstream health, rollback evidence, and explicit approval.
