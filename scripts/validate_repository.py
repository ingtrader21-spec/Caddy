#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
SITE_PATH = ROOT / "sites" / "api.codestra.co.caddy"
OBSERVABILITY_SITE_PATH = ROOT / "sites" / "observability-browser.caddy"
OBSERVABILITY_DENY_PATH = ROOT / "sites" / "observability-private-deny.caddy"
ROOT_CADDYFILE = ROOT / "Caddyfile"
SECURITY_HEADERS = ROOT / "snippets" / "security_headers.caddy"
CONTRACT_PATH = ROOT / "config" / "caddy-kong-contract.v1.json"
RUNTIME_EXAMPLE = ROOT / "config" / "runtime-values.example"
INTEGRATION_DOC = ROOT / "docs" / "CADDY_KONG_INTEGRATION.md"

for path in (
    README_PATH,
    SITE_PATH,
    OBSERVABILITY_SITE_PATH,
    OBSERVABILITY_DENY_PATH,
    ROOT_CADDYFILE,
    SECURITY_HEADERS,
    CONTRACT_PATH,
    RUNTIME_EXAMPLE,
    INTEGRATION_DOC,
):
    if not path.exists():
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_required_file:{path.relative_to(ROOT)}")

README = README_PATH.read_text(encoding="utf-8")
SITE = SITE_PATH.read_text(encoding="utf-8")
OBSERVABILITY_SITE = OBSERVABILITY_SITE_PATH.read_text(encoding="utf-8")
OBSERVABILITY_DENY = OBSERVABILITY_DENY_PATH.read_text(encoding="utf-8")
CADDYFILE = ROOT_CADDYFILE.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
RUNTIME = RUNTIME_EXAMPLE.read_text(encoding="utf-8")

required_repositories = (
    "appolon1908-hue/Caddy",
    "appolon1908-hue/Kong",
    "appolon1908-hue/Keycloak",
    "appolon1908-hue/Middleware-",
    "appolon1908-hue/codestra-production-platform",
)
for value in required_repositories:
    if value not in README:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_reference:{value}")

if CONTRACT.get("schema") != "codestra.caddy-kong-edge.v1":
    raise SystemExit("CADDY_AUTHORITY_ERROR=unsupported_contract_schema")
if CONTRACT.get("principalRepository") != "appolon1908-hue/Caddy":
    raise SystemExit("CADDY_AUTHORITY_ERROR=caddy_not_principal")
if CONTRACT.get("gatewayRepository") != "appolon1908-hue/Kong":
    raise SystemExit("CADDY_AUTHORITY_ERROR=wrong_gateway_principal")
if CONTRACT.get("referenceRepository") != "appolon1908-hue/codestra-production-platform":
    raise SystemExit("CADDY_AUTHORITY_ERROR=wrong_reference_repository")
if CONTRACT.get("canonicalHost") != "api.codestra.co":
    raise SystemExit("CADDY_AUTHORITY_ERROR=wrong_canonical_host")

identity = CONTRACT.get("identityBoundary") or {}
expected_identity = {
    "caddyAuthenticatesUsersOrServices": False,
    "authorizationHeaderForwardedToKong": True,
    "caddyCreatesTrustedApplicationIdentityHeaders": False,
    "kongPerformsOidcJwtAndScopePolicy": True,
    "middlewareRevalidatesPrivilegedAuthorization": True,
}
for key, expected in expected_identity.items():
    if identity.get(key) is not expected:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=identity_boundary:{key}")

migration = CONTRACT.get("migration") or {}
if migration.get("productionCutoverAuthorizedBySource") is not False:
    raise SystemExit("CADDY_AUTHORITY_ERROR=source_must_not_authorize_cutover")
if migration.get("runtimeInventoryRequiredBeforeCutover") is not True:
    raise SystemExit("CADDY_AUTHORITY_ERROR=runtime_inventory_gate_missing")
if migration.get("rollbackRehearsalRequiredBeforeCutover") is not True:
    raise SystemExit("CADDY_AUTHORITY_ERROR=rollback_gate_missing")

if "historical runtime/deployment/reconciliation" not in README:
    raise SystemExit("CADDY_AUTHORITY_ERROR=platform_not_reference_only")
if "operations/caddy/api.codestra.co.caddy" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=missing_import_provenance")
if "api.codestra.co {" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=missing_api_site")
if "{$CADDY_KONG_UPSTREAM}" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=kong_handoff_missing")
if "header_up Host {host}" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=kong_host_preservation_missing")
if "Authorization delete" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=authorization_log_redaction_missing")
if "header_up Authorization" in SITE or "header_up -Authorization" in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=authorization_forwarding_modified")

# Caddy is an edge transport boundary, not an application identity authority.
for forbidden_header in (
    "X-Authenticated-Client",
    "X-Authenticated-Tenant",
    "X-Authenticated-Role",
    "X-Codestra-Gateway-Secret",
):
    if forbidden_header in SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=trusted_identity_header_in_caddy:{forbidden_header}")

