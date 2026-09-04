# Manual production orchestrator source change

```text
DATE=2026-09-03
BASE_BRANCH=development
IMPLEMENTATION_BRANCH=ci/manual-one-click-production-orchestrator-20260903
RUNTIME_MUTATED=false
PRODUCTION_CONTAINER_CHANGED=false
PUBLIC_TRAFFIC_CHANGED=false
DNS_CHANGED=false
FIREWALL_CHANGED=false
SSH_CHANGED=false
```

This change converts the existing automatic production release/runtime workflows into reusable gates called by one manual production orchestrator. It adds exact live rollback-baseline capture, dynamic rollback consumption, distinct protected staging/read-only/activation environments, and final evidence-chain verification.

No workflow run created by this source change is itself production authorization. The orchestrator can report `FULL_PRODUCTION_GO` only after all protected jobs execute successfully against the exact production SHA/image/configuration tuple.
