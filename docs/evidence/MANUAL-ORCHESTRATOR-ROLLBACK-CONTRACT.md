# Captured production rollback contract

The one-click production orchestrator must capture the currently healthy `codestra-caddy` source, immutable image digest, configuration SHA-256, signature status, validator hash, listener ownership, and access-log redaction state before changing production.

The resulting `codestra.caddy-runtime-rollback-baseline.v1` file is root-owned, mode `0600`, and stored beneath `/var/lib/codestra/caddy/evidence/`. Activation fails closed when the file is missing or invalid. Any activation or final-readback failure restores that exact tuple through `deploy/compose.runtime.yaml`, waits for health, and reruns the production canary.
