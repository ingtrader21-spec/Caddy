# Caddy production certification

## Source and artifact gates

- one `config/` authority;
- exact-head and synthetic merge-result validation;
- enforced promotion chain;
- signed immutable image bound to the protected production SHA;
- deterministic configuration-tree hash in the image and container labels;
- SBOM, provenance, binary-build attestation, and zero unresolved HIGH/CRITICAL image findings;
- isolated canary passes TCP 80/443, UDP 443 binding, HTTP/2 ALPN, local TLS, redirects, HSTS, body limits, WebSocket proxying, Kong handoff, Keycloak redirect, mTLS, editor/OpenBao denial, upstream reachability, and log redaction.

## Production runtime gates

Run the reviewed no-argument validator through the existing bounded operator or the exact production checkout. It must return `codestra.caddy-container-validation.v2` evidence with:

- `container_running=true` and `container_health=healthy`;
- exact signed image digest and source SHA;
- image/container/config hashes aligned;
- required Caddy modules;
- TCP 80/443, UDP 443, and private TCP 2020 listeners;
- private metrics health;
- sanitized effective-configuration summary.

Then run `scripts/production-canary.sh` and retain its root-owned `0600` JSON evidence. Public certificate chain/expiry, real HTTP/3 request, DNS answers, Kong authentication denials, Keycloak callback behavior, and production upstream health must be checked from the actual production network.

## Rollback gate

The previous immutable digest in `config/release-baseline.v1.json` must still verify with the protected production workflow identity. Rehearse `scripts/rollback-runtime.sh`, verify the prior source label, compute the embedded baseline configuration hash (and compare a config label when present), restore the previous container, verify image/config read-back and health, and then return to the new release only after evidence review.

No source-only or GitHub-hosted canary is a substitute for production-network evidence.
