# Reload & Rollback Contract v1

## Safe reload requirement

A Caddy reload is valid only when:

- the candidate configuration is reviewed and pinned to a known artifact
- validation checks pass
- host and route contracts remain unchanged
- config checksum evidence exists
- health checks remain acceptable before and after reload

## Failed reload policy

When a reload or validation step fails:

- the operator must not leave the system in an unknown state
- the prior known-good configuration must remain available
- rollback must be rehearsed or validated against that prior configuration

## Rollback rule

Rollback must restore the last known-good configuration and revalidate the effective runtime state before any route or traffic restoration is treated as complete.

## Configuration identity

Every deployment or reload evidence record must identify the Git SHA,
configuration hash, environment, and UTC timestamp. These identifiers are
metadata only and must not contain secrets.

## Operational boundary

Caddy source changes do not authorize live reload, DNS changes, or production traffic cutover. Those remains explicit runtime authority outside Git.
