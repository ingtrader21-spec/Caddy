#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from caddy_kong_contract import (
    header_up_directives,
    routed_kong_prefixes,
    validate_exact_kong_routes,
    validate_identity_header_boundary,
)

ROOT = Path(__file__).resolve().parents[1]


class CaddyKongContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = (ROOT / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")
        contract = json.loads(
            (ROOT / "config" / "caddy-kong-contract.v1.json").read_text(encoding="utf-8")
        )
        self.managed_paths = contract["kongManagedPathPrefixes"]

    def test_caddy_and_kong_route_contract_is_bidirectional(self) -> None:
        validate_exact_kong_routes(self.site, self.managed_paths)

    def test_uncontracted_caddy_route_is_rejected(self) -> None:
        modified = self.site.replace("/v1/intake*", "/v1/intake* /v1/unmanaged*")
        with self.assertRaisesRegex(ValueError, "kong_route_not_contracted:/v1/unmanaged"):
            validate_exact_kong_routes(modified, self.managed_paths)

    def test_unrouted_contract_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "kong_contract_not_routed:/v1/declared-only"):
            validate_exact_kong_routes(self.site, [*self.managed_paths, "/v1/declared-only"])




class IdentityHeaderBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = (ROOT / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")
        contract = json.loads(
            (ROOT / "config" / "caddy-kong-contract.v1.json").read_text(encoding="utf-8")
        )
        self.deleted = contract["identityHeaders"]["deletedBeforeKong"]
        self.preserved = contract["identityHeaders"]["preservedToKong"]

    def test_site_deletes_every_contracted_identity_header_and_sets_none(self) -> None:
        validate_identity_header_boundary(self.site, self.deleted)
        directives = header_up_directives(self.site)
        self.assertEqual({name for action, name in directives if action == "set"}, {"Host", "X-Real-IP"})
        self.assertTrue(set(self.deleted) <= {name for action, name in directives if action == "delete"})
        self.assertFalse(set(self.preserved) & {name for action, name in directives if action == "delete"})

    def test_setting_a_trusted_identity_header_is_rejected(self) -> None:
        mutated = self.site.replace(
            "header_up X-Real-IP {remote_host}",
            "header_up X-Real-IP {remote_host}\n\t\t\t\theader_up X-Authenticated-Tenant tenant-a",
            1,
        )
        with self.assertRaises(ValueError) as caught:
            validate_identity_header_boundary(mutated, self.deleted)
        self.assertEqual(str(caught.exception), "trusted_identity_header_set_by_caddy:X-Authenticated-Tenant")

    def test_deleting_a_preserved_edge_header_is_rejected(self) -> None:
        mutated = self.site.replace("header_up -X-User-ID", "header_up -Idempotency-Key", 1)
        with self.assertRaises(ValueError) as caught:
            validate_identity_header_boundary(mutated, [h for h in self.deleted if h != "X-User-ID"])
        self.assertEqual(str(caught.exception), "preserved_edge_header_deleted:Idempotency-Key")

    def test_dropping_a_contracted_deletion_is_rejected(self) -> None:
        mutated = self.site.replace("\t\t\t\theader_up -X-Authenticated-Client\n", "", 1)
        with self.assertRaises(ValueError) as caught:
            validate_identity_header_boundary(mutated, self.deleted)
        self.assertEqual(str(caught.exception), "identity_header_not_deleted:X-Authenticated-Client")

    def test_every_kong_owned_contract_path_is_routed_to_kong(self) -> None:
        prefixes = routed_kong_prefixes(self.site)
        for path in (
            "/api/v1/automation/policy-check",
            "/api/v1/callbacks",
            "/api/v1/control/callbacks",
            "/api/v1/integration/campaign-actions",
            "/api/v1/integrations/n8n/results",
            "/api/v1/integrations/n8n/results/evt-1",
            "/api/v1/integrations/odoo/campaigns/c-1/desired-state",
            "/api/v1/integrations/odoo/campaign-commands",
            "/api/v1/odoo/events",
            "/api/v1/odoo/campaign-actions",
            "/platform/v1/agent-provisioning/requests",
            "/platform/v1/commands",
            "/v2/automation/jobs/claim",
            "/v1/integrations/n8n/commands",
        ):
            self.assertTrue(any(path == p or path.startswith(p) for p in prefixes), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
