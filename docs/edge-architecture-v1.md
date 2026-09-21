# Edge Architecture v1

## Canonical control plane

```text
Internet
   |
   v
Caddy (public ingress / TLS / edge security)
   |
   v
Kong (gateway policy / JWT / route control)
   |
   v
Middleware (privileged authorization / write boundary)
   |
   v
Downstream service
```

## Architectural principles

1. Caddy is not an identity provider.
2. Caddy does not authorize business actions.
3. Caddy preserves the bearer token and canonical host for the gateway.
4. Caddy rejects unknown hosts/paths via fail-closed policy.
5. Legacy fallback listeners are explicit migration support only.
6. Canonical contracts are pinned in JSON and validated by Python checks.

## Freeze gate

CADDY MISSION 1 — EDGE FOUNDATION:
IMPLEMENTATION COMPLETE — RUNTIME CERTIFICATION PENDING
