# Automated Production Gates

This repository is intended to support automated promotion without mandatory human pull-request approval, while preserving deterministic production safety gates.

## Merge policy
- Required approving reviews: 0.
- Required Code Owner reviews: off.
- Required status checks: on.
- Strict/up-to-date branch requirement: on.
- Conversation resolution: on.
- Force pushes and protected-branch deletion: blocked.
- Auto-merge: enabled.
- Administrator bypass is not part of the normal release path.

## Release policy
A merge does not authorize unsafe edge changes. Production promotion still requires source authority, immutable digest pinning where applicable, configuration validation, TLS/mTLS checks, secret-redaction checks, rollback evidence, staging/synthetic certification, and read-only production verification.

For server `65.109.65.169`, preserve TLS, Kong upstreams, WebSockets, timeouts, mTLS, request/credential redaction, source authority, and rollback evidence. Do not broaden filesystem or SSH access merely to make validation easier.
