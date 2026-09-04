# Manual production orchestrator gate matrix

| Gate | Failure behavior |
|---|---|
| Exact protected production SHA | Stop before build |
| Required source checks | Stop before build |
| Protected environment policy | Stop before build |
| Immutable image labels/digest | Stop before staging |
| Signature and source attestation | Stop before staging |
| HIGH/CRITICAL scan | Stop before publish |
| Historical rollback rehearsal | Stop before publish |
| Bounded staging evidence | Stop before production canary |
| Production read-only snapshot equality | Stop before activation |
| Captured live rollback baseline | Stop before production mutation |
| Activation health/readback | Restore captured baseline |
| Rollback health/readback | Hard failure; no production-go evidence |
| Final evidence-chain hashes | No `FULL_PRODUCTION_GO` |
