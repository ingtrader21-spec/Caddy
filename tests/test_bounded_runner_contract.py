from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bounded-runtime-certification.yml"


class BoundedRunnerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")

    def test_staging_uses_platform_canonical_runner_and_environment(self) -> None:
        self.assertIn("runs-on: [self-hosted, codestra-staging]", self.source)
        self.assertIn("environment: staging-readonly", self.source)
        self.assertIn("CADDY_STAGING_RUNNER_LABEL=codestra-staging", self.source)

    def test_production_canary_uses_platform_canonical_runner_and_environment(self) -> None:
        self.assertIn(
            "runs-on: [self-hosted, codestra-production-canary]", self.source
        )
        self.assertIn("environment: production-readonly-canary", self.source)
        self.assertIn(
            "CADDY_PRODUCTION_RUNNER_LABEL=codestra-production-canary", self.source
        )

    def test_repository_specific_runner_declarations_are_absent(self) -> None:
        for prohibited in (
            "runs-on: [self-hosted, linux, x64, caddy-staging-readonly]",
            "runs-on: [self-hosted, linux, x64, caddy-production-readonly]",
            "\n    environment: production-readonly\n",
        ):
            self.assertNotIn(prohibited, self.source)

    def test_staging_evidence_is_required_before_production(self) -> None:
        self.assertIn("needs: bounded-staging-runtime", self.source)
        self.assertIn("CADDY_STAGING_EVIDENCE_SHA256", self.source)
        self.assertIn("staging-evidence-identity.txt", self.source)
        self.assertLess(
            self.source.index("bounded-staging-runtime:"),
            self.source.index("production-readonly-canary:"),
        )

    def test_canary_stays_read_only_and_exact_identity_bound(self) -> None:
        for token in (
            "Prove exact production authority",
            "Wait for and verify the signed immutable production candidate",
            "cosign verify",
            "cosign verify-attestation",
            "CADDY_CANARY_SOURCE_SHA",
            "CADDY_CANARY_IMAGE_DIGEST",
            "CADDY_CANARY_CONFIG_SHA256",
            "bounded-production-readonly-canary-v2.sh",
        ):
            self.assertIn(token, self.source)


if __name__ == "__main__":
    unittest.main()
