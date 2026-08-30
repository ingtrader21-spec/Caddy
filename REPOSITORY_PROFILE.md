# Repository Profile — `Caddy`

## Identity

- **Repository:** `appolon1908-hue/Caddy`
- **Category:** Platform edge — TLS and reverse proxy
- **Visibility:** `public`
- **Default branch:** `main`
- **Authority:** Primary public edge, TLS, hostname-routing, and reverse-proxy authority
- **Status:** Active GitOps source; live validation and reload remain separate approved operations.

## Purpose

Terminates TLS, redirects HTTP, applies edge headers and access controls, redacts sensitive logs, and routes public hostnames to private Kong or approved service upstreams.

## Owns

- Caddyfile source, site imports, snippets, host routing, TLS/ACME, and edge headers
- Public/private hostname exposure decisions and reverse-proxy upstream contracts
- Edge configuration validation, backup, reload, smoke-test, and rollback procedures

## Does not own

- Kong API routes, plugins, or application policies
- Keycloak realm or application authorization state
- Native service exposure without an explicitly approved edge route

## Key integrations

- Kong
- Keycloak-aware upstreams
- Public product websites
- Authenticated Grafana, Superset, and restricted OpenBao access

## Current priorities

1. Complete and review observability edge routing
2. Keep internal observability hostnames controlled with 403/404 responses
3. Validate formatting, configuration, upstream health, certificates, and rollback before reload
4. Maintain log redaction, private upstream binds, and no-fallback routing

## Governance and safety

- Promotion model: `feature/docs/fix/security/upgrade -> development -> test -> staging -> production -> main`.
- Use pull requests and exact-head/merge-result validation; merge never reloads the live edge.
- Never commit private keys, DNS credentials, access tokens, customer data, or secret-bearing logs.
- Every production reload requires accepted source, rendered-config validation, backup, smoke tests, and rollback readiness.
- This document does not issue certificates, alter DNS/firewalls, expose services, reload Caddy, or change production traffic.

## Account-wide catalog

See `appolon1908-hue/documentaions/REPOSITORY_CATALOG.md`.
