#!/usr/bin/env python3
"""Validate pinned Keycloak -> Caddy -> Kong -> Middleware source authority."""

from __future__ import annotations

import json
import re
from pathlib import Path

from caddy_kong_contract import routed_kong_prefixes

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/caddy-kong-middleware-route-evidence.v1.json"
CONTRACT = ROOT / "config/caddy-kong-contract.v2.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_AUTHORITIES = {
    "keycloak": {
        "repository": "appolon1908-hue/Keycloak",
        "sha": "3b8422da498a47b8f1a91a6a2b2c62d2852ca50f",
        "files": {
            "config/clients/n8n-automation.json":
                "7784eb9cd5fc11e5e66d3fbe30418e0bfe16d5d7",
        },
    },
    "kong": {
        "repository": "appolon1908-hue/Kong",
        "sha": "f61c106ce736bf8fd6a013d4961eeca3bf125b56",
        "files": {
            "config/kong-intake-routes.json":
                "8d92e7a40dee5eefe279a3bd668fb7d3428972fc",
            "config/kong-n8n-control-plane-routes.json":
                "6d1649f2a3d95dfbb6eb862e0dd462dc0bfd4ad1",
        },
    },
    "middleware": {
        "repository": "appolon1908-hue/Middleware-",
        "sha": "4092b3b1e57819da75eb45631176b022f70a0c55",
        "files": {
            "app/main.py": "4cff19c6f30f67481b74f67bf15da83e62455c8e",
            "app/survey_routes.py": "4d4faa2a1acab26d1e4b4417f8381c0a9b52a27a",
            "app/n8n_control_plane.py": "87fc20c075a973e5a775d0d343c025054e0231be",
            "app/commands.py": "751d2e51b335520c0509f3758058967a2c767fef",
        },
    },
}
EXPECTED_ROUTES = {
    ("POST", "/v1/intake/leads"),
    ("POST", "/v1/intake/surveys/responses"),
    ("POST", "/v1/integrations/n8n/commands"),
    ("GET", "/v1/integrations/n8n/operations/{command_id}"),
}
EXPECTED_BLOCKED = {
    "/api/v1/control/callbacks",
    "/api/v1/callbacks",
    "/api/v1/automation/policy-check",
    "/api/v1/integrations/n8n/results",
}
PROBE_PATH = "/v1/integrations/n8n/operations/00000000-0000-0000-0000-000000000000"


def fail(reason: str) -> None:
    raise SystemExit(f"CADDY_CROSS_REPOSITORY_CONTRACT_ERROR={reason}")


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid_json:{path.relative_to(ROOT)}:{exc.__class__.__name__}")
    if not isinstance(value, dict):
        fail(f"object_required:{path.relative_to(ROOT)}")
    return value


def files(section: dict, scope: str) -> dict[str, str]:
    items = section.get("evidenceFiles")
    if not isinstance(items, list) or not items:
        fail(f"evidence_files_required:{scope}")
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            fail(f"invalid_evidence_file:{scope}")
        path = item.get("path")
        sha = item.get("blobSha")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in Path(path).parts
            or not isinstance(sha, str)
            or not SHA_RE.fullmatch(sha)
            or path in result
        ):
            fail(f"invalid_evidence_file:{scope}")
        result[path] = sha
    return result


