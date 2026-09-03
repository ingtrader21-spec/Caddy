# Bounded runtime certification implementation evidence

Date: 2026-09-03

This change introduces two distinct, fail-closed runtime phases for the same signed immutable Caddy digest.

## Bounded staging

The candidate is deployed into a dedicated Docker bridge network on the `caddy-staging-readonly` runner. Host exposure is limited to explicit `127.0.0.1` mappings, while real staging upstream values and copied staging certificate state are used. The candidate, network, copied state, and mapped listeners are removed before success is reported.

Required evidence: `bounded-staging-runtime-evidence.json` with `result=PASS`, loopback-only host mappings, exact source/image/config identity, protocol and route certification, sanitized logs, candidate removal, and no DNS/firewall/SSH/public-traffic change.

## Production read-only

The `caddy-production-readonly` runner receives the staging evidence hash and the same signed digest. It starts no candidate, sends no write request, and performs only fixed-target validation plus GET, TLS, HTTP/2, HTTP/3, WebSocket-upgrade, and mTLS-handshake probes against the existing live edge.

Required evidence: `production-canary-evidence.json` with `result=PASS`, byte-identical pre/post live-runtime snapshots, `write_requests_sent=false`, `candidate_started_on_production=false`, and no DNS/firewall/SSH/public-traffic change.

A queued, skipped, timed-out, or failed self-hosted job is not a certification pass.
