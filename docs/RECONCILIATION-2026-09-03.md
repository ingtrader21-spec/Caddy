# Caddy authority reconciliation — 2026-09-03

This change joins the accepted `main`, `production`, and `development` histories without rewriting or force-updating any branch. It preserves `config/` as the only deployable tree and retires the competing candidate tree.

The previously signed production image remains recorded only as the immutable rollback baseline. It is not the active candidate because it predates the canonical main-line validator and observability work and still contained the unrestricted legacy API fallback.

The reconciled release:

- routes all contracted shared API prefixes through Kong on both canonical and legacy hostnames;
- permits only explicitly enumerated realtime compatibility paths outside Kong;
- returns `404` for unknown API paths;
- applies one complete credential-redaction policy to every access log;
- exposes Caddy metrics only on an explicitly bound private listener;
- validates the actual immutable `codestra-caddy` container instead of a separate systemd service;
- binds image, source, and deployable configuration hashes;
- adds exact-head, synthetic merge-result, promotion, isolated canary, signed release, production read-back, and rollback gates.

No SSH, firewall, DNS, production certificate, or unrelated workload change is included.
