from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy/compose.runtime.yaml"
ACTIVATE = ROOT / "scripts/manual-production-activate.sh"
STAGING = ROOT / "scripts/bounded-staging-runtime-v2.sh"
VALIDATOR = ROOT / "scripts/caddy_readonly_validator.py"


class LegacyRollbackStagingKongTests(unittest.TestCase):
    def test_compose_allows_pre_variable_rollback_without_production_fallback(self) -> None:
        source = COMPOSE.read_text(encoding="utf-8")
        self.assertIn(
            'CADDY_STAGING_KONG_UPSTREAM: "${CADDY_STAGING_KONG_UPSTREAM:-}"',
            source,
        )
        self.assertNotIn(
            'CADDY_STAGING_KONG_UPSTREAM: "${CADDY_STAGING_KONG_UPSTREAM:?',
            source,
        )
        staging_line = next(
            line for line in source.splitlines()
            if "CADDY_STAGING_KONG_UPSTREAM:" in line
        )
        self.assertNotIn("CADDY_KONG_UPSTREAM", staging_line.replace("CADDY_STAGING_KONG_UPSTREAM", ""))

    def test_current_candidate_paths_still_require_dedicated_staging_kong(self) -> None:
        activation = ACTIVATE.read_text(encoding="utf-8")
        staging = STAGING.read_text(encoding="utf-8")
        validator = VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("CADDY_STAGING_KONG_UPSTREAM", activation)
        self.assertIn("missing_env", staging)
        self.assertIn("staging_kong_not_dedicated", staging)
        self.assertIn('CONFIG_CONDITIONAL_ENVIRONMENT = {\n    "CADDY_STAGING_KONG_UPSTREAM",', validator)

    def test_new_candidate_never_falls_back_to_production_kong(self) -> None:
        staging = STAGING.read_text(encoding="utf-8")
        self.assertIn(
            '[[ "${values[CADDY_STAGING_KONG_UPSTREAM]}" != "${values[CADDY_KONG_UPSTREAM]}" ]]',
            staging,
        )


if __name__ == "__main__":
    unittest.main()
