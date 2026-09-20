# M5 — Desired State, Drift & Deployment Reliability

## Governing principle

Caddy is the secure ingress / Edge TLS plane. Kong remains the API gateway behind it. Caddy does not absorb Keycloak, Middleware, Odoo, or n8n responsibilities.

## Mission structure

### 1. Canonical desired state
- define the reviewed Caddy desired state as the source of truth
- keep the root config, route groups, and runtime variable contracts aligned
- reject unreviewed local or ad hoc runtime drift

### 2. Validate
- validate syntax, route precedence, TLS integrity, and route contract compatibility
- enforce fail-closed behavior for unknown hosts and forbidden paths
- confirm required security headers and request redaction remain in place

### 3. Plan
- build the deployment plan from the canonical desired state
- record the planned host, upstreams, and security policy boundary
- keep plans environment-aware and explicit about promotion gates

### 4. Approved apply / reload
- require explicit review and approval before apply or reload
- keep reload operations deterministic and scoped to the reviewed candidate
- reject blind reloads when validation or health checks fail

### 5. Readback
- capture the live runtime configuration after apply/reload
- confirm the active runtime matches the candidate state and intended policy
- record any drift or acceptance gaps before promotion proceeds

### 6. Reconciliation
- compare live state against the desired state
- classify drift as accepted, rejected, or remediation-required
- do not permit reconciliation to silently reintroduce bypass or legacy exposure

### 7. Drift detection
- detect route changes, upstream changes, and policy drift
- alert on unauthorized configuration edits or stale host declarations
- preserve the source-of-truth boundary between Caddy and downstream systems

### 8. Environment promotion
- promote through defined stages with explicit review gates
- prevent production-only credentials or routes from leaking into lower environments
- maintain separation between development, staging, and production policy

### 9. CI/CD gates
- enforce contract validation in CI
- block merge or promotion where route ownership, TLS boundary, or security policy is violated
- require readback and evidence capture before release acceptance

### 10. Rollback
- define clear rollback criteria based on validation outcome, health regression, or policy drift
- keep rollback evidence and operator approval records
- restore the last known-good configuration without restoring insecure defaults

### 11. Deployment tests
- verify host/path/method routing under deployment conditions
- validate fail-closed behavior, TLS, upstream errors, and cover any migration-only fallback behavior
- test that no direct access to business systems occurs through the Caddy edge

### 12. Freeze gate
- desired state and live state match the approved candidate
- all promotion and rollback gates are complete
- deployment evidence is sealed and reviewable

## Mission status

CADDY MISSION 5 — DESIRED STATE, DRIFT & DEPLOYMENT RELIABILITY:
IMPLEMENTATION COMPLETE — RUNTIME CERTIFICATION PENDING
