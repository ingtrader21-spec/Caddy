#!/usr/bin/env python3
from __future__ import annotations
import json, unittest
from pathlib import Path
from caddy_kong_contract import validate_exact_kong_routes
ROOT=Path(__file__).resolve().parents[1]
class CaddyKongContractTests(unittest.TestCase):
    def setUp(self):
        self.site=(ROOT/'config/sites/api.codestra.co.caddy').read_text(); self.legacy=(ROOT/'config/sites/legacy-api.codestra.agency.caddy').read_text(); self.managed=json.loads((ROOT/'config/caddy-kong-contract.v2.json').read_text())['kongManagedPathPrefixes']
    def test_canonical_and_legacy_hosts_share_the_exact_kong_contract(self):
        validate_exact_kong_routes(self.site,self.managed); validate_exact_kong_routes(self.legacy,self.managed)
    def test_uncontracted_caddy_route_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'kong_route_not_contracted:/v1/unmanaged'): validate_exact_kong_routes(self.site.replace('/v1/intake*','/v1/intake* /v1/unmanaged*'),self.managed)
    def test_unrouted_contract_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'kong_contract_not_routed:/v1/declared-only'): validate_exact_kong_routes(self.site,[*self.managed,'/v1/declared-only'])
if __name__=='__main__': unittest.main(verbosity=2)
