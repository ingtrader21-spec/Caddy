# Caddy source-authority reconciliation evidence

Date: 2026-09-03

The canonical reconciliation was created without rewriting repository history.

- canonical tree commit: `5ef27cf716d548c7a24b1b99fe88e5cd0da29d98`
- latest-development ancestry merge: `8cb86539f4d9d9885928b12d3412869577334cd1`
- original development parent: `8301fd7e5924a0cbd1b5f5831fc1067043a73676`
- latest development parent: `732d1f34afc74b23ee43115588b5d30be6e12967`
- production parent: `c5f9555082aadbb0a762234394ef08f1908e484c`
- main parent: `2d91ea9f6301c9f278246f31dc6e45052891ea65`
- force push used: `false`
- branch history rewritten: `false`
- live Caddy reload performed: `false`
- DNS, firewall, SSH, or certificate state changed: `false`

The resulting tree makes `config/` the sole deployable configuration authority, retains the previously signed production image only as an immutable rollback baseline, and requires a new signed image from the reconciled protected production SHA before activation.
