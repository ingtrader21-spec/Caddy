#!/usr/bin/env python3
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
site = (root / "sites/n8n-editor.community.caddy").read_text()
compose = (root / "deploy/community-n8n/compose.security.yaml").read_text()
squid = (root / "deploy/community-n8n/squid.conf").read_text()
credentials = json.loads((root / "config/community-n8n-credentials.v1.json").read_text())

for required in (
    "{$CADDY_N8N_EDITOR_HOST}",
    "reverse_proxy {$CADDY_N8N_OAUTH2_PROXY_UPSTREAM}",
    "request_header -Authorization",
    "/webhook-test*",
    "/rest/owner/setup*",
):
    assert required in site, required
for forbidden in ("client" + "_secret=", "cookie" + "_secret=", "header_up Authorization"):
    assert forbidden not in site + compose, forbidden
for service in ("n8n:", "n8n-webhook:", "n8n-worker:"):
    assert service in compose, service
for required in ("NODES_EXCLUDE", "n8n-nodes-base.executeCommand", "n8n-nodes-base.ssh", "internal: true"):
    assert required in compose, required
assert "api.codestra.co auth.codestra.co" in squid
assert "http_access deny all" in squid
for required in (
    "--email-domain=*",
    "--allowed-role=n8n_operator",
    "--allowed-role=n8n_admin",
    "--upstream=http://n8n:5678",
    "--redirect-url=https://${EDITOR_HOST:?editor hostname required}/oauth2/callback",
    "--skip-auth-route=^/(webhook|webhook-waiting|form)/",
    "--pass-access-token=false",
    "--pass-basic-auth=false",
    "--custom-templates-dir=/etc/oauth2-proxy/templates",
    "--skip-provider-button=false",
    "--show-debug-on-error=false",
    "--cookie-secure=true",
    "--cookie-httponly=true",
    "--cookie-samesite=lax",
    "create_host_path: false",
    "N8N_LOGIN_TEMPLATE_DIR",
):
    assert required in compose, required
assert credentials["runtime_identity"]["owner"] == "n8n-service-owner"
assert credentials["runtime_identity"]["client_id"] == "n8n-automation"
assert credentials["runtime_identity"]["rotation_days"] <= 90
assert credentials["editor_gateway_identity"]["secret_source"] == "root-owned-docker-secret-files"
assert credentials["editor_gateway_identity"]["rotation_days"] <= 90
assert credentials["secret_values_in_repository"] is False
print("COMMUNITY_N8N_SECURITY=PASS")
