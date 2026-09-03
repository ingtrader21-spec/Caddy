# Caddy → Kong integration authority

`appolon1908-hue/Caddy` owns TLS termination, public host selection, request-size policy, shared security headers, sanitized access logs, and transport to the gateway. `appolon1908-hue/Kong` owns gateway authentication, authorization, scopes, rate limits, request policy, and gateway-to-Middleware routing. Keycloak issues identity; Middleware revalidates privileged commands and owns cross-system effects.

The required shared API path is:

```text
client → Caddy → Kong → Middleware → owned downstream service
```

The exact prefixes in `config/caddy-kong-contract.v2.json` are routed to `CADDY_KONG_UPSTREAM` on both `api.codestra.co` and the temporary `api.codestra.agency` compatibility host. The compatibility host rewrites the upstream Host header to `api.codestra.co`, ensuring Kong's host-bound routes remain authoritative.

There is no generic legacy upstream and no unrestricted catch-all. Only the explicit realtime/health paths in the contract may use `CADDY_REALTIME_UPSTREAM`. Every other unknown path returns `404`. Extending either set requires a reviewed contract change and exact bidirectional route validation.

Caddy must not create trusted `X-Authenticated-*` or gateway-secret headers. Browser-supplied identity headers are removed on administrative surfaces, while the incoming bearer token for Kong-managed API routes is preserved in transit and removed from logs.

A green source workflow does not authorize a live reload. Production acceptance additionally requires the signed image identity, actual-container read-back, real-network TLS/Kong/Keycloak checks, and rollback evidence described in `PRODUCTION-CERTIFICATION.md`.
