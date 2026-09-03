# Caddy Single Production Authority V2

## Current authority

This branch starts from current `development@1f3f40babe1f86f0aa680ec524d05fdea6cb0cb8`. It replaces the dirty, divergent PR #57 rather than resolving that branch by silently discarding current development governance or reintroducing the obsolete `candidate/` deployment tree.

## Required outcome

`config/` is the only deployable Caddy source tree. The canonical entry is `config/Caddyfile`. Root-level, `candidate/`, duplicate `sites/` or duplicate `snippets/` configuration trees are prohibited.

The resulting authority must preserve all current development routes and controls while incorporating the still-valid security, observability, immutable-release, staging-certification, runtime-readback and rollback work from PR #57.

## Canonical edge model

```text
public client
  -> Caddy TLS/reverse proxy
  -> Kong authentication, authorization, rate limits and route policy
  -> Middleware or owned downstream service
```

Caddy may not become an identity provider, business API, provider dispatcher or alternate Middleware bypass.

## Route requirements

- `api.codestra.co` routes every accepted API family to Kong.
- The unrestricted legacy API catch-all is prohibited.
- Temporary realtime/status fallbacks are explicitly enumerated, method constrained, labeled and default-deny.
- Unknown paths return 404.
- `automation.codestra.co` is source-CIDR gated, strips spoofable identity headers and routes to Kong for Keycloak browser authorization while retaining native n8n authentication behind Kong.
- Public routes may not expose Middleware private operations, Odoo command endpoints, n8n native administration, Prometheus, Alertmanager, Loki, Tempo, OpenTelemetry Collector, Alloy, exporters, databases or Caddy metrics.

## Security and redaction

Use one centralized security-header and access-log filter authority. Every access log must redact or delete credential-bearing request/response fields and query parameters, including Authorization, Proxy-Authorization, Cookie, Set-Cookie, API keys, Vault tokens, OAuth codes/state/tokens and client secrets.

Require HSTS, content-type protection, framing protection, bounded request bodies, TRACE/CONNECT denial, reviewed upstream timeouts and no unverified upstream TLS.

## Observability

- Caddy metrics bind privately or to loopback only.
- Grafana, Superset and any approved OpenBao UI require native SSO and/or source-CIDR protection.
- Prometheus, Alertmanager, Loki, Tempo, OpenTelemetry Collector, Alloy, Node Exporter, cAdvisor, Postgres Exporter, Redis Exporter, Blackbox Exporter and Caddy metrics have no public host.
- `pgex.codestra.media` remains prohibited.
- Runtime readback must prove the effective listener, route, module, log-redaction and metrics exposure state.

## Immutable runtime

The image and runtime must be bound to:

```text
exact protected source SHA
exact configuration-tree SHA-256
immutable image digest
OCI source/revision labels
non-root UID/GID
read-only root filesystem
minimal capabilities
no-new-privileges
health/readiness checks
previous exact rollback digest
```

A source merge is not deployment.

## Staging certification

Create a workflow-dispatch-only protected staging path that:

- accepts only the exact merged protected SHA and image digest;
- deploys without rebuilding or retagging;
- validates the complete configuration before replacement;
- exercises route ownership, security headers, redaction, HTTP/2, HTTP/3 where supported, WebSocket upgrade, readiness, private metrics and public-denial tests;
- performs no business write;
- records a credential-free evidence artifact;
- supports rollback to the previous exact digest and configuration checksum.

## Production read-only canary

The later production canary is limited to at most one percent of GET/HEAD-only traffic. Stop and roll back on source/digest mismatch, readiness or monitoring loss, unexpected listener/route drift, write request, credential leakage, latency/error regression or live-effect counter movement.

## Required source integration from old PR #57

Port only still-valid work from the old branch after adapting it to current development:

- immutable release and attestation gates;
- fixed-container runtime readback;
- staging certification;
- production read-only canary;
- restore/rollback rehearsal;
- exact configuration digest;
- private Caddy metrics;
- complete credential redaction;
- explicit fallback manifest;
- single-authority validator.

Do not port:

- `candidate/` as a deployable or validated source;
- workflows that validate `candidate/Caddyfile`;
- stale versions of route files already corrected in development;
- duplicate runtime validators;
- mutable image/tag deployment;
- public observability endpoints;
- source-side authorization to reload production.

## Required CI

- Caddy format and validate against `config/Caddyfile` only;
- single-source authority validator;
- Caddy/Kong route-contract parity;
- dangerous-node and editor-protection tests;
- security header and complete redaction tests;
- immutable Compose render;
- disposable edge certification;
- rollback rehearsal;
- HTTP/2, WebSocket and HTTP/3 protocol tests where supported;
- secret scan, SBOM, provenance and HIGH/CRITICAL vulnerability policy;
- exact-head and synthetic merge-result gates;
- `git diff --check`.

## Safety

```text
CADDY_RUNTIME_RELOADED=false
DNS_CHANGED=false
TLS_CHANGED=false
LIVE_TRAFFIC_CHANGED=false
PRODUCTION_CHANGED=false
```

No server, DNS, certificate, firewall, route, secret, container or production runtime is modified by this branch. Runtime staging and canary remain separately protected.