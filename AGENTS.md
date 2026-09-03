# Caddy repository operating rules

1. `appolon1908-hue/Caddy` is the sole source authority for shared Caddy edge configuration.
2. `config/` is the only deployable and validated Caddy tree. Never add a competing candidate/live tree.
3. Shared API traffic follows Caddy -> Kong -> Middleware. Do not add direct Caddy -> Middleware/provider routes for Kong-managed paths.
4. Unknown API paths fail closed. Compatibility routes must be enumerated in `config/caddy-kong-contract.v2.json`.
5. Every access log imports `sanitized_access_log`; never log Authorization, cookies, API keys, OIDC codes/state, vault tokens, or response cookies.
6. Never commit private keys, passwords, tokens, `.env` files, ACME data, runtime data, or host-managed certificate material.
7. Work starts from `development` and promotes only by PR: development -> test -> staging -> production -> main.
8. No force push, non-fast-forward update, admin bypass, or direct protected-branch write is allowed.
9. Production images are digest-pinned, signed, attested, vulnerability-scanned, and tied to the exact production SHA and configuration hash.
10. Production runtime is the fixed `codestra-caddy` container; do not certify a separate host-systemd Caddy process as the release runtime.
11. Runtime validation and canary commands are fixed-target/read-only and must not print raw configuration or secret values.
12. A failed activation must preserve or restore the previous immutable image and configuration identity.
13. Do not change SSH, firewall rules, DNS ownership, or unrelated workloads from this repository.
14. Do not declare production PASS without collected runtime, listener, TLS, routing, mTLS, denial, log-redaction, and rollback evidence.
