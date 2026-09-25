from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = (ROOT / "sites/api.codestra.co.caddy").read_text(encoding="utf-8-sig")
CONTRACT = json.loads((ROOT / "config/caddy-kong-contract.v1.json").read_text(encoding="utf-8-sig"))
MCR = [
    "/platform/v1/campaign-engine",
    "/platform/v1/leads",
    "/platform/v1/campaigns",
    "/platform/v1/delivery-events",
    "/platform/v1/suppressions",
]


def test_platform_v1_is_kong_managed_for_all_mcr_paths():
    managed = set(CONTRACT["kongManagedPathPrefixes"])
    assert "/platform/v1" in managed
    assert all(path.startswith("/platform/v1/") for path in MCR)
    assert "/platform/v1*" in SITE


def test_mcr_boundary_is_explicit_and_not_cutover_authority():
    b = CONTRACT["mcrBoundary"]
    assert b["mission"] == "MCR-K"
    assert b["kongOnly"] is True
    assert b["productionCutoverAuthorizedBySource"] is False
    assert b["authorizationHeaderForwarded"] is True
    assert b["trustedIdentityHeadersCreatedByCaddy"] is False
    assert b["publicInternalAndMetricsForbidden"] is True
    assert b["coveredByKongManagedPrefix"] == "/platform/v1"
    assert b["managedPaths"] == MCR


def test_platform_v1_handoff_targets_kong_not_middleware_or_provider():
    start = SITE.index("@kong path")
    end = SITE.index("# Transitional compatibility", start)
    block = SITE[start:end]
    assert "reverse_proxy {$CADDY_KONG_UPSTREAM}" in block
    assert "MIDDLEWARE" not in block.upper()
    assert "KLYROW" not in block.upper()
    assert "TELNEXA" not in block.upper()
    assert "VICIDIAL" not in block.upper()


def test_authorization_is_preserved_to_kong_and_only_redacted_from_logs():
    start = SITE.index("@kong path")
    end = SITE.index("# Transitional compatibility", start)
    block = SITE[start:end]
    assert "header_up Authorization" not in block
    assert "header_up -Authorization" not in block
    assert "request_header -Authorization" not in block
    assert "request>headers>Authorization delete" in SITE


def test_private_internal_and_metrics_stay_edge_denied():
    assert "@private_only path /metrics /metrics/* /internal /internal/*" in SITE
    assert "handle @private_only" in SITE
    assert "respond 404" in SITE
