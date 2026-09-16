#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import caddy_kong_contract
from caddy_kong_contract import (
    resolve_request,
    validate_exact_kong_routes,
    validate_service_jwt_routes,
)

ROOT = Path(__file__).resolve().parents[1]
VENDORED_CONTRACT = ROOT / "config" / "middleware-public-api-route-contract.v1.json"
VENDORED = json.loads(VENDORED_CONTRACT.read_text(encoding="utf-8"))
CANONICAL_ROUTES = tuple(
    (row["method"], row["path"], row["scope"])
    for row in VENDORED["routes"]
    if row["classification"] == "shared_edge"
)


class CaddyKongContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = (ROOT / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")
        contract = json.loads(
            (ROOT / "config" / "caddy-kong-contract.v1.json").read_text(encoding="utf-8")
        )
        self.managed_paths = contract["kongManagedPathPrefixes"]
        self.service_jwt = contract["serviceJwtRouteContract"]

    def test_caddy_and_kong_route_contract_is_bidirectional(self) -> None:
        validate_exact_kong_routes(self.site, self.managed_paths)

    def test_uncontracted_caddy_route_is_rejected(self) -> None:
        modified = self.site.replace("/v1/intake*", "/v1/intake* /v1/unmanaged*")
        with self.assertRaisesRegex(ValueError, "kong_route_not_contracted:/v1/unmanaged"):
            validate_exact_kong_routes(modified, self.managed_paths)

    def test_unrouted_contract_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "kong_contract_not_routed:/v1/declared-only"):
            validate_exact_kong_routes(self.site, [*self.managed_paths, "/v1/declared-only"])

    def test_service_jwt_contract_matches_the_canonical_route_table(self) -> None:
        declared = {(r["method"], r["path"], r["scope"]) for r in self.service_jwt["routes"]}
        self.assertEqual(declared, set(CANONICAL_ROUTES))
        self.assertRegex(self.service_jwt["sha256"], r"^[0-9a-f]{64}$")
        validate_service_jwt_routes(self.site, self.service_jwt)

    def test_every_canonical_route_reaches_kong_through_a_method_matcher(self) -> None:
        for method, template, _scope in CANONICAL_ROUTES:
            path = caddy_kong_contract.concrete_path(template)
            upstream, matcher, declares_method = resolve_request(self.site, method, path)
            self.assertEqual(upstream, "CADDY_KONG_UPSTREAM", (method, path))
            self.assertEqual(matcher, f"canonical_{method.lower()}", (method, path, matcher))
            self.assertTrue(declares_method, (method, path))

    def test_method_matchers_do_not_accept_noncanonical_longer_paths(self) -> None:
        probes = (
            "/api/v1/integrations/n8n/results/EVT-1/extra",
            "/api/v1/integrations/odoo/campaigns/TEST_SYN/extra",
            "/api/v1/integrations/odoo/campaigns/TEST_SYN/desired-state/extra",
        )
        for path in probes:
            upstream, matcher, declares_method = resolve_request(self.site, "GET", path)
            self.assertEqual(upstream, "CADDY_KONG_UPSTREAM", path)
            self.assertEqual(matcher, "kong", path)
            self.assertFalse(declares_method, path)

    def test_contract_hash_is_canonical_digest_of_vendored_source(self) -> None:
        self.assertTrue(VENDORED_CONTRACT.exists(), "vendored Middleware route contract is missing")
        vendored = json.loads(VENDORED_CONTRACT.read_text(encoding="utf-8"))
        digest = hashlib.sha256(
            json.dumps(vendored, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, self.service_jwt["sha256"])
        scoped = {
            (row["method"], row["path"], row["scope"])
            for row in vendored["routes"]
            if row["classification"] == "shared_edge"
        }
        self.assertEqual(scoped, set(CANONICAL_ROUTES))

    def test_contract_hash_validator_rejects_vendored_source_drift(self) -> None:
        validator = getattr(caddy_kong_contract, "validate_contract_hash", None)
        self.assertIsNotNone(validator, "contract hash validator is missing")
        with self.assertRaisesRegex(ValueError, "service_jwt_contract_hash_mismatch"):
            validator(self.service_jwt["sha256"], {"schema": "tampered"})

    def test_unsupported_methods_and_retired_paths_never_reach_legacy(self) -> None:
        probes = [
            ("DELETE", "/api/v1/integrations/odoo/campaigns/TEST_SYN"),
            ("POST", "/api/v1/integrations/odoo/campaigns/TEST_SYN/desired-state"),
            ("PUT", "/api/v1/integrations/n8n/results/EVT-1"),
            ("GET", "/api/v1/integrations/n8n/results"),
            ("POST", "/api/v1/integrations/odoo/campaign-actions"),
            ("POST", "/api/v1/integrations/odoo/campaign-commands"),
            ("GET", "/api/v1/integrations/odoo/campaign-commands/x"),
            ("POST", "/api/v1/integration/campaign-actions"),
            ("POST", "/api/v1/odoo/campaign-actions"),
        ]
        for method, path in probes:
            upstream, matcher, _declares = resolve_request(self.site, method, path)
            self.assertEqual(upstream, "CADDY_KONG_UPSTREAM", (method, path, matcher))
            self.assertNotIn(matcher, (None, "realtime"), (method, path))

    def test_legacy_fallback_still_serves_unrelated_paths_last(self) -> None:
        upstream, matcher, _declares = resolve_request(self.site, "GET", "/api/v2/anything")
        self.assertEqual((upstream, matcher), ("CADDY_LEGACY_API_UPSTREAM", None))

    def test_path_only_integration_matcher_is_rejected(self) -> None:
        modified = self.site.replace("\t\t\tmethod GET\n", "", 1)
        with self.assertRaisesRegex(
            ValueError, "service_jwt_matcher_without_method:GET"
        ):
            validate_service_jwt_routes(modified, self.service_jwt)

    def test_integration_route_falling_to_legacy_is_rejected(self) -> None:
        modified = self.site.replace(
            "|/api/v1/integrations/odoo/campaigns/[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
            "",
            1,
        ).replace(" /api/v1/integrations/odoo/campaigns*", "")
        with self.assertRaisesRegex(
            ValueError, "service_jwt_route_not_kong:GET /api/v1/integrations/odoo/campaigns/{campaign_id}"
        ):
            validate_service_jwt_routes(modified, self.service_jwt)

    def test_unsupported_method_falling_to_legacy_is_rejected(self) -> None:
        modified = self.site.replace(" /api/v1/integrations/odoo/campaigns*", "")
        with self.assertRaisesRegex(
            ValueError, "unsupported_method_reaches_legacy:(POST|DELETE) /api/v1/integrations/odoo/campaigns/{campaign_id}"
        ):
            validate_service_jwt_routes(modified, self.service_jwt)

    def test_retired_path_falling_to_legacy_is_rejected(self) -> None:
        modified = self.site.replace(" /api/v1/odoo/campaign-actions*", "")
        with self.assertRaisesRegex(ValueError, "retired_path_reaches_legacy:GET /api/v1/odoo/campaign-actions"):
            validate_service_jwt_routes(modified, self.service_jwt)

    def test_missing_contract_hash_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "service_jwt_contract_hash_missing"):
            validate_service_jwt_routes(self.site, {**self.service_jwt, "sha256": "pending"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
