# Maintenance Contract v1

## Service state model

```text
NORMAL
↕
MAINTENANCE
```

## Required elements

- host/path scope
- HTTP status code
- `Retry-After` behavior
- health/readiness exceptions
- operator exception criteria, if any
- activation mechanism
- deactivation mechanism

## Policy

Maintenance must be deterministic and explicit. It must not require random route editing, surprise source drift, or hidden path-specific bypasses. Fail-closed behavior applies when a maintenance path or health exception is not clearly approved.

## Repository posture

The current repository retains a clear route-boundary model and does not permit unapproved public fallback behavior to hide maintenance or outage conditions.
