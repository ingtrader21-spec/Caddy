#!/usr/bin/env python3
"""Validate the pinned Caddy -> Kong -> Middleware source and safety contract."""

from __future__ import annotations

import json
import re
from pathlib import Path

from caddy_kong_contract import routed_kong_prefixes

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "config/caddy-kong-middleware-route-evidence.v1.json"
CONTRACT_PATH = ROOT / "config/caddy-kong-contract.v2.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def fail(reason: str) -> None:
    raise SystemExit(f"CADDY_CROSS_REPOSITORY_CONTRACT_ERROR={reason}")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid_json:{path.relative_to(ROOT)}:{exc.__class__.__name__}")
    if not isinstance(value, dict):
        fail(f"object_required:{path.relative_to(ROOT)}")
    return value


def require_sha(value: object, scope: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        fail(f"invalid_sha:{scope}")
    return value


def covers(prefix: str, path: str) -> bool:
    normalized = prefix.rstrip("/")
    return path == normalized or path.startswith(normalized + "/")


def evidence_files(section: dict, scope: str) -> dict[str, str]:
    items = section.get("evidenceFiles")
    if not isinstance(items, list) or not items:
        fail(f"evidence_files_required:{scope}")
    result: dict[str, str] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            fail(f"invalid_evidence_file:{scope}:{index}")
        path = item.get("path")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
            fail(f"invalid_evidence_path:{scope}:{index}")
        if path in result:
            fail(f"duplicate_evidence_path:{scope}:{path}")
        result[path] = require_sha(item.get("blobSha"), f"{scope}:{path}")
    return result


def main() -> int:
    evidence = load_json(EVIDENCE_PATH)
    contract = load_json(CONTRACT_PATH)

    if evidence.get("schema") != "codestra.caddy-kong-middleware-source-evidence.v1":
        fail("evidence_schema")
    if contract.get("schema") != "codestra.caddy-kong-edge.v2":
        fail("caddy_contract_schema")

    caddy = evidence.get("caddy")
    kong = evidence.get("kong")
    middleware = evidence.get("middleware")
    if not all(isinstance(item, dict) for item in (caddy, kong, middleware)):
        fail("authority_objects_required")
    assert isinstance(caddy, dict)
    assert isinstance(kong, dict)
    assert isinstance(middleware, dict)

    if caddy.get("repository") != "appolon1908-hue/Caddy":
        fail("caddy_repository")
    if caddy.get("canonicalHost") != contract.get("canonicalHost"):
        fail("canonical_host")
    if kong.get("repository") != "appolon1908-hue/Kong":
        fail("kong_repository")
    if middleware.get("repository") != "appolon1908-hue/Middleware-":
        fail("middleware_repository")

    kong_sha = require_sha(kong.get("protectedMainSha"), "kong_main")
    middleware_sha = require_sha(middleware.get("protectedMainSha"), "middleware_main")
    if kong_sha != "f61c106ce736bf8fd6a013d4961eeca3bf125b56":
        fail("unexpected_kong_main")
    if middleware_sha != "50175213ca1c6e785dbb7b5ab2b00caf932a516d":
        fail("unexpected_middleware_main")

    kong_files = evidence_files(kong, "kong")
    middleware_files = evidence_files(middleware, "middleware")
    if set(kong_files) != {
        "config/kong-intake-routes.json",
        "config/kong-n8n-control-plane-routes.json",
    }:
        fail("kong_evidence_set")
    if set(middleware_files) != {
        "app/main.py",
        "app/survey_routes.py",
        "app/n8n_control_plane.py",
        "app/commands.py",
    }:
        fail("middleware_evidence_set")

    managed = contract.get("kongManagedPathPrefixes")
    if not isinstance(managed, list) or not managed or not all(isinstance(item, str) for item in managed):
        fail("managed_prefixes")
    managed_prefixes = list(managed)
    if len(managed_prefixes) != len(set(managed_prefixes)):
        fail("duplicate_managed_prefix")
    if "/api/v1/control" in managed_prefixes:
        fail("broad_control_prefix_forbidden")

    canonical_path = ROOT / str(caddy.get("canonicalSitePath", ""))
    legacy_path = ROOT / str(caddy.get("legacySitePath", ""))
    if not canonical_path.is_file() or not legacy_path.is_file():
        fail("site_source_missing")
    canonical_routes = set(routed_kong_prefixes(canonical_path.read_text(encoding="utf-8")))
    legacy_routes = set(routed_kong_prefixes(legacy_path.read_text(encoding="utf-8")))
    if canonical_routes != set(managed_prefixes):
        fail("canonical_site_contract_drift")
    if legacy_routes != set(managed_prefixes):
        fail("legacy_site_contract_drift")

    routes = evidence.get("sourceVerifiedRoutes")
    if not isinstance(routes, list):
        fail("source_routes_required")
    expected_routes = {
        ("POST", "/v1/intake/leads"),
        ("POST", "/v1/intake/surveys/responses"),
        ("POST", "/v1/integrations/n8n/commands"),
        ("GET", "/v1/integrations/n8n/operations/{command_id}"),
    }
    actual_routes: set[tuple[str, str]] = set()
    for index, route in enumerate(routes):
        if not isinstance(route, dict):
            fail(f"invalid_source_route:{index}")
        method = route.get("method")
        path = route.get("path")
        prefix = route.get("caddyPrefix")
        kong_path = route.get("kongEvidencePath")
        middleware_path = route.get("middlewareEvidencePath")
        if not all(isinstance(item, str) and item for item in (method, path, prefix, kong_path, middleware_path)):
            fail(f"invalid_source_route_fields:{index}")
        assert isinstance(method, str)
        assert isinstance(path, str)
        assert isinstance(prefix, str)
        assert isinstance(kong_path, str)
        assert isinstance(middleware_path, str)
        if method not in {"GET", "POST"} or not path.startswith("/"):
            fail(f"invalid_method_or_path:{index}")
        if prefix not in managed_prefixes or not covers(prefix, path.replace("/{command_id}", "")):
            fail(f"unrouted_source_route:{method}:{path}")
        if kong_path not in kong_files or middleware_path not in middleware_files:
            fail(f"missing_pinned_evidence:{method}:{path}")
        if route.get("runtimeProbeAuthorized") is True and method != "GET":
            fail(f"mutation_probe_forbidden:{path}")
        actual_routes.add((method, path))
    if actual_routes != expected_routes:
        fail("source_route_set")

    blocked = evidence.get("blockedUntilImplemented")
    contract_blocked_items = contract.get("blockedUntilImplemented")
    if not isinstance(blocked, list) or not isinstance(contract_blocked_items, list):
        fail("blocked_route_contract_required")
    contract_blocked = {
        item.get("pathPrefix")
        for item in contract_blocked_items
        if isinstance(item, dict) and isinstance(item.get("pathPrefix"), str)
    }
    blocked_set = set(blocked)
    expected_blocked = {
        "/api/v1/control/callbacks",
        "/api/v1/callbacks",
        "/api/v1/automation/policy-check",
        "/api/v1/integrations/n8n/results",
    }
    if blocked_set != expected_blocked or contract_blocked != expected_blocked:
        fail("blocked_route_set")
    for path in blocked_set:
        if any(covers(prefix, path) for prefix in managed_prefixes):
            fail(f"blocked_route_exposed:{path}")

    proof = evidence.get("runtimeProofContract")
    if not isinstance(proof, dict):
        fail("runtime_proof_contract")
    expected_probe_path = "/v1/integrations/n8n/operations/00000000-0000-0000-0000-000000000000"
    if (
        proof.get("required") is not True
        or proof.get("method") != "GET"
        or proof.get("path") != expected_probe_path
        or proof.get("expectedAuthenticatedStatus") != 404
        or proof.get("expectedErrorCode") != "command_not_found"
        or proof.get("expectedMiddlewareSourceSha") != middleware_sha
        or proof.get("mutationAllowed") is not False
        or proof.get("externalEffectsAllowed") is not False
        or proof.get("productionTrafficActivationAuthorized") is not False
    ):
        fail("unsafe_or_incomplete_runtime_proof")
    if not any(covers(prefix, expected_probe_path) for prefix in managed_prefixes):
        fail("runtime_probe_not_routed")

    print(f"KONG_PROTECTED_MAIN_SHA={kong_sha}")
    print(f"MIDDLEWARE_PROTECTED_MAIN_SHA={middleware_sha}")
    print(f"SOURCE_VERIFIED_ROUTE_COUNT={len(actual_routes)}")
    print(f"BLOCKED_UNIMPLEMENTED_ROUTE_COUNT={len(blocked_set)}")
    print("CADDY_KONG_MIDDLEWARE_SOURCE_CONTRACT=PASS")
    print("UNIMPLEMENTED_ROUTES_FAIL_CLOSED=PASS")
    print("RUNTIME_PROOF_REMAINS_REQUIRED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
