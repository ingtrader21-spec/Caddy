# Caddy V3 — edge transport & Kong handoff audit

Source-only audit of the Caddy public edge against the Middleware V3 kernel
contract. Nothing here was applied to a runtime: no Caddy reload, no staging
apply, no Kong or Middleware change, no provider effect.

```text
AUDIT_DATE=2026-09-18
BASE_MAIN_SHA=84c2b7b3bce6d90764eac5eab362aed973f56056
AUDIT_BRANCH=mission/caddy-v3-edge-transport
CADDY_VALIDATOR_IMAGE=docker.io/library/caddy@sha256:ae4458638da8e1a91aafffb231c5f8778e964bca650c8a8cb23a7e8ac557aa3c (CADDY_VERSION=v2.10.0)
RUNTIME_APPLY_AUTHORIZED=NO
PRODUCTION_EFFECTS=0
PRODUCTION_GO=NO
```

## 1. Hard start gate — NOT SATISFIED

| Gate | Observed | State |
| --- | --- | --- |
| Middleware PR #280 | `f864c11` — OPEN, base `main` | NOT MERGED |
| Middleware PR #279 | `dabc348` — OPEN, base `main` | NOT MERGED |
| Middleware V3 edge contract | The six kernel operations exist only on local branch `mission/middleware-v3-platform-20260918` @ `38f8d8b48538b9ef3b95f1628a94cff677c53ce7` (98 routes, canonical sha256 `d764f2858a3ed3ac6a5f053f0e95b76769a6b7f9758c5cbfe399fb00abfb1854`). Not pushed, no PR, not descended from current Middleware `main` (`06a4ae7`). Middleware `main` still carries the v2 contract (92 routes, `7580123dead97ea342c704a57a3c8eed9f5dce69aab247d4b693db96bc7334d5`). | NOT FROZEN |
| Kong V3 edge contract | No branch in `ingtrader21-spec/Kong` contains `/platform/v1/kernel/describe`, `/platform/v1/commands` or `/platform/v1/operations`. Kong `main` @ `5ac254c6fb04579615e4d60d25efcc911d42a2e3` pins the v2 digest `7580123d…`. | NOT STARTED |

```text
MIDDLEWARE_280=OPEN
MIDDLEWARE_279=OPEN
MIDDLEWARE_V3_EDGE_CONTRACT=NOT_FROZEN
MIDDLEWARE_V3_SHA=38f8d8b48538b9ef3b95f1628a94cff677c53ce7   (provisional, local only)
MIDDLEWARE_V3_CONTRACT_SHA256=d764f2858a3ed3ac6a5f053f0e95b76769a6b7f9758c5cbfe399fb00abfb1854   (provisional)
MIDDLEWARE_V2_CONTRACT_SHA256=7580123dead97ea342c704a57a3c8eed9f5dce69aab247d4b693db96bc7334d5   (frozen on Middleware main 06a4ae7, pinned by Kong main and Caddy PR #174)
KONG_V3_SHA=NONE
KONG_V3_CONTRACT_SHA256=NONE
```

Consequence: this mission is confined to audit and static preparation. No
Caddy parity is frozen against the provisional V3 digest, no PR is opened for
V3 parity, and nothing is merged.

## 2. Config discovery (all active Caddy authority on `main`)

Root `Caddyfile` → `admin 127.0.0.1:2019`, `import snippets/*.caddy`,
`import sites/*.caddy`. No JSON config, no generated fragments, no
environment-specific includes. Every upstream is an environment variable whose
non-secret reference values live in `config/runtime-values.example`.

