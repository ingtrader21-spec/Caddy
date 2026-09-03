# Observability URL repository evidence

This is source evidence only; no DNS, runtime, certificate, or reload state was inspected or changed.

| Control | Evidence |
|---|---|
| Public routes | Exactly Grafana, Superset, and restricted OpenBao in `sites/codestra.media.observability.caddy` |
| Private services | No native service hostname may occur in any `sites/*.caddy` source |
| PostgreSQL Exporter | `pgex.codestra.media` public DNS and route both prohibited |
| Upstreams | Required environment variables with no inline defaults; validation examples are loopback-only |
| OpenBao | Documentation-only CIDRs in source example; broad ranges rejected; unmatched clients receive `403` |
| Authentication | Native application OIDC preserved; spoofable identity headers removed |
| Browser security | Shared headers plus HSTS on every permitted route |
| Streaming | Flush and stream timeout controls checked for every permitted route |
| Logs | Authorization, cookies, OIDC query material, response cookies, and OpenBao token headers redacted |
| Caddy parser | Immutable Caddy image runs format, adapt, and full-root validation in exact-head CI |
| Configuration checksum | `release/observability/caddy-observability-configuration.sha256` |
| Activation | DNS read/change, upstream verification, reload, and production cutover remain false |

Protected merge SHA and any prior production rollback digest remain unavailable until the protected process and later authorized runtime inventory complete. They are not fabricated here.
