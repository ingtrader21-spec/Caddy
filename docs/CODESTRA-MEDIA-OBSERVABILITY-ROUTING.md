# Caddy Routing Plan — codestra.media Observability Stack

## DNS

All listed hosts resolve to `37.27.128.39` with TTL 600. DNS presence does not imply public service exposure.

## Public browser-facing routes

Only these hostnames receive normal browser HTTPS reverse-proxy routes:

### `graf.codestra.media`
Purpose: Grafana operational dashboard.
Requirements:
- automatic/public TLS certificate;
- HTTPS only;
- authenticated access before/at Grafana according to approved identity design;
- security headers;
- request/body limits appropriate to Grafana;
- WebSocket support if required by Grafana features;
- upstream bound on loopback/private network, never public service port;
- redact Authorization/cookie values from access logs.

### `supe.codestra.media`
Purpose: Superset business analytics.
Requirements:
- HTTPS only;
- authenticated access;
- secure proxy headers and correct forwarded scheme/host;
- CSRF/session compatibility;
- upstream private/loopback only;
- security headers and sensitive-header log redaction.

### `bao.codestra.media`
Purpose: protected OpenBao UI/API where explicitly allowed.
Requirements:
- HTTPS only;
- strongest access restriction of the three browser routes;
- prefer VPN/private-IP allowlist and/or strong identity gate in addition to OpenBao auth;
- never expose root-token/bootstrap workflows through public automation;
- upstream OpenBao listener remains private;
- do not log tokens, secret paths with sensitive identifiers, request/response bodies, or cookies;
- disable or block unauthenticated administrative paths as architecture permits.

## DNS-only/private hostnames

Do **not** create general public reverse-proxy routes for:

- `prom.codestra.media`
- `aler.codestra.media`
- `loki.codestra.media`
- `temp.codestra.media`
- `otel.codestra.media`
- `node.codestra.media`
- `cadv.codestra.media`
- `pgex.codestra.media`
- `rdex.codestra.media`
- `blac.codestra.media`
- `allo.codestra.media`

If Caddy is ever used for an internal-only TLS route for one of these hosts, the route must be protected by private-network/IP/mTLS policy and must not transform the service into a public endpoint.

## No-bypass rule

Caddy is TLS/edge routing authority only. It does not replace service authentication, OpenBao policy, Grafana/Superset RBAC, firewall policy, or monitoring-network restrictions.

## Certificate gate

Before enabling any browser route:
1. confirm DNS still resolves to the intended edge IP;
2. confirm ports 80/443 are reachable only as intended;
3. validate Caddy configuration offline;
4. obtain/validate certificate;
5. test upstream health from Caddy;
6. confirm direct upstream port is not public;
7. verify authentication and logout/session behavior;
8. confirm access logs redact sensitive headers;
9. record exact Caddy repo SHA and component repo SHA;
10. promote through development/test/staging before production.

## Initial route activation order

1. `graf.codestra.media`
2. `supe.codestra.media`
3. `bao.codestra.media` only after OpenBao policy/seal/bootstrap/access design is independently certified.
