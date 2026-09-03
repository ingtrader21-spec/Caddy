#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from caddy_kong_contract import validate_exact_kong_routes

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
SITE_PATH = ROOT / "sites" / "api.codestra.co.caddy"
N8N_SITE_PATH = ROOT / "sites" / "n8n-editor.community.caddy"
ROOT_CADDYFILE = ROOT / "Caddyfile"
SECURITY_HEADERS = ROOT / "snippets" / "security_headers.caddy"
CONTRACT_PATH = ROOT / "config" / "caddy-kong-contract.v1.json"
N8N_CONTRACT_PATH = ROOT / "config" / "n8n-editor-community.v1.json"
RUNTIME_EXAMPLE = ROOT / "config" / "runtime-values.example"
INTEGRATION_DOC = ROOT / "docs" / "CADDY_KONG_INTEGRATION.md"
N8N_DOC = ROOT / "docs" / "N8N_COMMUNITY_EDITOR_PROTECTION.md"
READONLY_VALIDATOR = ROOT / "scripts" / "caddy_readonly_validator.py"
READONLY_DOC = ROOT / "docs" / "READONLY_PRODUCTION_VALIDATION.md"

for path in (
    README_PATH,
    SITE_PATH,
    N8N_SITE_PATH,
    ROOT_CADDYFILE,
    SECURITY_HEADERS,
    CONTRACT_PATH,
    N8N_CONTRACT_PATH,
    RUNTIME_EXAMPLE,
    INTEGRATION_DOC,
    N8N_DOC,
    READONLY_VALIDATOR,
    READONLY_DOC,
):
    if not path.exists():
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_required_file:{path.relative_to(ROOT)}")

README = README_PATH.read_text(encoding="utf-8")
SITE = SITE_PATH.read_text(encoding="utf-8")
N8N_SITE = N8N_SITE_PATH.read_text(encoding="utf-8")
CADDYFILE = ROOT_CADDYFILE.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
N8N_CONTRACT = json.loads(N8N_CONTRACT_PATH.read_text(encoding="utf-8"))
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

for forbidden_header in (
    "X-Authenticated-Client",
    "X-Authenticated-Tenant",
    "X-Authenticated-Role",
    "X-Codestra-Gateway-Secret",
):
    if forbidden_header in SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=trusted_identity_header_in_caddy:{forbidden_header}")

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
try:
    validate_exact_kong_routes(SITE, managed_paths)
except ValueError as exc:
    raise SystemExit(f"CADDY_AUTHORITY_ERROR={exc}") from exc

# n8n Community editor boundary. Caddy terminates TLS but oauth2-proxy owns
# Keycloak OIDC; the editor is never routed directly to n8n.
if N8N_CONTRACT.get("schema_version") != "1.0":
    raise SystemExit("CADDY_AUTHORITY_ERROR=unsupported_n8n_editor_contract")
if N8N_CONTRACT.get("contract_id") != "codestra.n8n-community-editor-edge":
    raise SystemExit("CADDY_AUTHORITY_ERROR=wrong_n8n_editor_contract")
expected_n8n_contract = {
    "status": "PREPARED_NOT_APPLIED",
    "principal_repository": "appolon1908-hue/Caddy",
    "runtime_repository": "appolon1908-hue/N8N",
    "identity_repository": "appolon1908-hue/Keycloak",
    "identity_provider": "Keycloak",
    "authentication_gateway": "oauth2-proxy",
    "issuer": "https://auth.codestra.co/realms/codestra",
    "authorization_code_flow": True,
    "pkce_method": "S256",
    "native_n8n_owner_login_required": True,
    "enterprise_n8n_sso_required": False,
    "direct_n8n_public_exposure": False,
    "spoofable_identity_headers_stripped": True,
    "secrets_in_repository": False,
    "deployment_authorized": False,
}
for key, expected in expected_n8n_contract.items():
    if N8N_CONTRACT.get(key) != expected:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=n8n_editor_contract:{key}")
if set(N8N_CONTRACT.get("required_any_roles") or []) != {"n8n_operator", "n8n_admin"}:
    raise SystemExit("CADDY_AUTHORITY_ERROR=n8n_editor_roles")
if N8N_CONTRACT.get("edge_chain") != ["Caddy", "oauth2-proxy", "n8n"]:
    raise SystemExit("CADDY_AUTHORITY_ERROR=n8n_editor_chain")

