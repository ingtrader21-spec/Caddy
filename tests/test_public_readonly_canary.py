import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = (ROOT / "config/sites/api.codestra.co.caddy").read_text(encoding="utf-8")


def test_public_canary_is_exactly_bounded_to_reviewed_health_paths():
    contract = json.loads(
        (ROOT / "config/caddy-kong-contract.v2.json").read_text(encoding="utf-8")
    )["publicReadOnlyCanary"]
    assert contract == {
        "host": "api.codestra.co",
        "paths": ["/healthz", "/readyz", "/version"],
        "methods": ["GET", "HEAD"],
        "upstreamAuthority": "websocket-gateway",
        "kongManaged": False,
        "writeMethodsDeniedAtEdge": True,
    }
    assert SITE.count("path /healthz /readyz /version") == 2
    assert "method GET HEAD" in SITE
    assert "not method GET HEAD" in SITE
    assert 'header Allow "GET, HEAD"' in SITE
    assert 'respond "Method Not Allowed" 405' in SITE


def test_public_canary_does_not_include_effect_or_admin_paths():
    canary = SITE[SITE.index("@readonly_canary_denied") : SITE.index("# Only route")]
    for forbidden in (
        "/v1/email",
        "/v1/sms",
        "/v1/webhooks",
        "/v1/integrations/n8n",
        "/api/v1/control",
        "/api/v1/admin",
        "/metrics",
        "/debug",
    ):
        assert forbidden not in canary


def test_existing_kong_and_realtime_surfaces_remain_separate():
    assert "@kong path" in SITE
    assert "@realtime path /ws/agent /api/v1/realtime/sessions" in SITE
    assert "@realtime path /ws/agent /api/v1/realtime/sessions /healthz" not in SITE
