# Caddy production certification

## Source and artifact gates

The repository must prove all of the following before a runtime candidate exists:

- `config/` is the only deployable Caddy configuration authority;
- exact-head and synthetic merge-result validation pass;
- the reviewed promotion chain is enforced;
- the image is built from the exact protected `production` SHA;
- the image is immutable and bound to the canonical configuration-tree digest;
- OCI source/revision labels, non-root UID/GID, read-only filesystem, and capability restrictions pass;
- SBOM, provenance, binary-build attestation, Cosign signature, and the HIGH/CRITICAL vulnerability gate pass;
- the isolated release canary passes TCP 80/443, UDP 443, HTTP/2, HTTP/3, TLS, redirects, HSTS, request limits, WebSockets, Kong handoff, Keycloak behavior, mTLS, editor/OpenBao denial, upstream reachability, and complete log redaction;
- the previous immutable rollback baseline still verifies and boots in a protected-push disposable rehearsal.

## Required PR validation credential boundary

`.github/workflows/validate.yml` keeps every pull-request job credential-light. The source, synthetic merge, promotion, and `immutable-release-gate` jobs have only `contents: read`; they may build, test, scan, and upload source evidence, but they never receive `packages: read`, never authenticate Docker to GHCR, and never execute rollback code after a package credential is installed.

Signed rollback verification is a separate `protected-rollback-gate` that runs only for pushes to one of the five protected promotion branches after source validation succeeds. That job verifies the exact local and remote protected-branch SHA before receiving `packages: read`, authenticating to GHCR, and executing `scripts/verify-rollback-baseline.sh` from already-protected code. The aggregate `validate` context requires this protected rollback gate on branch pushes and requires it to be skipped on pull requests.

This separation means a required PR check cannot expose a package-readable token to PR-head code while preserving the protected rollback proof before subsequent branch promotion.

## Staging source certification

A push to `staging` and a governed same-repository `staging -> production` pull request run `.github/workflows/staging-certification.yml` as isolated GitHub-hosted CI on `ubuntu-24.04`. The source-certification job intentionally does **not** request the protected `staging-readonly` environment, does not consume protected environment variables, and has only `contents: read` repository permission. Production pull-request certification is rejected unless the head repository is the canonical repository and the direct or governed reconciliation route validates against the exact protected branch trees.

The source job builds the exact source SHA, runs the full disposable protocol/security canary, scans the image, and uploads `staging-certification.json`. It never authenticates to GHCR, never installs a package-readable Docker credential, and never executes rollback code after such a credential has been installed.

This source gate does not reload a host Caddy process, bind a public interface, change DNS, modify firewall or SSH policy, move traffic, or constitute protected runtime-environment admission. Protected `staging-readonly` admission is reserved for the later self-hosted bounded staging runtime described below.

## Protected staging rollback certification

Rollback rehearsal is a separate job in the same workflow and runs **only** for a push to the protected `staging` branch after source certification succeeds. Only that protected-push job receives `packages: read`, authenticates to GHCR, installs Cosign, and executes `scripts/verify-rollback-baseline.sh`. It rechecks that both the local checkout and `origin/staging` equal the exact protected staging push SHA before credential handling.

Passing rollback evidence is written to `staging-rollback-certification.json` and uploaded separately from the credential-free source packet. A production pull request does not receive package credentials and does not claim a new rollback rehearsal; production promotion must use the exact tree already present on protected `staging` and requires the corresponding protected staging-push rollback gate to be PASS.

The workflow's `staging-certification-gate` requires both source certification and rollback certification on a protected staging push. On a production pull request it requires the credential-free source certification and explicitly requires the credentialed rollback job to be skipped.

## Signed bounded staging runtime

After the protected production push publishes and signs the new immutable digest, `.github/workflows/bounded-runtime-certification.yml` waits for that exact digest and signature. The `codestra-staging` self-hosted runner executes `scripts/bounded-staging-runtime-v2.sh` only through the protected `staging-readonly` environment, with its runtime paths supplied by protected environment configuration.

The staging runtime:

- reads a root-owned `0400` or `0600` staging environment contract;
- copies staging certificate state into an ephemeral non-root data directory;
- keeps the candidate in a dedicated Docker bridge network;
- maps every candidate listener only to host loopback ports;
- preserves actual staging Kong, Keycloak, realtime, observability, and other upstream addresses;
- verifies TCP 80/443, UDP 443, certificates, redirects, HSTS, HTTP/2, a real HTTP/3 request, WebSockets, request limits, Kong handoff, Keycloak issuer, editor/OpenBao denial, mTLS handshake/denial, upstream health, and sanitized logs;
- removes the candidate container, private network, copied certificate state, and loopback listeners before completing;
- emits `bounded-staging-runtime-evidence.json` and binds its SHA-256 to the downstream production canary.

No public listener or live staging edge is replaced.

## Production read-only canary

Only after the bounded staging runtime passes does the `codestra-production-canary` self-hosted runner execute `scripts/bounded-production-readonly-canary-v2.sh` in the protected `production-readonly-canary` environment.

The production canary does **not** start the candidate, reload Caddy, alter traffic allocation, or send a write request. It:

1. runs the fixed-target `scripts/caddy_readonly_validator.py` against the actual `codestra-caddy` container;
2. verifies the same signed candidate digest, OCI source/revision labels, non-root identity, and configuration hash used in staging;
3. validates the candidate configuration offline with networking disabled and fixed PKI mounts read-only;
4. makes only GET, WebSocket-upgrade, TLS, HTTP/2, HTTP/3, and mTLS-handshake probes against the existing live edge;
5. verifies Kong health/auth behavior, the realtime version path, Keycloak issuer, Grafana health, unknown-route denial, editor/OpenBao denial, certificate validity, and effective access-log redaction;
6. reruns the fixed-target validator and requires byte-identical pre/post runtime evidence.

Passing evidence is written to `production-canary-evidence.json`. It explicitly records:

```text
write_requests_sent=false
candidate_started_on_production=false
public_traffic_changed=false
dns_changed=false
firewall_changed=false
ssh_changed=false
live_runtime_unchanged=true
```

## Live validator contract

The fixed-target validator must return `codestra.caddy-container-validation.v2` evidence with:

- `container_running=true` and `container_health=healthy`;
- the exact immutable image digest and source SHA;
- image, container, and configuration hashes aligned;
- the required Caddy modules;
- Caddy-process ownership of TCP 80/443, UDP 443, private metrics TCP 2020, and private mTLS TCP 18080;
- private metrics health;
- effective `/etc/caddy` configuration and complete credential-redaction validation.

## Rollback boundary

The previous immutable digest in `config/release-baseline.v1.json` must remain signed by the protected production workflow identity. Protected branch pushes, the protected staging push, and the release gate rehearse the baseline in disposable runtimes as applicable. A real production rollback remains a separate operator action through `scripts/rollback-runtime.sh`; the read-only canary never invokes it.

No source-only check is represented as live runtime evidence, no production-PR source check is represented as a protected staging rollback pass, and no queued or skipped self-hosted job is represented as a pass.
