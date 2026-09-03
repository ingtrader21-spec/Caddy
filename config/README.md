# Deployable Caddy configuration

`config/` is the repository's only deployable Caddy source tree. The root file imports `snippets/`, `sites/`, and `conf.d/`; image construction, exact-head CI, isolated canaries, runtime read-back, and rollback hashing all consume this same tree.

Do not add a second root Caddyfile, candidate tree, server-local route source, inline secret, mutable image reference, or unrestricted fallback. Runtime values are supplied from the protected environment according to `runtime-values.example`. Host-managed certificate material lives only under the fixed read-only mounts declared in `deploy/compose.runtime.yaml` and is excluded from the deterministic configuration hash.
