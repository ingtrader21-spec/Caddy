# Production lineage reconciliation — 2026-09-03

## Purpose

Reconcile the prior protected production release lineage into the current canonical development authority without force-updating any branch and without reverting the certified runner, Compose, release, or safety controls.

## Parent authorities

- current canonical development parent: `24c5e596678ab46ef1f00bde45d26c974f46ec62`;
- prior signed production parent: `4e365f659fc752cb06f9b3d4789715dabfe2f296`;
- prior signed production image: `ghcr.io/appolon1908-hue/codestra-caddy@sha256:72621218da8de41ffb57700de5a770ee8f619fec6b941e71b7180aa85e188c19`;
- prior production configuration SHA-256: `229ad5168724cfbe10bd3f8b90b8300f30383b3cde2743fbfa239fa143b33ee1`.

The reconciliation commit has both source commits as parents and retains the canonical development tree. This records the previously signed production authority in the ancestry consumed by the normal promotion chain:

```text
feature reconciliation -> development -> test -> staging -> production
```

## Preserved authority

The resulting tree continues to require:

- `config/` as the single deployable Caddy configuration tree;
- `deploy/compose.runtime.yaml` as the sole Caddy Compose runtime;
- the exact-source and synthetic-merge CI gates;
- immutable image build, scan, SBOM, provenance, signature, and source attestation;
- network-isolated current-candidate bind proof;
- signed historical rollback proof with serialized port preflight and listener cleanup;
- `[self-hosted, codestra-staging]` with `staging-readonly`;
- `[self-hosted, codestra-production-canary]` with `production-readonly-canary`;
- exact staging evidence identity before the production read-only canary.

## No-live-effects boundary

This lineage operation performs no Caddy deployment or reload and changes no live container, DNS, firewall, SSH, certificate ownership, route, public traffic, credential, or unrelated workload. Any later production promotion must rebuild and sign the exact resulting production SHA and must fail closed unless bounded staging and the production read-only canary both return machine-readable PASS evidence.
