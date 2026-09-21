# PAS-145 — Edge/API/Postman and V3 probe certification

## Source

- Repository: `ingtrader21-spec/Caddy`
- Parent candidate: PR #175
- Starting head: `56fd73d1647f7023cb07bdb14b1f72522c7b48d8`
- Agent-2 branch: `mission/caddy-pas145-edge-certification-20260920`
- Primary local checkout remains untouched at `C:\Users\agent\Documents\GitHub\Caddy`
- Primary preserved head: `1f72905471645d490e7bd4ddf20a11d846df1446`

PAS-145 owns certification tooling, Postman artifacts and source/adapted-route evidence. It does not own PAS-162 digest-chain authority files and does not perform PAS-146 reload/deployment/rollback actions.

## Real Caddy adapter

The repository was adapted with the checksum-verified official Caddy v2.10.0 Windows amd64 release.

- Caddy: `v2.10.0 h1:fonubSaQKF1YANl8TXqGcn4IbIRUDdfAkpcsfI/vX5U=`
- release ZIP SHA-512:
  `cb97adb2bff5de752e470486ae72d55a6ddcfe4bfa43f09ed849260955df7f61385ac1e2d28fc80458b6910d71fa38d4295bb0689263dcc1743f2050d847c2ad`
- adapted JSON SHA-256:
  `0850afc881c99ce9c1091874de237713404b4cd753c07b85670d2cfe55088d42`
- synthetic explicit Kong upstream:
  `127.0.0.1:8000`
- synthetic legacy upstream:
  `127.0.0.1:18101`

This is source/adapted-config certification only. No Caddy reload, deployment, DNS, certificate cutover or provider effect occurred.

## V3 probe

The real adapted JSON was passed to `scripts/caddy_v3_edge_probe.py` with an explicit Kong upstream.

Certified:

- all six V3 kernel probes route to Kong;
- `/v2/automation/*` probes route to Kong;
- canonical Odoo and n8n ingress route to Kong;
- wrong-method/unknown canonical namespaces do not reach the legacy upstream;
- `/metrics`, `/metrics/*`, `/internal/*` return public 404 before an upstream;
- pending Telnexa/VICIdial/n8n-ack/observability/SMS ingress returns 404 before the legacy fallback;
- Authorization, X-Correlation-ID, Idempotency-Key, traceparent and tracestate are not overwritten/deleted;
- all contracted spoofable identity/consumer headers are stripped before the Kong handoff.

Result:

```text
CADDY_V3_EDGE_PROBE=PASS FAILURES=0
```

The adapted-route resolver also reports:

```text
CADDY_ADAPTED_ROUTE_MATRIX=PASS CANONICAL=11 FAIL_CLOSED=28 LEGACY_PROBES=1
```

The one legacy probe represents the explicitly transitional unknown-route fallback. PAS-145 does not claim `UNKNOWN_ROUTE_FALLBACK=0`.

## Registry/API/private/webhook certification

`scripts/certify_caddy_edge_api.py` validates the PAS-145-owned behavior against the checked-in PAS-162 registries plus the real adapted JSON.

Current parallel result:

```text
CADDY_EDGE_API_CERTIFICATION=PENDING_PAS_162
API_URL_REGISTRY=PASS
PUBLIC_HOST_REGISTRY=PASS
UPSTREAM_REGISTRY=PASS
WEBHOOK_REGISTRY=PASS
PLATFORM_V1_TO_KONG=PASS
AUTOMATION_V2_TO_KONG=PASS
PRIVATE_NAMESPACE_DENIAL=PASS
DATABASE_PUBLIC_EXPOSURE=0
SPOOFED_IDENTITY_HEADERS_STRIPPED=PASS
PRESERVED_TRANSPORT_HEADERS=PASS
PUBLIC_API_DIRECT_TO_MIDDLEWARE=0
PUBLIC_API_DIRECT_TO_ODOO=0
PUBLIC_API_DIRECT_TO_N8N=0
FAILURE_BYPASS_PATHS=0
POSTMAN_API_CERTIFICATION=PASS
POSTMAN_WEBHOOK_CERTIFICATION=PASS
POSTMAN_PRIVATE_ROUTE_CERTIFICATION=PASS
MIDDLEWARE_KONG_CADDY_DIGEST_CHAIN=PENDING_PAS_162
POSTMAN_DIGEST_CHAIN=PENDING_PAS_162
UNKNOWN_ROUTE_FALLBACK=TRANSITIONAL
CADDY_LIVE_RELOAD_AUTHORIZED=NO
```

The pending state is deliberate. PAS-162 still owns the stale Kong digest and Postman digest bindings in `config/edge-contract-chain.v1.json`.

## Deterministic Postman

Repository-owned generator:

`scripts/generate_caddy_edge_certification_postman.py`

Generated artifacts:

- `postman/Caddy-V3-Edge-Certification.postman_collection.json`
- `postman/Caddy-V3-Edge-Certification.postman_environment.json`

Digests:

- collection SHA-256: `5a81fb5725a7ca16886cfb4e93eca02258feeeb668427611103e1056dd91bfb3`
- environment SHA-256: `a64883b955b8bd39cd339c4575dda789b5ca2fc6ec7fc4bf772550859b73fb97`

Safety defaults:

- `base_url=https://127.0.0.1:9443`
- `RUN_CADDY_EDGE_CERTIFICATION=false`
- bearer-token variables are empty
- collection-level pre-request guard blocks accidental live execution

Coverage includes positive API transport probes, wrong methods, private routes, internal database routes, all pending-contract public denials and wrong-method webhook probes.

## Local gates

```text
FULL_PYTEST=112 passed
SUBTESTS=18 passed
CADDY_REPOSITORY_AUTHORITY=PASS
CADDY_TO_KONG_CONTRACT=PASS
KONG_ROUTE_CONTRACT_BIDIRECTIONAL=PASS
CADDY_KONG_CONTRACT_TESTS=14/14 PASS
CADDY_POSTMAN_GENERATION=PASS
CADDY_V3_EDGE_PROBE=PASS
CADDY_ADAPTED_ROUTE_MATRIX=PASS
```

## Final dependency

PAS-145 can leave the dependency-waiting state only after PAS-162 lands its exact accepted digest-chain authority. Then rerun:

```text
python scripts/certify_caddy_edge_api.py <adapted.json> --kong-upstream <exact-kong-upstream>
```

without `--allow-pending-pas162`.

Final required result:

```text
CADDY_EDGE_API_CERTIFICATION=PASS
MIDDLEWARE_KONG_CADDY_DIGEST_CHAIN=PASS
POSTMAN_DIGEST_CHAIN=PASS
LOCAL_REMOTE_SYNC=PASS
```

No reload/deployment/production effect is authorized by PAS-145.
