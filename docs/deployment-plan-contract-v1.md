# Deployment Plan Contract v1

## Plan-only stage

A plan is derived from one identified candidate and is non-mutating. It reports candidate identity, environment, affected hosts, routes, upstreams, TLS/security changes, observability changes, configuration hash, previous configuration identity, and risk summary.

The plan result is `PLAN_ONLY`; it cannot reload Caddy, change DNS, mutate runtime files, or apply secrets.

## Pipeline

```text
candidate -> repository validation -> Caddy format/adapt -> Caddy validation -> policy validation -> DEPLOYABLE
```

A candidate is deployable only after every stage passes. The repository owns validation and planning; authorized runtime tooling owns any later apply/reload.
