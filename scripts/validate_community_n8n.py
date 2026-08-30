#!/usr/bin/env python3
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
site = (root / "sites/n8n-editor.caddy").read_text()
compose = (root / "deploy/community-n8n/compose.security.yaml").read_text()
squid = (root / "deploy/community-n8n/squid.conf").read_text()
credentials = json.loads((root / "config/community-n8n-credentials.v1.json").read_text())

for required in ("{$EDITOR_HOST}", "forward_auth", "/automation-editors", "header_up -Authorization"):
    assert required in site, required
for forbidden in ("client" + "_secret=", "cookie" + "_secret=", "header_up Authorization"):
    assert forbidden not in site + compose, forbidden
for service in ("n8n:", "n8n-webhook:", "n8n-worker:"):
    assert service in compose, service
for required in ("NODES_EXCLUDE", "n8n-nodes-base.executeCommand", "n8n-nodes-base.ssh", "internal: true"):
    assert required in compose, required
assert "api.codestra.co auth.codestra.co" in squid
assert "http_access deny all" in squid
assert credentials["runtime_identity"]["owner"] == "n8n-service-owner"
assert credentials["runtime_identity"]["rotation_days"] <= 90
assert credentials["secret_values_in_repository"] is False
print("COMMUNITY_N8N_SECURITY=PASS")