| Source | Host | Matcher | Upstream | Rewrite | Header policy | TLS | State |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sites/api.codestra.co.caddy` | `api.codestra.co` | `@kong` explicit path list (`/api/v1/control*` … `/v1/intake*`) | `{$CADDY_KONG_UPSTREAM}` (ref `127.0.0.1:8000`) | none | `Host {host}`, `X-Real-IP {remote_host}` | ACME | ACTIVE_PUBLIC |
| `sites/api.codestra.co.caddy` | `api.codestra.co` | `@realtime` `/ws/agent /api/v1/realtime/sessions /healthz /readyz /version` | `{$CADDY_REALTIME_UPSTREAM}` (ref `127.0.0.1:18102`) | none | same | ACME | ACTIVE_PUBLIC (transitional) |
| `sites/api.codestra.co.caddy` | `api.codestra.co` | **catch-all `handle`** | `{$CADDY_LEGACY_API_UPSTREAM}` (ref `127.0.0.1:18101`) | none | same | ACME | **ACTIVE_PUBLIC (transitional fallback)** |
| `sites/automation.codestra.co.caddy` | `automation.codestra.co` | `not remote_ip {$CADDY_EDITOR_ADMIN_CIDRS}` → 404; else all | `{$CADDY_KONG_UPSTREAM}` | none | same | ACME | ACTIVE_PUBLIC (admin CIDR gated) |
| `sites/n8n-editor.community.caddy` | `{$CADDY_N8N_EDITOR_HOST}` | `@never_public` → 404; else all | `{$CADDY_N8N_OAUTH2_PROXY_UPSTREAM}` | none | strips `X-Auth-Request-*`, `X-Forwarded-User/Email/Groups`, `Authorization` | ACME | ACTIVE_PUBLIC (oauth2-proxy gated) |
| `sites/codestra.media.observability.caddy` | `graf.` / `supe.` / `bao.codestra.media` | host; `bao` CIDR gated else 403 | Grafana / Superset / OpenBao refs | none | strips `X-Auth-Request-*`, `X-Authenticated-*`, `X-Codestra-Gateway-Secret` | ACME | ACTIVE_PUBLIC (separate monitoring gateway) |
| `sites/kyyow.com.caddy` | six `*.kyyow.com` hosts | host | Kyyow refs | none | strips `X-Authenticated-*` | ACME | ACTIVE_PUBLIC (unrelated product) |

```text
UNKNOWN_ACTIVE_ROUTE_SOURCES=0
CADDY_KONG_UPSTREAM={$CADDY_KONG_UPSTREAM}   reference 127.0.0.1:8000
CADDY_KONG_PORT=8000 (reference; Kong data plane)
KONG_TO_MIDDLEWARE=middleware-integration-api:8095 (Kong main, production routes)
```

## 3. Findings on `main` (84c2b7b)

### 3.1 V3 kernel paths have no source-proven Kong handoff — CADDY_CHANGE_REQUIRED=YES

The `@kong` matcher on `main` lists sixteen explicit prefixes. It does **not**
contain `/platform/v1`, `/v2/automation` or `/api/v1/odoo/events`. Every
request outside the list falls through to the catch-all
`reverse_proxy {$CADDY_LEGACY_API_UPSTREAM}`.

`scripts/caddy_v3_edge_probe.py` run against the JSON that the CI-pinned
Caddy image adapts from `main` (identical result with a checksum-verified
local v2.10.0 binary):

```text
FAIL V3_KERNEL  POST   /platform/v1/commands                             upstream=127.0.0.1:18101
FAIL V3_KERNEL  GET    /platform/v1/kernel/describe                      upstream=127.0.0.1:18101
FAIL V3_KERNEL  GET    /platform/v1/operations/{operation_id}            upstream=127.0.0.1:18101
FAIL V3_KERNEL  GET    /platform/v1/operations/{operation_id}/timeline   upstream=127.0.0.1:18101
FAIL V3_KERNEL  POST   /platform/v1/operations/{operation_id}/cancel     upstream=127.0.0.1:18101
FAIL V3_KERNEL  POST   /platform/v1/operations/{operation_id}/replay     upstream=127.0.0.1:18101
FAIL FAMILY     POST   /v2/automation/commands                           upstream=127.0.0.1:18101
FAIL FAMILY     GET    /v2/automation/jobs/{job_id}                      upstream=127.0.0.1:18101
FAIL FAMILY     POST   /api/v1/odoo/events                               upstream=127.0.0.1:18101
FAIL NEGATIVE   GET    /metrics                                          upstream=127.0.0.1:18101
FAIL NEGATIVE   GET    /internal/v1/anything                             upstream=127.0.0.1:18101
PASS NEGATIVE   POST   /v1/integrations/n8n/commands                     upstream=127.0.0.1:8000
PASS HEADER_UP  authorization,idempotency,trace untouched
CADDY_V3_EDGE_PROBE=FAIL FAILURES=15
```

Classification of `CADDY_LEGACY_API_UPSTREAM`:

- Source: environment-controlled; the Caddy source contract does not constrain
  what listens there. `config/caddy-kong-contract.v1.json` records
  `legacyFallbackTemporarilyAllowed: true`.
- Historical runtime evidence (`codestra-production-platform` @ `119ff36`,
  `operations/caddy/CADDY-KONG-CONTRACT.md`, `reports/claude-system-audit/09_CADDY.md`):
  `127.0.0.1:18101` was `codestra-caddy-upstream-gateway`, an internal fan-out
  Caddy that forwarded to Kong. The current historical reference
  (`release/production-activation`) has since moved its catch-all to
  `codestra-kong-kong-gateway-1:8000` directly and denies `/internal*` with 404.
- Verdict: **not a source-proven direct Middleware or provider route**, but
  **not a source-proven Kong handoff either**. For the V3 kernel operations the
  Kong handoff is missing at the source level, which is mission §34 case B.

```text
ACTIVE_PUBLIC_DIRECT_MIDDLEWARE_ROUTES=0   (no site targets :8095, http(s)://middleware, or the integration container; validator enforces this)
ACTIVE_PUBLIC_DIRECT_PROVIDER_ROUTES=0     (no Odoo/n8n/Klyrow/Telnexa/VICIdial/telephony upstream in any site)
ACTIVE_PUBLIC_MIDDLEWARE_8080=0            (":8080" appears in no active config source)
BUSINESS_CAPABILITY_ROUTING_IN_CADDY=0     (no email.send/sms.send/call.originate/automation.submit/crm.*/campaign.* token)
PUBLIC_API_TO_KONG=FAIL on main for /platform/v1*, /v2/automation*, /api/v1/odoo/events*  (legacy fallback catches them)
MISSING_KONG_HANDOFF=/platform/v1* /v2/automation* /api/v1/odoo/events*
```

### 3.2 Remediation already in flight — PR #174

`ingtrader21-spec/Caddy#174` (`codex/cross-repo-authority-20260916` @
`1ffff826b32c2934c8de3fafdc8b179638462c42`, MERGEABLE/CLEAN, `validate`,
`validate-source`, `validate-merge-result` green, awaiting one approval) pins
the frozen v2 digest `7580123d…`, generates exact method+path rules for the 92
v2 routes, and adds a prefix-level `@kong` matcher that includes
`/v2/automation*`, `/platform/v1*` and `/api/v1/odoo/events*` ahead of the
legacy fallback.