def covers(prefix: str, path: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def main() -> int:
    evidence = load(EVIDENCE)
    contract = load(CONTRACT)
    if evidence.get("schema") != "codestra.caddy-kong-middleware-source-evidence.v1":
        fail("evidence_schema")
    if contract.get("schema") != "codestra.caddy-kong-edge.v2":
        fail("contract_schema")

    caddy = evidence.get("caddy")
    if not isinstance(caddy, dict):
        fail("caddy_authority")
    if (
        caddy.get("repository") != "appolon1908-hue/Caddy"
        or caddy.get("canonicalHost") != contract.get("canonicalHost")
    ):
        fail("caddy_authority")

    for name, expected in EXPECTED_AUTHORITIES.items():
        section = evidence.get(name)
        if not isinstance(section, dict):
            fail(f"missing_authority:{name}")
        sha = section.get("protectedMainSha")
        if (
            section.get("repository") != expected["repository"]
            or sha != expected["sha"]
            or not isinstance(sha, str)
            or not SHA_RE.fullmatch(sha)
            or files(section, name) != expected["files"]
        ):
            fail(f"authority_drift:{name}")

    keycloak = evidence["keycloak"]
    tenant = keycloak.get("tenantClaim")
    if (
        keycloak.get("stagingHost") != "auth-staging.codestra.co"
        or keycloak.get("stagingIssuer") != "https://auth-staging.codestra.co/realms/codestra"
        or keycloak.get("clientId") != "n8n-automation"
        or keycloak.get("audience") != "middleware-api"
        or keycloak.get("maximumAccessTokenLifetimeSeconds") != 300
        or set(keycloak.get("requiredScopes") or [])
        != {
            "middleware.request.forward",
            "middleware.status.read",
            "workflow.result.publish",
        }
        or not isinstance(tenant, dict)
        or tenant != {
            "claim": "tenant_id",
            "source": "service-account-user-attribute",
            "wildcardAllowed": False,
        }
    ):
        fail("keycloak_identity_contract")

    managed = contract.get("kongManagedPathPrefixes")
    if (
        not isinstance(managed, list)
        or not managed
        or not all(isinstance(item, str) and item.startswith("/") for item in managed)
        or len(managed) != len(set(managed))
        or "/api/v1/control" in managed
    ):
        fail("managed_prefixes")
    managed_set = set(managed)

    canonical = ROOT / str(caddy.get("canonicalSitePath", ""))
    legacy = ROOT / str(caddy.get("legacySitePath", ""))
    if not canonical.is_file() or not legacy.is_file():
        fail("site_source_missing")
    if set(routed_kong_prefixes(canonical.read_text(encoding="utf-8"))) != managed_set:
        fail("canonical_site_contract_drift")
    if set(routed_kong_prefixes(legacy.read_text(encoding="utf-8"))) != managed_set:
        fail("legacy_site_contract_drift")
    staging = ROOT / "config/sites/staging-internal.caddy"
    if not staging.is_file() or "auth-staging.codestra.co" not in staging.read_text(encoding="utf-8"):
        fail("staging_identity_edge_missing")

    kong_files = set(EXPECTED_AUTHORITIES["kong"]["files"])
    middleware_files = set(EXPECTED_AUTHORITIES["middleware"]["files"])
    routes = evidence.get("sourceVerifiedRoutes")
    if not isinstance(routes, list):
        fail("source_routes")
    actual: set[tuple[str, str]] = set()
    for route in routes:
        if not isinstance(route, dict):
            fail("source_route_type")
        method = route.get("method")
        path = route.get("path")
        prefix = route.get("caddyPrefix")
        if (
            not isinstance(method, str)
            or not isinstance(path, str)
            or not isinstance(prefix, str)
            or method not in {"GET", "POST"}
            or prefix not in managed_set
            or not covers(prefix, path.replace("/{command_id}", ""))
            or route.get("kongEvidencePath") not in kong_files
            or route.get("middlewareEvidencePath") not in middleware_files
            or (route.get("runtimeProbeAuthorized") is True and method != "GET")
        ):
            fail("source_route_contract")
        actual.add((method, path))
    if actual != EXPECTED_ROUTES:
        fail("source_route_set")

    blocked = set(evidence.get("blockedUntilImplemented") or [])
    contract_blocked = {
        item.get("pathPrefix")
        for item in contract.get("blockedUntilImplemented") or []
        if isinstance(item, dict)
    }
    if blocked != EXPECTED_BLOCKED or contract_blocked != EXPECTED_BLOCKED:
        fail("blocked_route_set")
    for path in blocked:
        if any(covers(prefix, path) for prefix in managed_set):
            fail(f"blocked_route_exposed:{path}")

    proof = evidence.get("runtimeProofContract")
    if (
        not isinstance(proof, dict)
        or proof.get("required") is not True
        or proof.get("identityEnvironment") != "staging"
        or proof.get("expectedIssuer") != keycloak.get("stagingIssuer")
        or proof.get("method") != "GET"
        or proof.get("path") != PROBE_PATH
        or proof.get("expectedAuthenticatedStatus") != 404
        or proof.get("expectedErrorCode") != "command_not_found"
        or proof.get("expectedMiddlewareSourceSha")
        != EXPECTED_AUTHORITIES["middleware"]["sha"]
        or proof.get("mutationAllowed") is not False
        or proof.get("externalEffectsAllowed") is not False
        or proof.get("productionTrafficActivationAuthorized") is not False
        or not any(covers(prefix, PROBE_PATH) for prefix in managed_set)
    ):
        fail("runtime_proof_contract")

    for name, expected in EXPECTED_AUTHORITIES.items():
        print(f"{name.upper()}_PROTECTED_MAIN_SHA={expected['sha']}")
    print(f"SOURCE_VERIFIED_ROUTE_COUNT={len(actual)}")
    print(f"BLOCKED_UNIMPLEMENTED_ROUTE_COUNT={len(blocked)}")
    print("STAGING_IDENTITY_CONTRACT=PASS")
    print("CADDY_KONG_MIDDLEWARE_SOURCE_CONTRACT=PASS")
    print("UNIMPLEMENTED_ROUTES_FAIL_CLOSED=PASS")
    print("RUNTIME_PROOF_REMAINS_REQUIRED=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
