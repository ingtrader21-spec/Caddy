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
- the previous immutable rollback baseline still verifies and boots in the disposable rehearsal.

## Staging source certification

A push to `staging` and a `staging -> production` pull request run `.github/workflows/staging-certification.yml` in the protected `staging-readonly` environment. The job builds the exact source SHA, runs the full disposable protocol/security canary, scans the image, verifies the prior rollback baseline, and uploads `staging-certification.json`.

This source gate does not reload a host Caddy process, bind a public interface, change DNS, modify firewall or SSH policy, or move traffic.

## Signed bounded staging runtime

After the protected production push publishes and signs the new immutable digest, `.github/workflows/bounded-runtime-certification.yml` waits for that exact digest and signature. The `caddy-staging-readonly` runner then executes `scripts/bounded-staging-runtime-v2.sh` with paths supplied only by the protected `staging-readonly` environment.

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

Only after the bounded staging runtime passes does the `caddy-production-readonly` runner execute `scripts/bounded-production-readonly-canary-v2.sh` in the protected `production-readonly` environment.

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

The previous immutable digest in `config/release-baseline.v1.json` must remain signed by the protected production workflow identity. Staging and the release gate rehearse the baseline in a disposable runtime. A real production rollback remains a separate operator action through `scripts/rollback-runtime.sh`; the read-only canary never invokes it.

No source-only check is represented as live runtime evidence, and no queued or skipped self-hosted job is represented as a pass.
