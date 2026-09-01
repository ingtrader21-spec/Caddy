#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from caddy_kong_contract import validate_exact_kong_routes

ROOT = Path(__file__).resolve().parents[1]


class CaddyKongContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = (ROOT / "candidate" / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
