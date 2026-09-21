# Reverse Proxy Contract v1

## Canonical behavior

Caddy is the public ingress and transport boundary. Kong remains the API gateway behind it, and Caddy routes only to approved upstreams.

## Required contract fields

- upstream identity
- protocol classification (`HTTP`, `HTTPS`, `mTLS`)
- dial timeout
- response timeout
- keepalive policy
- health behavior
- forwarded headers
- TLS expectations
- WebSocket behavior
- streaming behavior
- failure behavior

## Repository posture

- managed API routes are intentionally forwarded to `CADDY_KONG_UPSTREAM`
- the legacy listener remains a transitional fallback only
- `Host` and `X-Real-IP` are preserved at the edge boundary
- no Caddy-managed direct Middleware or provider target is allowed for the Kong-managed route family

## WebSocket and streaming expectations

- long-lived connections are allowed when the traffic class requires them
- standard API timeout assumptions must not be applied blindly to WebSocket or SSE traffic
- real-time routes must remain classified and auditable, not silently treated as generic HTTP responses

## Failure behavior

When an upstream is unavailable, unhealthy, or misconfigured, the edge must fail closed and not silently redirect to an untrusted backend or hidden legacy bypass.
