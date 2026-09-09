from __future__ import annotations

import os
import stat
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "config/sites/staging-internal.caddy"
BOUNDED_CANARY = ROOT / "scripts/bounded-production-readonly-canary-v2.sh"
PKI_PREPARER = ROOT / "scripts/prepare-runtime-pki-permissions.sh"
PRODUCTION_CANARY = ROOT / "scripts/production-canary.sh"


class PR129ReviewRegressionTests(unittest.TestCase):
    def test_runtime_helpers_are_executable(self) -> None:
        for path in (PKI_PREPARER, BOUNDED_CANARY, PRODUCTION_CANARY):
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertTrue(mode & stat.S_IXUSR, f"{path.name} must be executable")

    def test_production_canary_uses_canonical_grafana_hostname(self) -> None:
        source = BOUNDED_CANARY.read_text(encoding="utf-8")
        self.assertIn("graf.codestra.media", source)
        self.assertNotIn("grafana.codestra.media", source)

    def test_staging_shared_api_surfaces_route_through_kong(self) -> None:
        source = STAGING.read_text(encoding="utf-8")
        self.assertEqual(source.count("reverse_proxy {$CADDY_STAGING_KONG_UPSTREAM}"), 2)
        self.assertEqual(source.count("header_up Host api.codestra.co"), 2)
        self.assertNotIn("reverse_proxy {$CADDY_STAGING_API_UPSTREAM}", source)
        self.assertNotIn("reverse_proxy {$CADDY_KONG_UPSTREAM}", source)

    def test_private_vicidial_callback_remains_denied(self) -> None:
        source = STAGING.read_text(encoding="utf-8")
        self.assertIn("@private_callback path /api/v1/events/vicidial", source)
        self.assertIn("respond @private_callback 404", source)


if __name__ == "__main__":
    unittest.main()
