# Unified Intake Edge Contract

Canonical request path:

`website/landing-page/chat/voice -> same-origin BFF -> Caddy -> Kong -> Middleware -> durable inbox/outbox -> Odoo`

Caddy responsibilities are deliberately narrow:

- terminate public HTTPS/TLS for `api.codestra.co`;
- apply shared edge security headers and body ceiling;
- forward `/v1/intake*` to the configured Kong upstream;
- preserve the public host for Kong host-based routing;
- forward the real client IP;
- redact authorization/API-key material from access logs.

Caddy MUST NOT perform lead authorization, tenant authorization, CRM writes, campaign routing, or direct Odoo routing. Kong owns API gateway policy. Middleware owns business validation, durable event identity, idempotency and cross-system write authority.

No runtime deployment or activation is authorized by this file.
