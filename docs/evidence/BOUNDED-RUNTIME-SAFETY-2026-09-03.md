# Bounded runtime safety evidence — 2026-09-03

The bounded certification workflow is intentionally ordered and fail-closed:

```text
signed production image
  -> bounded staging runtime
  -> exact immutable tuple output
  -> production read-only canary
```

The staging candidate uses a dedicated Docker bridge network and host-loopback-only published ports. The production phase does not start a candidate process; it validates the candidate image without network access and probes the already-running fixed Caddy container with read-only requests.

Promotion must stop on any source, digest, configuration, signature, attestation, health, listener, certificate, protocol, routing, denial, mTLS, redaction, upstream, or pre/post runtime-snapshot mismatch.
