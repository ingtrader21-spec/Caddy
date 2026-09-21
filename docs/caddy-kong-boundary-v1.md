# Caddy ↔ Kong Boundary v1

## Boundary contract

```text
client
  -> Caddy
  -> Kong
  -> Middleware
  -> owned downstream service
```

## Ownership responsibilities

- Caddy: TLS termination, host routing, request redaction, reverse-proxy handoff, safe ingress behavior.
- Kong: OIDC/JWT, scope, route, rate, and request policy.
- Middleware: authorization revalidation and write boundary.
- Keycloak: identity and token issuance.

## Repository enforcement

The contract is pinned in `config/caddy-kong-contract.v1.json` and validated by `scripts/validate_repository.py` and `scripts/caddy_kong_contract.py`.

## Forbidden patterns

- Direct Caddy -> Middleware for Kong-managed routes.
- Direct public upstream to n8n or to provider services for shared API traffic.
- Trusted application identity headers minted by Caddy.
- Authorization header forwarding outside the Kong handoff model.

## Supported state

The repository is intentionally configured to preserve the bearer token and canonical host while preventing any direct application identity creation in Caddy.
