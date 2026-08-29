# Caddy Communications Platform Authority

## Purpose

This document defines the permanent role of `appolon1908-hue/Caddy` in the Codestra communications platform.

Caddy is the principal public TLS edge and reverse-proxy authority. It is not an application API, identity provider, API authorization engine, communications runtime, SDK authority, orchestration engine, or cross-system write authority.

## Permanent request path

```text
Internet / external client
        -> Caddy
        -> Kong
        -> Middleware
        -> principal provider/runtime repository
```

Examples of downstream provider/runtime authorities:

- email: `appolon1908-hue/klyrow.com` -> Postal/Mautic
- SMS: `appolon1908-hue/telnexa` -> Jasmin/SMPP
- voice: `appolon1908-hue/Vicidialer-Codestra` -> VICIdial/Asterisk
- CRM/business state: `appolon1908-hue/Odoo`
- social: `appolon1908-hue/social.codestra.co`
- crawler: `appolon1908-hue/kyqra-crawler`

Developer-facing contracts and SDKs remain in `appolon1908-hue/SDK-repository`. Cross-product communications architecture and coordination documentation may live in `appolon1908-hue/communication-platform-`, but neither repo may become a second Caddy runtime authority.

## Caddy owns

Caddy owns shared edge concerns only:

- TLS termination and certificate lifecycle configuration;
- public host selection;
- HTTPS enforcement;
- reverse-proxy handoff to Kong or explicitly reviewed private ingress;
- HTTP request-body limits at the edge;
- shared security headers;
- access-log redaction and edge logging policy;
- public/private ingress separation;
- private source-IP allowlists where appropriate;
- mutual-TLS enforcement for explicitly private provider callback paths;
- canonical host preservation for Kong;
- edge health and validation checks;
- reload, rollback and release evidence for Caddy configuration.

## Caddy must not own

Caddy must never become responsible for:

- user or service authentication logic;
- issuing or transforming identity;
- application role/scope decisions;
- tenant authorization;
- communications send policy;
- email/SMS/voice business rules;
- idempotency ledgers;
- provider retries or reconciliation;
- application webhooks or workflow orchestration;
- Postal, Jasmin, VICIdial, Odoo or provider credentials;
- SDK/OpenAPI/AsyncAPI business contracts;
- cross-system state mutation.

Those responsibilities belong to Keycloak, Kong, Middleware, SDK-repository, n8n and the owning provider/product repositories.

## Caddy -> Kong rule

Every public communications API path that is represented by Kong must use:

```text
Caddy -> Kong -> Middleware
```

Caddy must not introduce a direct public route such as:

```text
Caddy -> Middleware
Caddy -> Postal
Caddy -> Jasmin
Caddy -> VICIdial
Caddy -> Odoo
Caddy -> n8n privileged write endpoint
```

for a privileged cross-system mutation.

Temporary migration fallbacks may exist only when explicitly documented, bounded, tested, and scheduled for removal after Kong parity is proven.

## Identity handling

Caddy does not validate application JWT semantics and does not mint trusted application identity headers.

Caddy must:

- preserve the bearer token for Kong on API paths;
- preserve the canonical host expected by Kong route contracts;
- strip or reject spoofable trusted headers when required by the reviewed gateway contract;
- redact sensitive authorization material from logs without deleting it from the forwarded request;
- keep browser forward-auth and private callback paths explicitly separated from API bearer-token flows.

Keycloak owns token issuance. Kong owns gateway authentication, audience/scope/route policy and rate limits. Middleware revalidates privileged authorization and tenant context before cross-system execution.

## Private communications callbacks

Provider callbacks that require private ingress may use Caddy as the mTLS edge when the route is explicitly designed for that purpose.

Examples include email delivery events or telephony events.

Private callback requirements:

1. dedicated host/path;
2. mutual TLS where required;
3. explicit source policy;
4. request-size limits;
5. sensitive-header/log redaction;
6. no public fallback route;
7. forwarding only to the reviewed private Middleware ingress;
8. application-level signature/replay validation remains the responsibility of Middleware/provider contract where applicable.

mTLS at Caddy does not replace Middleware event authentication, replay protection, tenant validation, inbox persistence or idempotency.

## Communications route families

The exact public path names are owned by the versioned Kong/API contracts, but Caddy must support the following architectural families without implementing their business behavior:

- communications message submission and status reads;
- email sender/domain administration where publicly exposed;
- templates and approved communications configuration;
- webhook management;
- delivery/event ingestion where explicitly public;
- SDK/API documentation endpoints if exposed;
- operator/admin routes only when the gateway contract permits them.

Caddy configuration must not infer provider-specific authorization or route dynamically based on user input.

## Security rules

1. Never expose Caddy Admin API publicly. Keep it loopback-only.
2. Never commit TLS private keys, ACME state, passwords, tokens or `.env` secrets.
3. Never manufacture trusted application identity headers.
4. Preserve API bearer tokens to Kong.
5. Redact secrets from logs.
6. Fail closed on malformed or unknown private ingress where the route contract requires strict host/path matching.
7. Do not permit arbitrary upstream selection from request input.
8. Do not proxy privileged API writes around Kong/Middleware.
9. Validate the complete Caddy configuration before reload.
10. A failed validation must leave the current live configuration unchanged.
11. Production reload requires separate approval from Git merge.
12. Record source SHA/config checksum for every promoted release.

## Environment model

Recommended repository promotion flow:

```text
feature/*
   -> development
   -> test
   -> production
   -> main
```

No environment branch automatically authorizes a live reload.

The infrastructure repository may define deployment automation, inventory, host expectations, monitoring and recovery requirements, but the actual shared Caddy configuration remains owned here.

## Required tests before communications cutover

Before a communications API family is enabled through Caddy, prove at minimum:

- valid TLS and expected hostname routing;
- HTTP -> HTTPS behavior where applicable;
- Caddy sends the route to the expected Kong listener;
- canonical Host is preserved;
- valid bearer credentials can reach Kong;
- invalid/missing credentials are rejected by the security chain;
- request-body limits behave as designed;
- sensitive headers are not leaked to logs;
- private callback paths reject non-mTLS clients when mTLS is required;
- direct public access to private provider/runtime listeners remains impossible;
- Caddy cannot bypass Middleware for a privileged communications mutation;
- rollback restores the prior reviewed config.

## Cross-repository release evidence

A communications cutover involving Caddy must record exact accepted source identities for at least:

- Caddy;
- Kong;
- Keycloak where identity contracts changed;
- Middleware;
- SDK-repository where the public contract changed;
- the applicable provider runtime such as Klyrow, Telnexa or VICIdial connector;
- infrastructure/deployment source where host configuration changed.

A green Caddy configuration check proves edge syntax/behavior only. It does not prove the entire communications platform is production-ready.

## Current documentation status

This document changes repository governance only. It does not authorize or perform a Caddy reload, DNS change, certificate replacement, Kong route activation, Middleware capability activation, email delivery, SMS delivery or PSTN dialing.
