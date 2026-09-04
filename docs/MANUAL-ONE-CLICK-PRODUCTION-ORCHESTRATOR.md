# Manual one-click Caddy production orchestrator

## Purpose

`Manual one-click Caddy production orchestrator` is the single operator entry
point for the already-reviewed Caddy release chain. It does not introduce a
second build, Compose, staging, canary, or deployment implementation. Instead,
it freezes the exact protected `production` SHA and adopts or reruns the two
existing production-push authorities:

1. `.github/workflows/immutable-release.yml`
2. `.github/workflows/bounded-runtime-certification.yml`

The orchestrator verifies their exact artifacts before it can report `PASS`.
A missing runner, expired artifact, SHA mismatch, digest mismatch, failed
signature, failed scan, failed staging gate, changed production snapshot, or
missing rollback evidence produces `NO_GO`.

## Operator button

After this source is promoted through `development -> test -> staging ->
production -> main`, open:

```text
https://github.com/appolon1908-hue/Caddy/actions/workflows/manual-production-orchestrator.yml
```

Select **Run workflow** on `main`. The default inputs freeze the current
production head, reuse an already-successful signed release for that exact SHA,
and execute or adopt the bounded runtime chain.

## Inputs

| Input | Default | Meaning |
|---|---:|---|
| `expected_production_sha` | blank | Optional 40-character confirmation. Blank means freeze the current remote `production` head at dispatch time. |
| `rebuild_signed_image` | `false` | When true, rerun the exact production release workflow even when its current exact-SHA attempt already succeeded. |
| `runtime_wait_minutes` | `120` | Bounded wait for the protected staging and production-canary runners. |
| `confirm_readonly_orchestration` | `true` | Must remain true. It is an explicit assertion that this workflow runs the staging and production-read-only certification chain. |

## Exact execution sequence

### 1. Freeze production authority

The controller:

- requires dispatch from protected `main`;
- reads the current remote `production` head;
- optionally requires it to equal `expected_production_sha`;
- requires both `main` and `production` to report protected;
- requires `staging` to be an ancestor of the candidate or have a byte-identical tree;
- requires the canonical `config/` tree and `deploy/compose.runtime.yaml`;
- runs `scripts/validate-ci.sh` against the exact production checkout;
- computes the configuration SHA-256 from that checkout.

### 2. Build, scan, sign, attest, and prove rollback

The controller only accepts the exact production-push run for
`.github/workflows/immutable-release.yml`. It rejects runs from another SHA,
branch, event, or workflow path. Its downloaded artifact must prove:

```text
SBOM=PASS
IMAGE_PROVENANCE=PASS
SOURCE_PROVENANCE=PASS
BINARY_BUILD_ATTESTATION=PASS
SIGNATURE=PASS
VULNERABILITY_GATE=PASS
CANARY_CERTIFICATION=PASS
HTTP3_CANARY=PASS
ROLLBACK_BASELINE=PASS
ROLLBACK_REHEARSAL=PASS
```

The source SHA, immutable GHCR digest, and configuration SHA-256 must all match
the frozen production checkout.

### 3. Bounded staging certification

The existing runtime workflow remains the deployment authority. Its first job
runs only on:

```text
runner: self-hosted, codestra-staging
environment: staging-readonly
```

It deploys the exact signed digest into an isolated, loopback-bound staging
runtime and checks the Caddy configuration, non-root runtime, TCP 80/443, UDP
443, TLS, HTTP/2, HTTP/3, redirects, HSTS, request limits, WebSockets, Kong,
Keycloak, mTLS, editor/OpenBao denial, upstream behavior, credential redaction,
and candidate cleanup.

### 4. Production read-only canary

Only after bounded staging succeeds, the existing workflow runs on:

```text
runner: self-hosted, codestra-production-canary
environment: production-readonly-canary
```

It verifies the same source/image/configuration tuple and its Cosign evidence,
performs fixed GET/HEAD/handshake probes, and requires byte-identical live
runtime snapshots before and after the canary. It does not start the candidate
on production, send application writes, move public traffic, or change DNS,
firewall, SSH, or certificate ownership.

### 5. Final receipt

The workflow publishes a machine-readable receipt containing the controller
SHA, production source SHA, image digest, configuration digest, child run IDs
and attempts, evidence hashes, and each job result. `PASS` is emitted only when
all three stages succeed. Every other state is `NO_GO` and the workflow exits
non-zero.

## Protected environment prerequisites

The button can exist before runtime capacity is attached, but it will remain
fail-closed until these bindings exist:

- online runner labeled `self-hosted, codestra-staging`;
- protected environment `staging-readonly` with the required absolute file-path variables;
- online runner labeled `self-hosted, codestra-production-canary`;
- protected environment `production-readonly-canary` with its separately scoped mTLS paths;
- package read access to the exact GHCR digest;
- the fixed PKI and runtime paths required by the existing child workflows.

The manual controller does not create runners, weaken environment protection,
change SSH, expose secrets, or grant Docker authorization.

## Safety boundary

This orchestrator is a one-click **release, staging, rollback, and production
read-only certification** controller. It deliberately does not call
`run-immutable-runtime.sh`, directly execute `docker compose up`, or replace the
live Caddy container. A later live-activation authority must consume this exact
successful receipt and preserve the separately reviewed production operator and
rollback controls.
