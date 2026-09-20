# Deployment Evidence Contract v1

Every candidate or runtime operation evidence record contains, where applicable:

- candidate Git SHA
- configuration SHA-256
- desired-state version
- environment
- UTC timestamp
- repository validator result
- plan result
- apply/reload result
- health result
- sanitized readback result
- drift result
- rollback result and both candidate identities when rollback occurs

Evidence contains metadata only. It must not contain access tokens, cookies, passwords, private keys, or runtime secret values.

The repository source and immutable release workflows are the evidence authority; live readback and apply records remain runtime certification evidence.
