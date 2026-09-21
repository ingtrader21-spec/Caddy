# Trusted Proxy Contract v1

## Scope

Caddy must protect the public edge from spoofed forwarded headers while preserving legitimate upstream trust semantics.

## Required protections

The forwarded-header contract must protect:

- `X-Forwarded-For`
- `X-Forwarded-Proto`
- `X-Forwarded-Host`
- `Forwarded`

Poisoning of these values by public clients must be denied or ignored unless the request arrived from an explicitly trusted proxy path.

## Contract intent

- Caddy is not the application identity authority.
- Caddy must not create or trust application user or role headers.
- Only a trusted edge/proxy chain may set forwarded identity or scheme information.
- Any public-client spoof attempt must fail closed.

## Repository alignment

This is consistent with the existing source behavior in the public hosts and with the repository’s explicit boundary between Caddy, Kong, Keycloak, and Middleware.
