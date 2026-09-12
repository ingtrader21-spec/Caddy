#!/usr/bin/env python3
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
contract = json.loads((root / "config/kyyow-ingress.v1.json").read_text())
site = (root / "sites/kyyow.com.caddy").read_text()
runtime = (root / "config/runtime-values.example").read_text()

assert contract["schema"] == "kyyow.ingress.v1"
assert contract["principalRepository"] == "appolon1908-hue/Caddy"
assert contract["identityRepository"] == "appolon1908-hue/Keycloak"
assert contract["activation"] == {
    "repositoryConfigurationOnly": True,
    "dnsChangeAuthorized": False,
    "liveReloadAuthorized": False,
    "productionCutoverAuthorized": False,
}
for host, route in contract["publicHosts"].items():
    assert len(re.findall(rf"(?m)^{re.escape(host)}\s*\{{", site)) == 1
    assert f"{{$" + route["upstream"] + "}" in site
    assert runtime.count(route["upstream"] + "=127.0.0.1:") == 1
for token in ("import security_headers", "request>headers>Authorization delete"):
    assert site.count(token) >= len(contract["publicHosts"])
for forbidden in contract["prohibitedPublicServices"]:
    assert not re.search(rf"(?m)^{re.escape(forbidden)}(?:\.|:)?.*\{{", site)
assert "header_up Authorization" not in site
assert "header_up X-Authenticated-" not in site
print("KYYOW_INGRESS_CONTRACT=PASS")
