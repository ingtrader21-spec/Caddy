# Caddy V3 API, URL, Webhook and Database Boundary Contract

## Authority rule

Caddy knows **where** traffic may go. Kong knows **who** may call which API.
Middleware knows **what** the request means and whether it may cause an effect.
PostgreSQL owns durable Middleware state.

Caddy is intentionally limited to host/path/method class, TLS/transport, body
ceilings, source-network restrictions, security headers, upstream selection,
failure behavior, and log redaction.

It must not implement customer, billing, CRM, workflow, provider, tenant,
idempotency, database-row, or command business logic.

## Machine-readable source

- `config/public-edge-registry.v1.json`
- `config/webhook-edge-registry.v1.json`
- `config/edge-contract-chain.v1.json`

The current `api.codestra.co` legacy catch-all remains explicitly
**TRANSITIONAL**. Certification must not claim `LEGACY_UNKNOWN_FALLBACK=0`
until that fallback is removed after route classification.

## Canonical public traffic

`/platform/v1/*` and `/v2/automation/*` are Kong-owned public namespaces.
Caddy never falls back directly to Middleware when Kong is unavailable.

Private namespaces `/internal/*`, `/metrics`, and `/metrics/*` are denied at
the public edge.

Database/control-plane destinations such as PostgreSQL, Redis, NATS,
Temporal, and OpenBao internal APIs are not valid public Caddy upstreams.

## Webhooks

Every public provider ingress must be registered before release. Caddy owns
the transport declaration only; HMAC, replay, idempotency, event-ledger and
business verification remain with Kong/Middleware as documented per entry.

Telnexa and VICIdial entries are presently marked transitional/pending because
their final routes are not in the current Middleware public-edge contract.

## Failure policy

Kong unavailable -> 502/503. No direct Middleware or legacy bypass.
Middleware unavailable -> 502/503. No secondary write path.

## Logging

Authorization, cookies, HMAC/API secrets, provider tokens, and sensitive
message bodies are not edge-log fields. Safe evidence includes provider,
path, status, duration, request/correlation ID, and body size.

## Digest chain

`config/edge-contract-chain.v1.json` records the accepted upstream authorities
that the edge is certified against:

| Link | Pin |
|---|---|
| Middleware source | `2862af0aa97367b18cb360af69212abe4243a1ac` |
| Middleware public contract | `9c32daecd4a15104c6f9ff60ce19c8f7e78707fb31d9fd9fcb55b1b8dfa3512b` |
| Kong protected main | `3e68cb2a4955bd71ddb3e839f4d9e3770465fc08` |
| Kong Middleware contract | `9c32daecd4a15104c6f9ff60ce19c8f7e78707fb31d9fd9fcb55b1b8dfa3512b` (`status: PASS`) |
| Postman collection | sha256 of the committed collection bytes (LF line endings) |

`MIDDLEWARE_KONG_CADDY_DIGEST_CHAIN=PASS` means the Middleware digest, the
digest Kong pins, and the digest Caddy requires are the same value, and the
Kong side records the protected head that carries it. The Caddy source, edge
contract and configuration digests are filled in at certification time from
the exact head; they are never self-referenced from source.

A passing digest chain does not retire the transitional legacy fallback and
does not claim `UNKNOWN_ROUTE_FALLBACK=0`.

## Production exit counters

The edge is not production-complete until all unclassified public routes,
webhooks, upstreams, and the generic legacy API fallback are zero.