# The shared API host must never route Kong-managed paths directly to the
# Middleware integration listener. Transitional listeners are separately named.
for forbidden_target in (
    "codestra-middleware-integration-api-1",
    ":8095",
    "http://middleware",
    "https://middleware",
):
    if forbidden_target in SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=direct_middleware_target:{forbidden_target}")

managed_paths = CONTRACT.get("kongManagedPathPrefixes")
if not isinstance(managed_paths, list) or not managed_paths:
    raise SystemExit("CADDY_AUTHORITY_ERROR=missing_kong_managed_paths")
for path_prefix in managed_paths:
    if not isinstance(path_prefix, str) or not path_prefix.startswith("/"):
        raise SystemExit("CADDY_AUTHORITY_ERROR=invalid_kong_path")
    if path_prefix not in SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=kong_path_not_routed:{path_prefix}")

for env_name in (
    "CADDY_KONG_UPSTREAM",
    "CADDY_LEGACY_API_UPSTREAM",
    "CADDY_REALTIME_UPSTREAM",
    "CADDY_GRAFANA_UPSTREAM",
    "CADDY_SUPERSET_UPSTREAM",
    "CADDY_OPENBAO_UPSTREAM",
    "CADDY_OPENBAO_ALLOWED_NETWORKS",
):
    if env_name not in RUNTIME:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=runtime_variable_missing:{env_name}")

if "admin 127.0.0.1:2019" not in CADDYFILE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=admin_api_not_private")
if "import snippets/*.caddy" not in CADDYFILE or "import sites/*.caddy" not in CADDYFILE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=canonical_imports_missing")

browser_hosts = {
    "graf.codestra.media": "CADDY_GRAFANA_UPSTREAM",
    "supe.codestra.media": "CADDY_SUPERSET_UPSTREAM",
    "bao.codestra.media": "CADDY_OPENBAO_UPSTREAM",
}
for host, upstream in browser_hosts.items():
    if f"{host} {{" not in OBSERVABILITY_SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_observability_host:{host}")
    if "{" + "$" + upstream + "}" not in OBSERVABILITY_SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_observability_upstream:{upstream}")

if "CADDY_OPENBAO_ALLOWED_NETWORKS" not in OBSERVABILITY_SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=openbao_network_gate_missing")
if 'respond "Forbidden" 403' not in OBSERVABILITY_SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=openbao_default_deny_missing")
for secret_header in ("Authorization", "Cookie", "X-Vault-Token", "X-Bao-Token"):
    if f"request>headers>{secret_header} delete" not in OBSERVABILITY_SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=observability_log_redaction:{secret_header}")

private_hosts = (
    "prom.codestra.media",
    "aler.codestra.media",
    "loki.codestra.media",
    "temp.codestra.media",
    "otel.codestra.media",
    "node.codestra.media",
    "cadv.codestra.media",
    "pgex.codestra.media",
    "rdex.codestra.media",
    "blac.codestra.media",
    "allo.codestra.media",
)
for host in private_hosts:
    if host not in OBSERVABILITY_DENY:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=private_host_denial_missing:{host}")
deny_source_without_comments = re.sub(r"(?m)^\s*#.*$", "", OBSERVABILITY_DENY)
if re.search(r"(?m)^\s*reverse_proxy\b", deny_source_without_comments):
    raise SystemExit("CADDY_AUTHORITY_ERROR=private_host_reverse_proxy_forbidden")
if 'respond "Not Found" 404' not in OBSERVABILITY_DENY:
    raise SystemExit("CADDY_AUTHORITY_ERROR=private_host_controlled_denial_missing")
for forbidden_port in (":9090", ":9093", ":3100", ":3200", ":4317", ":4318", ":9100", ":8080", ":9187", ":9121", ":9115", ":12345"):
    if forbidden_port in OBSERVABILITY_DENY:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=private_native_port_routed:{forbidden_port}")

secret_patterns = (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)client_secret\s*[=:]\s*[^<\s][^\s]*",
    r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~-]+",
)
for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pattern in secret_patterns:
        if re.search(pattern, text):
            raise SystemExit(f"CADDY_AUTHORITY_ERROR=possible_secret:{path.relative_to(ROOT)}")

print("CADDY_REPOSITORY_AUTHORITY=PASS")
print("CADDY_PRINCIPAL=appolon1908-hue/Caddy")
print("CADDY_TO_KONG_CONTRACT=PASS")
print("KONG_PRINCIPAL=appolon1908-hue/Kong")
print("PRODUCTION_PLATFORM=REFERENCE_ONLY")
print("DIRECT_MIDDLEWARE_FOR_KONG_PATHS=DENIED")
print("LIVE_RELOAD_AUTHORIZED=NO")
print("OBSERVABILITY_BROWSER_HOSTS=graf.codestra.media,supe.codestra.media,bao.codestra.media")
print("OBSERVABILITY_PRIVATE_HOSTS=DENY_ONLY")
print("OPENBAO_EDGE_POLICY=ALLOWLIST_AND_NATIVE_AUTH_REQUIRED")
