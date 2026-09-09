from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from caddy_readonly_validator import (  # noqa: E402
    CONFIG_CONDITIONAL_ENVIRONMENT,
    REQUIRED_ENVIRONMENT,
    ValidationError,
    config_required_environment,
    validate_environment,
)

STAGING = ROOT / "config/sites/staging-internal.caddy"
BOUNDED_STAGING = ROOT / "scripts/bounded-staging-runtime-v2.sh"
BOUNDED_CANARY = ROOT / "scripts/bounded-production-readonly-canary-v2.sh"
PKI_PREPARER = ROOT / "scripts/prepare-runtime-pki-permissions.sh"
PRODUCTION_CANARY = ROOT / "scripts/production-canary.sh"
STAGING_KONG_ENV = "CADDY_STAGING_KONG_UPSTREAM"


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

    def test_legacy_runtime_does_not_require_new_staging_kong_variable(self) -> None:
        self.assertIn(STAGING_KONG_ENV, CONFIG_CONDITIONAL_ENVIRONMENT)
        self.assertNotIn(STAGING_KONG_ENV, REQUIRED_ENVIRONMENT)
        environment = self.valid_environment()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Caddyfile").write_text("legacy.example { respond /healthz 200 }\n", encoding="utf-8")
            required = config_required_environment(root)
            self.assertNotIn(STAGING_KONG_ENV, required)
            validate_environment(environment, required)

    def test_candidate_config_reference_requires_staging_kong_variable(self) -> None:
        environment = self.valid_environment()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Caddyfile").write_text(
                "candidate.example { reverse_proxy {$CADDY_STAGING_KONG_UPSTREAM} }\n",
                encoding="utf-8",
            )
            required = config_required_environment(root)
            self.assertIn(STAGING_KONG_ENV, required)
            with self.assertRaises(ValidationError):
                validate_environment(environment, required)
            environment[STAGING_KONG_ENV] = "127.0.0.1:18000"
            validate_environment(environment, required)

    def test_bounded_staging_exercises_dedicated_staging_gateway_hosts(self) -> None:
        source = BOUNDED_STAGING.read_text(encoding="utf-8")
        normalization = source.index('127.0.0.1:*) values["$name"]="host.docker.internal:')
        separation = source.index("staging_kong_not_dedicated")
        self.assertGreater(separation, normalization)
        for hostname in ("api.staging.internal.codestra.agency", "bridge-staging.codestra.agency"):
            self.assertIn(hostname, source)
        self.assertIn("staging_api_unknown", source)
        self.assertIn("bridge_staging_unknown", source)
        self.assertIn("bridge_private_callback", source)
        self.assertIn('"staging_gateway_readonly": "PASS"', source)

    @staticmethod
    def valid_environment() -> dict[str, str]:
        environment: dict[str, str] = {}
        bind_names = {
            "CADDY_PUBLIC_BIND",
            "CADDY_PRIVATE_METRICS_BIND",
            "CADDY_PRIVATE_INGRESS_BIND",
        }
        for name in REQUIRED_ENVIRONMENT:
            if name in bind_names:
                environment[name] = "127.0.0.1"
            elif name.endswith("_CIDRS"):
                environment[name] = "127.0.0.1/32"
            elif name.endswith("_UPSTREAM"):
                environment[name] = "127.0.0.1:18001"
            elif name == "CADDY_N8N_EDITOR_MAX_REQUEST_BODY":
                environment[name] = "10485760"
            else:
                raise AssertionError(f"test fixture needs a value for {name}")
        return environment


if __name__ == "__main__":
    unittest.main()