Probe against the JSON adapted from `1ffff82`:

```text
PASS V3_KERNEL  POST   /platform/v1/commands                             upstream=127.0.0.1:8000
PASS V3_KERNEL  GET    /platform/v1/kernel/describe                      upstream=127.0.0.1:8000
PASS V3_KERNEL  GET    /platform/v1/operations/{operation_id}            upstream=127.0.0.1:8000
PASS V3_KERNEL  GET    /platform/v1/operations/{operation_id}/timeline   upstream=127.0.0.1:8000
PASS V3_KERNEL  POST   /platform/v1/operations/{operation_id}/cancel     upstream=127.0.0.1:8000
PASS V3_KERNEL  POST   /platform/v1/operations/{operation_id}/replay     upstream=127.0.0.1:8000
PASS FAMILY     (all three)                                              upstream=127.0.0.1:8000
PASS NEGATIVE   DELETE /platform/v1/commands, PUT …/replay, GET /platform/v1/metrics, GET /v2/automation/unknown, POST /v1/integrations/n8n/commands  → Kong (404/405 there)
FAIL NEGATIVE   GET    /metrics                                          upstream=127.0.0.1:18101
FAIL NEGATIVE   GET    /internal/v1/anything                             upstream=127.0.0.1:18101
PASS HEADER_UP  authorization,idempotency,trace untouched
CADDY_V3_EDGE_PROBE=FAIL FAILURES=2
```

The host/prefix rule transports all six V3 kernel operations without one rule
per operation, so on top of PR #174:

```text
CADDY_V3_ROUTE_CHANGES_REQUIRED=NO
```

