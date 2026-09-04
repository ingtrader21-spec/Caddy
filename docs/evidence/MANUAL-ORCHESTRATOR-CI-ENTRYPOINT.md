# CI/CD entrypoint

The only production deployment entrypoint introduced by this change is `.github/workflows/manual-production-orchestrator.yml`. The reusable release and bounded-runtime workflows have no push or standalone manual trigger.
