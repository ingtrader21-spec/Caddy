# Caddy Repository Agent Guide

## Repository role

This repository owns the public Codestra Caddy edge: TLS termination, canonical public hostnames, security headers, request limits, access-log redaction, mTLS private ingress, the Caddy-to-Kong handoff, the immutable custom Caddy image, the unified production Compose service, bounded runtime certification, protected activation, and rollback evidence.

It does not own application business logic, Keycloak realm administration, Kong route administration, DNS-provider credentials, production secrets, or application-write authorization.

## Layout

- `config/Caddyfile` is the only root Caddy configuration.
- `config/conf.d/` contains global options, redirects, and shared internal listeners.
- `config/snippets/` contains reusable transport, security, and sanitized logging policy.
- `config/sites/` contains one file per canonical public host or tightly related host group.
- `contracts/` contains the explicit Caddy-to-Kong route contract.
- `deploy/compose.runtime.yaml` is the only production Compose authority.
- `scripts/` contains source validation, immutable build, runtime readback, baseline capture, activation, canary, rollback, and evidence tools.
- `.github/workflows/manual-production-orchestrator.yml` is the only production deployment entrypoint.
- `.github/workflows/immutable-release.yml` and `.github/workflows/bounded-runtime-certification.yml` are reusable gates called by the orchestrator.
- `tests/` contains source, isolation, protocol, redaction, runner, orchestration, and rollback contract tests.
- `docs/` contains routing, security, release, recovery, and evidence documentation.

Do not create another deployable Caddy tree, root `Caddyfile`, Dockerfile, production Compose file, or host-systemd runtime authority.

## Validation commands

Run before every commit:

```bash
bash scripts/validate-ci.sh
```

Focused commands include:

```bash
python3 scripts/validate_repository.py
python3 scripts/verify_caddy_kong_contract.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

A green source check is not runtime evidence.

## Configuration rules

- Keep reusable security, transport, and logging policy in snippets.
- Every access log must import `sanitized_access_log`.
- Route known shared API families through the Kong boundary.
- Keep unknown API routes fail-closed.
- Preserve explicit realtime exceptions only where the contract names them.
- Never add an unrestricted legacy Middleware fallback.
- Keep internal admin and metrics listeners private.
- Prefer exact host matchers and explicit path families over broad catch-all behavior.

## Runtime and release rules

- Use only `deploy/compose.runtime.yaml` for production Caddy.
- Require exact source SHA, `image@sha256:...`, configuration SHA-256, and release ID.
- Never use `latest`, mutable release tags, `docker compose build`, or retagging during deployment.
- Build the custom binary through the pinned upstream/module authority.
- Require non-root execution, read-only root filesystem, dropped capabilities except `NET_BIND_SERVICE`, and `no-new-privileges`.
- Verify signature, source attestation, OCI source/revision labels, configuration label, listeners, modules, process ownership, health, and sanitized logging against the actual container.
- Keep runtime state and private trust material outside Git with the ownership and mode checks enforced by the scripts.

## Manual production orchestration

Production deployment is manual-only. The operator performs one `workflow_dispatch` of `.github/workflows/manual-production-orchestrator.yml` against the exact protected `production` ref. The workflow accepts no free-form deployment inputs.

The fixed sequence is:

1. prove exact protected production SHA and staging ancestry;
2. prove protected environment policy and required successful source checks;
3. build, scan, sign, attest, and publish the exact immutable image;
4. preserve SBOM, provenance, canary, and historical rollback evidence;
5. deploy and certify the exact tuple on `staging-readonly` using `codestra-staging`;
6. require the staging evidence hash before `production-readonly-canary` using `codestra-production-canary`;
7. require byte-identical live-runtime snapshots and no writes or live changes;
8. capture the current healthy production source/image/configuration as a root-owned rollback baseline;
9. activate only in `production-activation` using `codestra-production`;
10. automatically restore the captured baseline on any activation or final-readback failure;
11. emit `FULL_PRODUCTION_GO` only after the complete evidence chain is rehashed and revalidated.

Do not add a second dispatch path, arbitrary command input, mutable image input, unprotected runner, generic production shell, or environment bypass.

## Rollback rules

- `scripts/capture-runtime-baseline.sh` must run before production mutation.
- The captured baseline must be an exact signed live tuple and root-owned mode `0600` under `/var/lib/codestra/caddy/evidence/`.
- `scripts/run-immutable-runtime.sh` must require that baseline.
- `scripts/rollback-runtime.sh` may consume either the captured runtime schema or the committed historical fallback schema, but the one-click activation must use the captured runtime schema.
- Rollback must use the unified Compose service with `--pull never --no-build`, verify signature and configuration identity, wait for health, and run the production canary.
- Never report rollback success merely because a command was attempted.

## Safety boundaries

Never commit secrets, private keys, bearer tokens, registry passwords, live environment files, or certificate private material.

Do not change SSH, firewall, DNS, Keycloak, Kong administration, application workloads, public traffic allocation, or live business-effect flags from this repository unless a separate reviewed authority explicitly owns that change.

The Caddy production workflow does not authorize application writes, payments, withdrawals, trading, dialing, email, SMS, campaigns, provider delivery, Odoo writes, or n8n external delivery.

## Branch and pull-request workflow

- Start changes from `development`.
- Promote through `development → test → staging → production → main` with merge commits.
- Keep commits focused and use Conventional Commit messages.
- Never force-push protected branches or erase promotion ancestry with squash/rebase merges.
- Every pull request must pass exact-head source validation, synthetic merge validation, promotion guard, immutable release gate, and any branch-specific staging certification.
- Resolve every review thread before merge.
- Include source SHA, image/configuration impact, tests, runtime effect, rollback effect, and remaining external bindings in the PR description.
- Do not claim deployment or production readiness from repository validation alone.
