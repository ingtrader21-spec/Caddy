# Security Header Profiles v1

## Shared edge policy

The canonical shared header profile resides in `snippets/security_headers.caddy` and is imported by all public site blocks. This ensures the HSTS and hardening profile is not accidentally omitted when a host is added.

## Active headers

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

## Policy notes

- Browser policy is applied intentionally and without broadening the app trust boundary.
- API and WebSocket traffic classes are not given a blanket rule-set that would duplicate gateway-level policy.
- Header policy is centralized to avoid drift and silent omission.
