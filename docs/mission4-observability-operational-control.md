# M4 — Observability & Operational Control

## Governing principle

Caddy is the secure ingress / Edge TLS plane. Kong remains the API gateway behind it. Caddy does not absorb Keycloak, Middleware, Odoo, or n8n responsibilities.

## Mission structure

### 1. Finish rollback
- preserve last-known-good configuration identity
- validate rollback target before cutover
- retain reload evidence and service health readback
- confirm rollback does not widen access or restore unapproved hosts

### 2. Configuration identity
- assign canonical source hash or fingerprint per accepted config
- bind config artifact to deployment environment
- record time, operator, and validation result
- ensure drift between source, runtime, and release evidence is visible

### 3. Monitoring contracts
- define access logs, error logs, and metrics contracts
- separate edge metrics from upstream business metrics
- keep observability data non-sensitive and reduce cardinality risk
- set explicit integration boundaries for Prometheus, Grafana, Loki, Alloy, and OpenTelemetry

### 4. Alerting
- alert on TLS failures, route mismatches, upstream errors, reload failures, and health regressions
- ensure alerting signals are actionable and scoped to edge-plane failure modes
- avoid alerting on internal business-state noise that belongs to downstream systems

### 5. Operational tests
- validate structured logging format and field redaction
- verify failed reload leaves previous config active
- test health/readiness assertions under normal and degraded conditions
- confirm request-id and correlation-id handling does not leak credentials

### 6. Evidence matrix
- store validation outputs for config, reload, health, and rollback
- preserve readback and drift evidence
- keep the evidence chain auditable and reviewable per environment

### 7. Freeze gate
- Caddy mission evidence is complete and stored
- operational contracts are documented and testable
- rollback path is proven with real evidence
- no production authorization exists without explicit deployment review

## Mission status

CADDY MISSION 4 — OBSERVABILITY & OPERATIONAL CONTROL:
IMPLEMENTATION COMPLETE — RUNTIME CERTIFICATION PENDING
