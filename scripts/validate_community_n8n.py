#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
site = (root / "config/sites/automation.codestra.co.caddy").read_text()
compose = (root / "deploy/community-n8n/compose.security.yaml").read_text()
squid = (root / "deploy/community-n8n/squid.conf").read_text()
credentials = json.loads((root / "config/community-n8n-credentials.v1.json").read_text())
contract = json.loads((root / "config/n8n-editor-community.v2.json").read_text())

for required in (
    "automation.codestra.co",
    "remote_ip {$CADDY_EDITOR_ADMIN_CIDRS}",
    "reverse_proxy {$CADDY_KONG_UPSTREAM}",
    "/webhook-test*",
    "/rest/owner/setup*",
    "request_header -X-Auth-Request-User",
    "request_header -X-Forwarded-User",
    "import sanitized_access_log",
):
    assert required in site, required
for forbidden in (
    "CADDY_N8N_OAUTH2_PROXY_UPSTREAM", "CADDY_N8N_UPSTREAM", ":5678",
    "request_header -Authorization", "header_up Authorization",
    "client" + "_secret=", "cookie" + "_secret=",
):
    assert forbidden not in site, forbidden
for service in ("n8n:", "n8n-webhook:", "n8n-worker:"):
    assert service in compose, service
for required in (
    "NODES_EXCLUDE", "n8n-nodes-base.executeCommand", "n8n-nodes-base.ssh", "internal: true",
    "--email-domain=*", "--allowed-role=n8n_operator", "--allowed-role=n8n_admin",
    "--upstream=http://n8n:5678", "--pass-access-token=false", "--pass-basic-auth=false",
    "--custom-templates-dir=/etc/oauth2-proxy/templates", "--skip-provider-button=false",
    "--show-debug-on-error=false", "--cookie-secure=true", "--cookie-httponly=true",
    "--cookie-samesite=lax", "create_host_path: false", "N8N_LOGIN_TEMPLATE_DIR",
):
    assert required in compose, required
assert "api.codestra.co auth.codestra.co" in squid
assert "http_access deny all" in squid
assert credentials["runtime_identity"]["owner"] == "n8n-service-owner"
assert credentials["runtime_identity"]["rotation_days"] <= 90
assert credentials["secret_values_in_repository"] is False
assert contract["authentication_gateway"] == "Kong"
assert contract["edge_chain"] == ["Caddy", "Kong", "n8n"]
assert contract["direct_n8n_public_exposure"] is False
assert contract["spoofable_identity_headers_stripped"] is True
print("COMMUNITY_N8N_SECURITY=PASS")
