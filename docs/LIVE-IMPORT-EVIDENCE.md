# Historical import evidence

The initial server-to-Git import is retained only as historical evidence. It is no longer a source-selection or deployment mechanism.

The reconciled authority is the single `config/` tree. Runtime must be the signed `codestra-caddy` container selected by exact production SHA and immutable digest. Any future emergency server change must be treated as drift, captured read-only, reconciled through the full pull-request promotion chain, rebuilt, signed, canaried, and deployed from the resulting protected production SHA.