PR #174's generator (`scripts/generate_middleware_edge_contract.py`) was run
twice on a scratch copy of `1ffff82`; both runs produced identical output and,
after LF normalisation, byte-identical content to the committed
`config/caddy-kong-contract.v1.json` and `sites/api.codestra.co.caddy`.

```text
CONFIG_GENERATION_DETERMINISTIC=PASS (PR #174 generator; main has no generator)
```

### 3.3 Residual after PR #174 — private namespace still reaches the fallback

`GET /metrics` and anything under `/internal*` on `api.codestra.co` still
resolve to `CADDY_LEGACY_API_UPSTREAM`. Kong has no `/metrics` or `/internal`
route (its Prometheus metrics sit on a private status listener), so these would
404 if sent to Kong; the historical reference refused `/internal*` at the edge
with `respond 404`. Whether the fallback's live target exposes a `/metrics`
endpoint cannot be proven from source.

```text
PUBLIC_MIDDLEWARE_METRICS_ROUTE=0        (no Caddy rule targets a metrics endpoint; Kong exposes none)
LEGACY_FALLBACK_CARRIES=/metrics /internal*   (residual until the fallback is removed or the namespace is refused)
```

Recommended edge-hygiene change (independent of the V3 contract, to be folded
into the eventual Caddy V3 PR or a separate hardening PR — not applied here):

```caddyfile
	route {
		# Private namespaces never cross the public edge; the historical
		# reference refused /internal* the same way.
		@private_namespace path /internal* /metrics
		handle @private_namespace {
			respond "Not Found" 404
		}
		…
```

### 3.4 Header and transport invariants (main and PR #174 identical)

| Invariant | Evidence | Result |
| --- | --- | --- |
| `Authorization` preserved | Kong handoff sets only `Host` and `X-Real-IP`; no `header_up Authorization` / `-Authorization` (validator forbids both); redacted from access logs only | PASS |
| `X-Correlation-ID` preserved | not touched by Caddy; Kong `correlation-id` plugin (`generator: uuid`, `echo_downstream: true`) only generates when absent | PASS |
| `traceparent` / `tracestate` preserved | not touched by Caddy | PASS |
| `Idempotency-Key` preserved | not touched by Caddy; no Caddy cache/dedupe/state directive | PASS, `CADDY_DURABLE_IDEMPOTENCY=0` |
| Method / path / query preserved | no `rewrite`, `uri`, `method` or `handle_path` directive on the API host; `{operation_id}` arrives unchanged | PASS |
| Body semantics | only `request_body max_size 10MB`; no body inspection | PASS, `BODY_SEMANTICS_IN_CADDY=0` |
| Trusted forwarding | `X-Real-IP {remote_host}` from the TCP peer; Caddy appends the peer to `X-Forwarded-For` and sets `X-Forwarded-Proto`/`X-Forwarded-Host` per its reverse-proxy defaults; no `trusted_proxies` on the public edge, so client-supplied values never become the trusted peer | PASS |
| Identity headers | `api.codestra.co` passes `X-Authenticated-*`, `X-User-ID`, `X-Roles`, … through untouched; Kong strips all of them per route (`kong.service.request.clear_header`) before minting `X-Codestra-Contract-*`; Caddy is forbidden by validator from creating any | PASS, `CADDY_IDENTITY_AUTHORITY=0` |
| Admin isolation | `admin 127.0.0.1:2019`; no Kong Admin, OpenBao management (`bao.codestra.media` is CIDR-gated to TEST-NET refs, 403 otherwise), DB, Redis, NATS or Temporal route | PASS |
| Kong unavailable | reverse_proxy to `CADDY_KONG_UPSTREAM` has no `lb_policy`/fallback upstream; Caddy answers 502; no route to Middleware/:8080/provider on failure | PASS, `KONG_UNAVAILABLE_DIRECT_BYPASS=0`, `CADDY_PROVIDER_FAILOVER_LOGIC=0` |
| Retired `/v1/integrations/n8n/*` | routed to Kong, which has no route → 404 (existing contract) | PASS |

## 4. Cross-repo parity for the six V3 kernel operations

