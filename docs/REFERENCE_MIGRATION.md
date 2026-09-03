# Reference migration status

The former `codestra-production-platform` Caddy files and the retired `candidate/` tree are historical references only. Neither may be used as the deployable source.

Migration is reconciled into `config/` with these enforced boundaries:

- contracted shared API prefixes go to Kong;
- only enumerated realtime compatibility paths bypass Kong temporarily;
- unknown API paths return `404`;
- every access log uses the shared credential redactor;
- immutable image, runtime validator, canary, and rollback use the same configuration tree.

Removing the remaining realtime compatibility path requires accepted Kong route parity and production-network evidence. It does not require or permit restoring an unrestricted legacy fallback.
