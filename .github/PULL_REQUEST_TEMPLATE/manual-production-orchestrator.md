## Manual Caddy production orchestrator review

- [ ] Exact current protected `production` SHA is the only source authority.
- [ ] Immutable image output is `image@sha256`, never a mutable tag.
- [ ] `deploy/compose.runtime.yaml` remains the only production Compose authority.
- [ ] Release includes scan, SBOM, provenance, signature, source attestation, protocol/security canary, and historical rollback rehearsal.
- [ ] `staging-readonly` runs before `production-readonly-canary`.
- [ ] Production read-only canary consumes the exact staging evidence hash and does not mutate live Caddy.
- [ ] Current healthy production runtime is captured before activation.
- [ ] Activation uses `production-activation` and `codestra-production`.
- [ ] Every activation failure invokes exact captured-baseline rollback.
- [ ] Final evidence rehashes release, rollback, staging, read-only canary, and activation packets.
- [ ] No DNS, firewall, SSH, Keycloak, Kong-admin, unrelated workload, traffic-allocation, or application-write authority is introduced.

### Evidence

```text
SOURCE_SHA=
IMAGE=
CONFIG_SHA256=
VALIDATE_SOURCE=
VALIDATE_MERGE_RESULT=
IMMUTABLE_RELEASE_GATE=
REVIEW_THREADS=
RUNTIME_EFFECT=source-only until manual protected dispatch
```
