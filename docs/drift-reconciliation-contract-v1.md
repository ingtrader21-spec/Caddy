# Drift & Reconciliation Contract v1

## Drift classes

- `IN_SYNC`: expected and effective values match exactly
- `DRIFTED`: an expected value exists but differs
- `MISSING`: an expected value is absent
- `UNEXPECTED`: an effective value is not in desired state
- `UNKNOWN`: effective state is unavailable or cannot be trusted

`UNKNOWN` fails closed for production promotion.

## Reconciliation

```text
Desired State -> Readback -> Difference -> Plan -> Reviewed correction
```

Readback is sanitized and must not expose secrets. Security-sensitive production drift is not auto-overwritten; correction requires an identified candidate, policy validation, and authorization. The same desired state applied twice returns `NO_CHANGE` on the second plan.
