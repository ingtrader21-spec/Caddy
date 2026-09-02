# Rapid Domain Production Onboarding

A new Codestra-managed website/domain should be onboarded from one reviewed manifest rather than by editing Caddy manually on the server.

Manifest inputs: domain, environment, upstream/service name, health/readiness path, TLS mode, security-header profile, public/private classification, Kong/API path bindings, Keycloak/auth requirement, redirects, canonical host, rate-limit profile, release SHA/image digest and owner.

Automation should validate DNS readiness, generate deterministic Caddy config, run `caddy validate`, confirm no hostname collision, check upstream health, build/read the immutable release identity, deploy to staging, run HTTPS/security-header/redirect smoke tests, then promote the exact reviewed config to production with runtime checksum read-back.

Never publish PostgreSQL, Redis, OpenBao Raft, provider/admin ports, internal metrics or private Middleware adapters. New public APIs route Caddy -> Kong -> Middleware. Identity routes go Caddy -> Keycloak.

Production activation requires DNS/TLS PASS, config validation PASS, staging smoke PASS, rollback snapshot PASS, exact config checksum match and no unresolved Critical/High findings. SSH policy is out of scope.