| Operation | Middleware | Kong | Caddy `main` | Caddy PR #174 |
| --- | --- | --- | --- | --- |
| `POST /platform/v1/commands` | YES (provisional `38f8d8b`; NO on main) | NO | legacy fallback | via Kong (prefix) |
| `GET /platform/v1/kernel/describe` | YES (provisional; NO on main) | NO | legacy fallback | via Kong (prefix) |
| `GET /platform/v1/operations/{operation_id}` | YES (provisional; NO on main) | NO | legacy fallback | via Kong (prefix) |
| `GET /platform/v1/operations/{operation_id}/timeline` | YES (provisional; NO on main) | NO | legacy fallback | via Kong (prefix) |
| `POST /platform/v1/operations/{operation_id}/cancel` | YES (provisional; NO on main) | NO | legacy fallback | via Kong (prefix) |
| `POST /platform/v1/operations/{operation_id}/replay` | YES (provisional; NO on main) | NO | legacy fallback | via Kong (prefix) |

```text
CROSS_REPO_PARITY=BLOCKED (Middleware V3 not on main; Kong V3 absent)
```

## 5. Source gates on `main` (84c2b7b) — all green

```text
scripts/test_caddy_kong_contract.py           3 tests OK
scripts/validate_repository.py                CADDY_REPOSITORY_AUTHORITY=PASS … DIRECT_MIDDLEWARE_FOR_KONG_PATHS=DENIED
scripts/validate_community_n8n.py             COMMUNITY_N8N_SECURITY=PASS
scripts/test_observability_exposure.py        18 tests OK
scripts/validate_observability_exposure.py    CADDY_OBSERVABILITY_URL_CONTRACT=PASS, CADDY_PRIVATE_NATIVE_ROUTES=0
scripts/validate_kyyow_ingress.py             KYYOW_INGRESS_CONTRACT=PASS
python -m unittest discover -s tests          7 tests OK (+12 new probe tests OK, 1 skipped without CADDY_BIN)
caddy fmt (v2.10.0)                           byte-identical for all five site files (LF blobs)
caddy validate (CI image ae445863…)           Valid configuration
caddy adapt --validate (CI image)             exit 0
gitleaks 8.30.1 dir (git archive HEAD)        no leaks found (47 files)
CADDY_VALIDATOR=PASS  CADDY_CONFIG_PARSE=PASS  CADDY_CONFIG_VALIDATE=PASS  FAILURES=0  ERRORS=0  SECRET_SCAN=PASS  GITLEAKS=PASS
```

## 6. Static preparation delivered on this branch

- `scripts/caddy_v3_edge_probe.py` — resolves the V3 kernel, family and
  negative probes plus the handoff header policy through adapted JSON. Prints
  `CADDY_V3_EDGE_PROBE=PASS|FAIL` and exits non-zero on any failure. Intended
  to be wired into `scripts/validate-ci.sh` after the adapt step once PR #174
  has landed.
- `tests/test_caddy_v3_edge_probe.py` — fixture tests proving the probe
  detects the legacy-fallback shape and accepts the Kong-prefix shape, plus a
  `CADDY_BIN`-gated test that adapts the repository config and asserts every V3
  kernel probe lands on Kong (fails on `main` today by design; passes once the
  prefix handoff is merged).

## 7. Blockers and next action

```text
BLOCKERS=
  1. Middleware #280 / #279 open; V3 kernel contract only on an unpushed, non-main-based branch.
  2. Kong has no V3 kernel routes and pins the v2 digest.
  3. Caddy PR #174 (v2 parity + prefix handoff) awaits one independent approval.
NEXT_ACTION=
  a. Land Caddy PR #174 on its exact SHA 1ffff82 (independent approval; CI already green) — this removes the V3 transport bypass on main without touching the V3 contract.
  b. Middleware: merge #280/#279, land the V3 platform branch on main, publish the final contract digest.
  c. Kong: add the six V3 kernel routes, pin the final digest.
  d. Caddy V3 PR (one PR, from origin/main after a–c): regenerate config/middleware-public-api-route-contract.v1.json from the frozen digest, run the generator twice, add the V3 kernel probes to the canonical matrix, wire scripts/caddy_v3_edge_probe.py into validate-ci.sh, refuse /internal* and /metrics at the edge; exact-SHA CI + independent review; then isolated staging edge certification.
```