for token in (
    "{$CADDY_N8N_EDITOR_HOST}",
    "{$CADDY_N8N_OAUTH2_PROXY_UPSTREAM}",
    "max_size {$CADDY_N8N_EDITOR_MAX_REQUEST_BODY}",
    "reverse_proxy {$CADDY_N8N_OAUTH2_PROXY_UPSTREAM}",
    "request_header -X-Auth-Request-User",
    "request_header -X-Auth-Request-Email",
    "request_header -X-Auth-Request-Groups",
    "request>headers>Authorization delete",
    "request>headers>Cookie delete",
    "delete code",
    "delete state",
    "delete session_state",
):
    if token not in N8N_SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=n8n_editor_site_missing:{token}")
for forbidden in (
    "CADDY_N8N_UPSTREAM",
    "N8N_EDITOR_UPSTREAM",
    ":5678",
    "max_size 2MB",
    "max_size 2MiB",
    "header_up X-Auth-Request-User",
    "header_up X-Forwarded-User",
):
    if forbidden in N8N_SITE:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=n8n_editor_direct_or_spoofable:{forbidden}")

for env_name in (
    "CADDY_KONG_UPSTREAM",
    "CADDY_LEGACY_API_UPSTREAM",
    "CADDY_REALTIME_UPSTREAM",
    "CADDY_N8N_EDITOR_HOST",
    "CADDY_N8N_OAUTH2_PROXY_UPSTREAM",
    "CADDY_N8N_EDITOR_MAX_REQUEST_BODY",
):
    if env_name not in RUNTIME:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=runtime_variable_missing:{env_name}")
if "CADDY_N8N_EDITOR_MAX_REQUEST_BODY=16777216" not in RUNTIME:
    raise SystemExit("CADDY_AUTHORITY_ERROR=n8n_editor_body_limit_example_drift")

if "admin 127.0.0.1:2019" not in CADDYFILE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=admin_api_not_private")
if "import snippets/*.caddy" not in CADDYFILE or "import sites/*.caddy" not in CADDYFILE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=canonical_imports_missing")

# Every public site block must import the shared header snippet. HSTS and the
# other shared response headers are defined once in snippets/security_headers.caddy,
# so a site that forgets the import silently ships without them.
SITES_DIR = ROOT / "sites"
SITE_ADDRESS = re.compile(r"(?m)^\S.*\{\s*$")
for site_path in sorted(SITES_DIR.glob("*.caddy")):
    source = site_path.read_text(encoding="utf-8")
    blocks = len(SITE_ADDRESS.findall(source))
    imports = source.count("import security_headers")
    if blocks == 0:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=no_site_block:{site_path.name}")
    if imports != blocks:
        raise SystemExit(
            f"CADDY_AUTHORITY_ERROR=security_headers_not_imported:{site_path.name}:{imports}/{blocks}"
        )

SHARED_HEADERS = SECURITY_HEADERS.read_text(encoding="utf-8")
SHARED_HEADER_DIRECTIVES = "\n".join(
    line for line in SHARED_HEADERS.splitlines() if not line.lstrip().startswith("#")
)
for token in (
    'Strict-Transport-Security "max-age=31536000; includeSubDomains"',
    'X-Content-Type-Options "nosniff"',
    'X-Frame-Options "DENY"',
    "Referrer-Policy",
    "Permissions-Policy",
):
    if token not in SHARED_HEADER_DIRECTIVES:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=shared_security_header_missing:{token}")
if "preload" in SHARED_HEADER_DIRECTIVES:
    raise SystemExit("CADDY_AUTHORITY_ERROR=hsts_preload_requires_separate_review")

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
print("KONG_ROUTE_CONTRACT_BIDIRECTIONAL=PASS")
print("KONG_PRINCIPAL=appolon1908-hue/Kong")
print("N8N_COMMUNITY_EDITOR_EDGE=PREPARED_NOT_APPLIED")
print("N8N_DIRECT_PUBLIC_UPSTREAM=DENIED")
print("N8N_EDITOR_BODY_LIMIT=RUNTIME_ALIGNED")
print("KEYCLOAK_OIDC_GATE=OAUTH2_PROXY")
print("PRODUCTION_PLATFORM=REFERENCE_ONLY")
print("DIRECT_MIDDLEWARE_FOR_KONG_PATHS=DENIED")
print("LIVE_RELOAD_AUTHORIZED=NO")
print("CADDY_READONLY_VALIDATOR=SOURCE_ONLY")
print("SHARED_SECURITY_HEADERS=ALL_SITES")
print("HSTS_SCOPE=EVERY_PUBLIC_SITE")
