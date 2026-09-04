# Codestra Caddy edge authority

This repository is the authoritative source for the Codestra public Caddy edge. It owns the reviewed Caddy configuration, custom immutable image, unified production Compose service, edge validation, signed release evidence, bounded staging certification, read-only production canary, exact-digest production activation, and rollback controls.

It does **not** own application business logic, Keycloak realm administration, Kong route administration, DNS-provider credentials, production secrets, or application/provider write authorization.

## Canonical source and runtime

The only deployable configuration tree is:

```text
config/
```

The only production runtime composition is:

```text
deploy/compose.runtime.yaml
```

The production service is `codestra-caddy`. The Compose model requires an exact `image@sha256:...` identity, exact protected source SHA, canonical configuration SHA-256, release ID, non-root UID/GID `65532:65532`, read-only root filesystem, dropped capabilities except `NET_BIND_SERVICE`, and `no-new-privileges`.

A second Dockerfile, production Compose model, Caddy configuration root, mutable image tag, or host-systemd deployment authority is prohibited.

## CI

Pull-request CI validates the exact head and GitHub synthetic merge result. The required gates are:

```text
validate-source
validate-merge-result
promotion-guard
immutable-release-gate
```

The checks prove the single configuration authority, unified Compose ownership, Caddy-to-Kong route contract, unknown-route denial, non-root privileged-port binding, HTTP/2 and HTTP/3, TLS, HSTS, request limits, WebSockets, Keycloak redirects, mTLS, complete credential redaction, HIGH/CRITICAL vulnerability status, signed rollback compatibility, and absence of a competing runtime.

Run the same source contract locally with:

```bash
bash scripts/validate-ci.sh
```

## Manual one-click CD

The production entry point is:

```text
.github/workflows/manual-production-orchestrator.yml
```

From **Actions → Caddy one-click production orchestrator**, select the exact `production` branch, enter:

```text
RUN_CADDY_PRODUCTION
```

and dispatch once. There are no free-form image, digest, source, host, command, percentage, or script inputs. Protected-environment approvals may pause the run and must not be bypassed.

The fixed chain is:

```text
current protected production SHA
  → active no-bypass ruleset and protected-environment readback
  → exact signed image and release-evidence verification
  → bounded staging deployment and certification
  → historical rollback rehearsal and evidence hash
  → production GET/HEAD/handshake-only canary
  → byte-identical pre/post live-runtime readback
  → capture current live image/environment/mount/release baseline
  → exact-digest Caddy activation through unified Compose
  → health, source, image, config, listener and redaction readback
  → automatic exact-live-baseline rollback on failure
  → machine-readable FULL_PRODUCTION_GO or NO_GO
```

A successful source push, pull-request check, image release, or read-only canary is not a complete deployment. The final workflow artifact must report:

```text
CADDY_ONE_CLICK_PRODUCTION=FULL_PRODUCTION_GO
FULL_PRODUCTION_GO=true
CADDY_RUNTIME_LIVE=true
APPLICATION_WRITES_AUTHORIZED=false
```

## Protected environments and runners

| Environment | Required runner | Authority |
|---|---|---|
| `staging-readonly` | `self-hosted`, `codestra-staging` | Isolated exact-digest staging deployment and rollback rehearsal |
| `production-readonly-canary` | `self-hosted`, `codestra-production-canary` | Read-only live inspection with no container replacement |
| `production-activation` | `self-hosted`, `codestra-production` | Exact-digest Caddy replacement with captured live rollback |

All three environments must allow protected branches only. The preflight reads that policy through the GitHub API before any runtime job starts.

The production runner must be dedicated to this private repository and protected environment, execute the reviewed job as root, and provide root-owned, non-group/world-writable `/usr/bin/docker`, `/usr/bin/python3`, `/usr/bin/jq`, and `/usr/local/bin/cosign`. It must not accept pull-request or unrelated-repository jobs.

`production-activation` must expose only the variable:

```text
CADDY_PRODUCTION_ENV_FILE=/absolute/root-owned/path/caddy-production.env
```

The referenced file must be root-owned, mode `0600`, not a symlink, and contain the non-secret variables declared in `config/runtime-values.example`. The parser rejects unknown or duplicate keys and never evaluates shell syntax.

## Immutable release authority

Production pushes build the exact protected SHA and publish only the exact SHA tag plus immutable digest. The release pipeline produces:

- custom patched Caddy binary evidence;
- OCI source, revision, and configuration labels;
- zero-HIGH/zero-CRITICAL image gate;
- SBOM and BuildKit provenance;
- keyless image signature;
- Codestra source attestation;
- HTTP/2, HTTP/3, TLS, mTLS, Kong, Keycloak, denial, limit, WebSocket, and log-redaction canary evidence;
- historical rollback rehearsal.

The one-click workflow consumes and re-verifies this existing release. It never substitutes `latest`, rebuilds on a runtime host, or retags an image.

## Exact live rollback

Before production replacement, `scripts/capture-runtime-baseline.sh` verifies the current healthy `codestra-caddy` container and writes root-owned mode-`0600` records containing:

- live source SHA, immutable image digest, configuration digest, and release ID;
- Cosign signature proof;
- validator-output checksum, health, Caddy-only listener ownership, and redaction state;
- exact allowlisted runtime environment in a separate protected file;
- `/data` and `/config` host mount identities.

`scripts/run-immutable-runtime.sh` requires that captured baseline. Candidate health, production canary, or final source/image/configuration mismatch invokes `scripts/rollback-runtime.sh`. Rollback restores the captured image, runtime environment, state mounts, configuration, source, and release identity, then reruns the production canary. A rollback failure is surfaced as `activation_and_rollback_failed`; it is never hidden.

The committed `config/release-baseline.v1.json` remains the independently tested historical CI authority. It is not substituted for the captured live baseline during production activation.

## Edge routing contract

Known shared API families use:

```text
client → Caddy → Kong → Middleware or owned downstream service
```

`api.codestra.co` is canonical. `api.codestra.agency` is legacy compatibility only. Both follow the governed Caddy/Kong contract. Unknown API routes return `404`; there is no unrestricted fallback to the old Middleware listener.

Every access log imports the shared sanitizer and removes authorization headers, cookies, API keys, OAuth/OIDC query values, response cookies, and access-token response headers.

## Branch flow

Source changes move through protected branches:

```text
development → test → staging → production → main
```

No force push, direct unreviewed branch update, or administrator bypass is part of the release model. The current governance source requires one independent exact-head approval, stale-review dismissal, last-push approval, resolved conversations, required status checks, and linear history.

## Safety boundary

The one-click workflow authorizes only the reviewed Caddy edge runtime. It does not authorize application writes, payments, withdrawals, trading, dialing, email, SMS, provider delivery, campaign activation, Odoo writes, n8n external delivery, DNS changes, firewall changes, SSH-policy changes, or unrelated workload changes.

Never commit tokens, private keys, bearer credentials, registry passwords, certificate private material, environment payloads, or live service secrets. GitHub protected environments and root-owned host paths are the only accepted runtime binding locations.
