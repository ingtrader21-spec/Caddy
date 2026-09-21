# Environment Promotion Contract v1

## Promotion chain

```text
development -> staging -> production
```

Promotion moves an identified candidate; it does not regenerate an unrelated configuration in the target environment.

## Rules

- only adjacent promotion edges are allowed
- a candidate environment must equal the promotion target
- development or staging upstreams cannot be promoted as production identity
- production secrets are never copied into development or staging evidence
- unknown environment names fail closed
- the production read-only canary consumes exact source and configuration identities

Live deployment authorization remains outside Git and requires the protected release process.
