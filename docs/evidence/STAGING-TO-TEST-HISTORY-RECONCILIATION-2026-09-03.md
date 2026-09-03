# Staging-to-test history reconciliation — 2026-09-03

This commit resolves the promotion-history conflict between:

- canonical test source: `330c4b10624df9ca5da9d8254902f2348f9f14d8`;
- prior staging source: `f3c09533a9a373ba63c37e8c8c75f81e7835cd4c`.

The reconciliation enters through the permitted `fix/* -> development` route. After it merges, the exact `development` head promotes normally to `test`, which restores a shared staging ancestry before `test -> staging` proceeds.

The resulting tree preserves the complete canonical `test` runtime and validation authority. The prior staging commit is retained as a normal second parent so no branch history is rewritten or discarded. This reconciliation does not deploy or reload Caddy, change DNS/TLS/firewall/SSH, move traffic, or enable any external effect.
