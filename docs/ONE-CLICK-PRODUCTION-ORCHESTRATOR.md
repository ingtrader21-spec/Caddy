# Caddy one-click production orchestrator

The workflow `.github/workflows/manual-production-orchestrator.yml` is the manual CD entry point for an already reviewed `production` commit. CI and immutable candidate publication remain separate fail-closed authorities; this workflow refuses to deploy when the exact production release is missing or cannot be cryptographically verified.

## Start

Open **Actions → Caddy one-click production orchestrator → Run workflow**, select the `production` branch, enter:

```text
RUN_CADDY_PRODUCTION
```

Then run the workflow once. Do not select another branch and do not substitute a tag, shortened commit, mutable image name, or user-supplied digest.

## Ordered gates

The workflow performs the following sequence:

1. Proves the selected checkout is the current remote `production` SHA and has a clean worktree.
2. Runs the complete repository CI validator, including the single `config/` authority and `deploy/compose.runtime.yaml` ownership checks.
3. Reads back the active `Protect Caddy promotion branches` ruleset and requires five protected promotion branches, zero bypass actors, merge-only history, and the four canonical status checks.
4. Resolves the GitHub release named for the exact production SHA.
5. Extracts an `image@sha256:...` identity only; mutable tags are rejected.
6. Verifies OCI source, revision, configuration checksum, non-root identity, Cosign signature, source attestation, successful immutable-release run, and the exact release-evidence artifact.
7. Uses the protected `staging-readonly` environment and a runner labeled `self-hosted,codestra-staging` to deploy that exact digest in bounded staging.
8. Certifies TLS, HTTP/2, HTTP/3, routes, Kong, Keycloak, mTLS, request limits, WebSockets, sanitized logs, source/configuration readback, health, and isolation through the existing staging controller.
9. Rehearses the signed historical rollback baseline and binds the resulting output, baseline checksum, staging evidence, and unified Compose checksum into a machine-readable packet.
10. Uses the protected `production-readonly-canary` environment and a runner labeled `self-hosted,codestra-production-canary` only after staging and rollback succeed.
11. Re-verifies the identical source/image/configuration tuple, performs only the bounded read-only canary, and requires byte-identical live-runtime snapshots before and after.
12. Publishes a final receipt and returns `READ_ONLY_CANARY_GO` only when every upstream job succeeds.

## Fail-closed conditions

The run stops with `NO_GO` for any missing runner, protected environment value, absolute certificate/key path, branch ruleset, exact release, immutable artifact, signature, attestation, source label, revision label, configuration checksum, non-root identity, staging evidence, rollback evidence, production runtime snapshot, or canary check.

The workflow also stops on any write request, candidate start/replace/reload on production, public traffic change, source/digest drift, configuration drift, or pre/post runtime difference.

## Authority boundary

A successful result means:

```text
STAGING_CERTIFIED=true
ROLLBACK_REHEARSED=true
PRODUCTION_READONLY_CANARY=true
FULL_LIVE_ACTIVATION_AUTHORIZED=false
```

It does not authorize application writes, provider delivery, email, SMS, PSTN, campaign activation, DNS changes, firewall changes, SSH changes, or unrestricted production traffic. Those require a separate protected activation release.
