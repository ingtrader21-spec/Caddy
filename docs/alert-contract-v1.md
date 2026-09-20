# Alert Contract v1

## Trigger conditions

Alerts must fire for operational conditions that meaningfully affect site health or policy integrity.

### Required alert classes

- TLS certificate or renewal failure
- route mismatch or unexpected host mismatch
- repeated upstream failure or health regression
- reload failure or config validation failure
- security-header drift
- redaction regression in access logs
- unexpected admin exposure or port binding drift

## Alert scope

Alerts are edge-focused and operational. They do not assert business authorization correctness or service-level policy outside the ingress plane.
