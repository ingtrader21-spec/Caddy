# Codestra Caddy Edge

This repository is the principal Git source for Codestra shared Caddy edge configuration, immutable release construction, validation, promotion, runtime read-back, and rollback evidence.

## Single authority

There is exactly one deployable configuration tree:

```text
config/Caddyfile
config/snippets/*.caddy
config/sites/*.caddy
config/conf.d/*.caddy
```

The image build, CI validation, immutable launcher, container validator, canary, and rollback controls all consume that same tree. There is no separate candidate configuration and no server-owned route authority.

## Unified Compose and CI

The sole Caddy runtime composition is:

```text
deploy/compose.runtime.yaml
```

It owns the fixed `codestra-caddy` service, immutable GHCR digest, source/configuration/release labels, non-root identity, read-only filesystem, capability boundary, health check, state mounts, and host-network listener model. Activation, rollback, rollback rehearsal, and CI all consume this exact file. No second Compose file may define the Caddy image, service, or container identity.

`deploy/community-n8n/compose.security.yaml` is a separate n8n security overlay and is not a Caddy runtime authority. CI fails if that overlay or any future Compose file introduces a competing Caddy service.

Both exact-source and synthetic-merge CI execute the unified-Compose authority test and render `deploy/compose.runtime.yaml` with the complete non-secret runtime contract before a release gate can pass.

## Manual one-click production orchestration

The operator entry point is `.github/workflows/manual-production-orchestrator.yml`.
After it reaches protected `main`, run it from the Actions tab to freeze the
current exact `production` SHA, verify the unified Compose and source gates,
adopt or rerun the exact signed-image workflow, deploy that immutable digest to
bounded staging, and execute the dependent production read-only canary.

The workflow validates the release, staging, rollback, and production-canary
artifacts before emitting `PASS`. Missing runner capacity, an expired artifact,
a source/image/configuration mismatch, failed signature or scan, failed staging
check, or changed production snapshot emits `NO_GO`. It does not bypass the
`staging-readonly` or `production-readonly-canary` environments and does not
directly replace the live Caddy container.

See [`docs/MANUAL-ONE-CLICK-PRODUCTION-ORCHESTRATOR.md`](docs/MANUAL-ONE-CLICK-PRODUCTION-ORCHESTRATOR.md).

## Request boundary

The governed shared API path is:

```text
client -> Caddy -> Kong -> Middleware -> owned downstream service
```

Caddy owns TLS termination, host selection, request limits, transport policy, security headers, and sanitized edge logs. Kong owns gateway authentication, authorization, scopes, rate limits, and route policy. Keycloak owns identity and token issuance. Middleware owns privileged cross-system commands and provider effects.

Known shared API paths on both `api.codestra.co` and the legacy compatibility host are handed to Kong. Only the explicitly contracted realtime/health paths may use `CADDY_REALTIME_UPSTREAM`; every unknown path returns `404`. An unrestricted legacy API fallback is prohibited.

## Immutable runtime

Production uses only:

```text
ghcr.io/appolon1908-hue/codestra-caddy@sha256:<approved-digest>
```

The release pipeline builds the patched Caddy binary, records the upstream source and module overrides, scans for HIGH/CRITICAL vulnerabilities, tests non-root privileged-port binding, runs an isolated edge canary, emits SBOM and provenance, signs the binary attestation and image digest, and uploads release evidence.

The production container is fixed as `codestra-caddy`, runs as UID/GID `65532`, has a read-only root filesystem, drops all capabilities except `NET_BIND_SERVICE`, and uses host networking so reviewed public/private binds remain explicit. `scripts/caddy_readonly_validator.py` validates the actual container, image digest, OCI labels, configuration hash, environment contract, modules, listeners, health, and effective Caddy configuration without printing raw configuration or secret values.

## Promotion

All accepted work follows:

```text
feature|fix|chore|docs|refactor -> development -> test -> staging -> production -> main
```

The repository defines exact-head, synthetic merge-result, promotion-chain, and immutable-release checks. The declarative branch ruleset is `config/github/protected-branches-ruleset.json`; it has no bypass actors and prohibits deletion and non-fast-forward updates.

## Runtime activation and rollback

A source merge never authorizes a live reload. Before activation, the operator must verify the exact protected production SHA and signed image digest, preserve the current release as the rollback baseline, validate the complete image configuration, and run the bounded canary. `scripts/run-immutable-runtime.sh` fails closed and invokes the immutable rollback path if the new container does not become healthy. `scripts/rollback-runtime.sh` accepts no arguments and restores only the signed digest recorded in `config/release-baseline.v1.json`.

SSH configuration, firewall policy, DNS ownership, unrelated workloads, and application secrets are outside this repository and must not be changed by a Caddy release.
