# Caddy one-click production orchestrator

`.github/workflows/manual-production-orchestrator.yml` is the single manual CD entry point for an already reviewed, signed, immutable Caddy `production` commit. Automatic pull-request CI and immutable candidate publication remain independent fail-closed authorities; this workflow refuses to activate an image when the exact production release, protected environments, staging result, rollback evidence, or production read-only evidence cannot be proven.

## Start

Open **Actions → Caddy one-click production orchestrator → Run workflow**, select the exact `production` branch, enter:

```text
RUN_CADDY_PRODUCTION
```

Then dispatch the workflow once. Do not select another branch and do not substitute a tag, shortened commit, mutable image name, user-provided digest, host command, or script path.

A single dispatch may pause at protected-environment approval gates. Those gates are part of the one-click release and must not be bypassed.

## Ordered gates

The workflow performs this fixed sequence:

1. Proves the selected checkout is the current remote `production` SHA and has a clean worktree.
2. Runs the complete repository CI validator, including the single `config/` authority and `deploy/compose.runtime.yaml` ownership checks.
3. Reads back the active `Protect Caddy promotion branches` ruleset and requires five protected branches, zero bypass actors, one independent approval, stale-review dismissal, last-push approval, resolved conversations, squash-only linear history, and the four canonical status checks.
4. Reads back `staging-readonly`, `production-readonly-canary`, and `production-activation` and requires each environment to allow protected branches only.
5. Resolves the GitHub release named for the exact production SHA and extracts only an `image@sha256:...` identity.
6. Verifies OCI source, revision, configuration checksum, non-root identity, Cosign signature, source attestation, successful immutable-release run, vulnerability result, SBOM/provenance packet, and exact release-evidence artifact.
7. Uses `staging-readonly` on `self-hosted,codestra-staging` to deploy that exact digest in an isolated, loopback-only staging runtime.
8. Certifies TLS, HTTP/2, HTTP/3, routes, Kong, Keycloak, mTLS, limits, WebSockets, sanitized logs, source/configuration readback, health, and isolation.
9. Rehearses the signed historical rollback and binds the staging evidence, rollback result, baseline checksum, and unified Compose checksum.
10. Uses `production-readonly-canary` on `self-hosted,codestra-production-canary` only after staging and rollback pass.
11. Re-verifies the same source/image/configuration tuple, performs GET/HEAD/TLS/handshake-only live checks, and requires byte-identical runtime snapshots before and after.
12. Uses `production-activation` on the dedicated `self-hosted,codestra-production` runner only after the read-only canary passes.
13. Captures the currently healthy live Caddy source SHA, image digest, configuration digest, release ID, runtime environment, data/config mount identities, signature, listener ownership, and redaction state into root-owned mode-`0600` rollback files.
14. Activates only the exact signed digest through `deploy/compose.runtime.yaml`, validates the non-root Caddy configuration, waits for health, and proves final source/image/configuration/listener readback.
15. Automatically restores the captured live baseline if candidate health, canary, or final identity readback fails. A rollback failure is a distinct hard `NO_GO`.
16. Publishes a machine-readable final receipt and returns `FULL_PRODUCTION_GO` only when every prior job succeeds.

## Protected environments and runners

| Environment | Runner labels | Purpose |
|---|---|---|
| `staging-readonly` | `self-hosted`, `codestra-staging` | Isolated exact-digest staging certification and rollback rehearsal |
| `production-readonly-canary` | `self-hosted`, `codestra-production-canary` | Read-only inspection of the existing production edge; no replacement |
| `production-activation` | `self-hosted`, `codestra-production` | Exact-digest Caddy replacement with captured live rollback |

All environments must be configured for **protected branches only**. The workflow checks this before staging starts.

The production runner must be dedicated to this repository and environment, run the reviewed job as root, and provide root-owned, non-group/world-writable `/usr/bin/docker`, `/usr/bin/python3`, `/usr/bin/jq`, and `/usr/local/bin/cosign`. It must not be shared with pull-request jobs or untrusted repositories.

`production-activation` must define the environment variable:

```text
CADDY_PRODUCTION_ENV_FILE=/absolute/root-owned/path/caddy-production.env
```

The file must be root-owned, mode `0600`, not a symlink, and contain exactly the non-secret Caddy runtime variables declared in `config/runtime-values.example`. The parser rejects unknown keys, duplicate keys, missing values, and shell syntax; it never `source`s or evaluates the file.

## Exact rollback authority

Before any production replacement, `scripts/capture-runtime-baseline.sh` inspects the current `codestra-caddy` container and records:

- exact live `image@sha256:...` identity;
- source SHA, configuration SHA-256, and release ID labels;
- keyless signature verification;
- healthy container and Caddy-only listener ownership;
- effective access-log redaction state;
- exact allowlisted runtime environment values in a separate root-owned mode-`0600` file;
- `/data` and `/config` host mount identities;
- validator-output SHA-256.

`scripts/rollback-runtime.sh` accepts that captured baseline, verifies its checksums and signature, restores the exact previous image, environment, state mounts, source/configuration/release labels, waits for health, and reruns the production canary. It writes an immutable rollback-result receipt. The committed `config/release-baseline.v1.json` remains the independent historical CI rehearsal authority; it is not substituted for the captured live baseline during production activation.

## Fail-closed conditions

The run stops with `NO_GO` for any missing or mismatched:

- current production SHA or clean checkout;
- active no-bypass ruleset or required review policy;
- protected environment;
- exact GitHub release or immutable artifact;
- OCI source/revision/configuration label;
- image signature, source attestation, SBOM, provenance, scan, or release packet;
- staging runner, staging path, certificate, route, health, protocol, isolation, or evidence result;
- historical rollback result;
- production read-only runner, live snapshot, listener, certificate, denial, route, or unchanged-runtime proof;
- production activation runner, root-owned runtime environment file, live baseline, state mount, trust material, candidate health, or final exact-identity readback.

The workflow also stops on any write request, unexpected production mutation during the read-only canary, public traffic movement outside the Caddy replacement, DNS/firewall/SSH change, source/digest drift, configuration drift, or inability to prove rollback.

## Successful result

A complete success emits:

```text
CADDY_ONE_CLICK_PRODUCTION=FULL_PRODUCTION_GO
FULL_PRODUCTION_GO=true
CADDY_RUNTIME_LIVE=true
APPLICATION_WRITES_AUTHORIZED=false
```

This authorizes the exact Caddy edge runtime only. It does **not** authorize application writes, payments, withdrawals, trading, provider delivery, email, SMS, PSTN, campaign activation, Odoo writes, n8n external delivery, DNS changes, firewall changes, SSH changes, or unrelated workload changes.
