# Observability URL boundary

## Allowed edge routes

The repository may render only these observability/security sites:

| Public host | Upstream authority | Protection |
|---|---|---|
| `graf.codestra.media` | Grafana private listener | Native Keycloak OIDC and Grafana RBAC |
| `supe.codestra.media` | Superset private listener | Native Keycloak OIDC and Superset RBAC |
| `bao.codestra.media` | OpenBao private listener | Source-network allowlist, native Keycloak OIDC, and OpenBao policy |

The Caddy source preserves `Authorization` for native application authentication, strips spoofable identity headers, bounds request size and upstream timeouts, supports streaming/WebSocket upgrades, applies browser security headers, and redacts credentials and OIDC parameters from access logs.

## Private-only services

Prometheus, Alertmanager, Loki, Tempo, OpenTelemetry, Alloy, Node Exporter, cAdvisor, PostgreSQL Exporter, Redis Exporter, and Blackbox Exporter have no public Caddy site. Retained short names are private DNS/admin-plane names only. `pgex.codestra.media` is prohibited as a public DNS hostname and is not rendered even as a public denial page.

Unknown or private-only observability hostnames therefore do not match any site in this repository. This is stronger than issuing a public certificate and returning `403`.

## Repository validation

`scripts/validate_observability_exposure.py` cross-checks the machine contract, every Caddy site, runtime validation values, security headers, activation flags, and the committed configuration checksum. Its negative tests prove private-route, PostgreSQL Exporter hostname, broad OpenBao CIDR, authorization-header, and live-reload drift fail closed.

Exact-head and merge-result CI use the immutable Caddy validator image `docker.io/library/caddy@sha256:ae4458638da8e1a91aafffb231c5f8778e964bca650c8a8cb23a7e8ac557aa3c` to check formatting, adapt the complete root config, and validate it without a network.

## Activation and rollback

A protected merge does not authorize DNS, certificate issuance, or a Caddy reload. The later server mission must verify private upstream listeners and health, the applied Keycloak state, source-network ranges, current active Caddy checksum, backup integrity, and explicit owner authorization.

Before any later reload, retain the prior protected Caddy source SHA, prior complete rendered-config checksum, and the server’s current recoverable configuration backup. Rollback restores that exact prior config, validates it with its accepted Caddy digest, reloads only with approval, and verifies the previous health/route matrix. No prior production value is guessed in this repository change.
