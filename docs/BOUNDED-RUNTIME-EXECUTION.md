# Bounded Caddy runtime execution

This release path certifies one immutable production image in two ordered environments.

1. `bounded-staging-runtime` verifies the protected production SHA, registry digest, Cosign signature, source attestation, OCI labels, configuration checksum, non-root runtime, and staging-only protected file paths. It starts the candidate in a dedicated Docker bridge network and publishes only fixed loopback ports on the staging host.
2. `production-readonly-canary` receives the exact tuple emitted by staging. It validates the candidate with networking disabled, reads the actual `codestra-caddy` container before and after the probes, and requires byte-identical runtime evidence.

The production canary is non-mutating. It does not call Compose, start a second edge, reload Caddy, change DNS or firewall state, modify SSH, or send an application write request.

## Required runner labels

```text
caddy-staging-readonly
caddy-production-readonly
```

## Required protected environment variables

`staging-readonly`:

```text
CADDY_STAGING_ENV_FILE
CADDY_STAGING_DATA_SOURCE
CADDY_STAGING_MTLS_CLIENT_CERT
CADDY_STAGING_MTLS_CLIENT_KEY
CADDY_STAGING_MTLS_CA_CERT
```

`production-readonly`:

```text
CADDY_PRODUCTION_MTLS_CLIENT_CERT
CADDY_PRODUCTION_MTLS_CLIENT_KEY
CADDY_PRODUCTION_MTLS_CA_CERT
```

Every configured path must be absolute and resolve to an existing root-owned, non-symlinked file or directory on its bounded runner.
