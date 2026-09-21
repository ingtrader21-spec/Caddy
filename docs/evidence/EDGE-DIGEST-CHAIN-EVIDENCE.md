# Edge digest-chain repository evidence

This is source evidence only; no Kong, Caddy, Keycloak or Middleware runtime was contacted, reloaded or changed.

| Link | Authority | Verification |
|---|---|---|
| Middleware | `2862af0aa97367b18cb360af69212abe4243a1ac` | `deploy/public-api-route-contract.json` canonical sha256 `9c32daec…`; `.sha256` pin agrees; 117 routes (105 shared_edge / 10 denied / 2 private_only) |
| Kong | protected main `3e68cb2a4955bd71ddb3e839f4d9e3770465fc08` | `config/middleware-public-api-route-contract.v1.json` canonical sha256 `9c32daec…`; Middleware gateway retries 0; upstream `middleware-integration-api:8095` |
| Caddy | `config/edge-contract-chain.v1.json` | `middleware.public_contract_sha256 == kong.middleware_contract_sha256 == kong.required_sha256 == 9c32daec…`; `kong.source_sha` = Kong protected main; `kong.status = PASS` |
| Keycloak | `45a487d71a516ae3039b00c250752897469ffe7a` | caller contract carries `platform-command-client`, audience `middleware-api`; token matrix dimensions complete |
| Postman | `postman/Caddy-V3-Edge-Certification.postman_collection.json` | `postman.sha256` equals the sha256 of the committed collection bytes (LF); asserted by `tests/test_edge_api_url_webhook_boundaries.py` |

Strict cross-repo gate (`Kong/scripts/validate_kong_cross_repo_parity.py`, no `--allow-pending-lane-a`):

```
KONG_CROSS_REPO_PARITY=PASS
CADDY_KONG_MIDDLEWARE_DIGEST_CHAIN=PASS
KONG_FINAL_CONTRACT_REPIN=PASS
KEYCLOAK_CALLER_TOKEN_CONTRACT=PASS
```

Retained transitional state: the `api.codestra.co` legacy unknown-route fallback is still `TRANSITIONAL`; `UNKNOWN_ROUTE_FALLBACK=0` is not claimed. Caddy `source_sha`, `edge_contract_sha256` and `config_sha256` remain `GENERATED_AT_CERTIFICATION` until the exact-head certification fills them.
