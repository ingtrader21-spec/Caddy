from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/manual-production-orchestrator.yml"
PREFLIGHT = ROOT / "scripts/manual-production-preflight.sh"
STAGING = ROOT / "scripts/manual-staging-certify.sh"
CANARY = ROOT / "scripts/manual-production-readonly-canary.sh"


class ManualProductionOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.preflight = PREFLIGHT.read_text(encoding="utf-8")
        self.staging = STAGING.read_text(encoding="utf-8")
        self.canary = CANARY.read_text(encoding="utf-8")
        self.all_source = "\n".join(
            (self.workflow, self.preflight, self.staging, self.canary)
        )

    def test_cd_is_manual_and_exact_production_only(self) -> None:
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("RUN_CADDY_PRODUCTION", self.workflow)
        self.assertNotIn("\n  push:\n", self.workflow)
        self.assertNotIn("\n  schedule:\n", self.workflow)
        for token in (
            '[[ "$GITHUB_REF" == "refs/heads/production" ]]',
            "git rev-parse origin/production",
            '[[ -z "$(git status --porcelain)" ]]',
            "bash scripts/validate-ci.sh",
        ):
            self.assertIn(token, self.preflight)

    def test_preflight_requires_canonical_no_bypass_governance(self) -> None:
        for token in (
            "Protect Caddy promotion branches",
            "bypass_actors",
            "refs/heads/development",
            "refs/heads/test",
            "refs/heads/staging",
            "refs/heads/production",
            "refs/heads/main",
            "validate-source",
            "validate-merge-result",
            "promotion-guard",
            "immutable-release-gate",
        ):
            self.assertIn(token, self.preflight)

    def test_exact_signed_candidate_and_release_packet_are_bound(self) -> None:
        for token in (
            "caddy-production-${source_sha}",
            "immutable-release.yml/runs",
            "caddy-release-evidence-${source_sha}",
            "org.opencontainers.image.source",
            "org.opencontainers.image.revision",
            "io.codestra.caddy.config.sha256",
            "cosign verify",
            "cosign verify-attestation",
            "https://codestra.co/attestations/caddy-source/v2",
            "verified-image-signature.json",
            "verified-source-attestation.json",
            "release-evidence.SHA256SUMS",
        ):
            self.assertIn(token, self.all_source)
        self.assertNotIn(":latest", self.all_source)

    def test_staging_is_protected_and_rollback_is_evidence_bound(self) -> None:
        for token in (
            "runs-on: [self-hosted, codestra-staging]",
            "environment: staging-readonly",
            "scripts/manual-staging-certify.sh",
        ):
            self.assertIn(token, self.workflow)
        for token in (
            "deploy/compose.runtime.yaml",
            "bounded-staging-runtime-v2.sh",
            "verify-rollback-baseline.sh",
            "bounded-staging-runtime-evidence.json",
            "one-click-rollback-evidence.json",
            "staging_certified:true",
            "rollback_rehearsed:true",
            "production_changed:false",
            "live_effects_enabled:false",
        ):
            self.assertIn(token, self.staging)

    def test_production_canary_requires_staging_and_is_read_only(self) -> None:
        for token in (
            "needs: [verify-production-candidate, bounded-staging-and-rollback]",
            "runs-on: [self-hosted, codestra-production-canary]",
            "environment: production-readonly-canary",
            "CADDY_STAGING_EVIDENCE_SHA256",
            "CADDY_ROLLBACK_EVIDENCE_SHA256",
            "scripts/manual-production-readonly-canary.sh",
        ):
            self.assertIn(token, self.workflow)
        for token in (
            "bounded-production-readonly-canary-v2.sh",
            "cmp -s pre-canary-runtime.json post-canary-runtime.json",
            ".write_requests_sent == false",
            ".candidate_started_on_production == false",
            ".public_traffic_changed == false",
            "production_canary_read_only:true",
            "full_live_activation_authorized:false",
        ):
            self.assertIn(token, self.canary)

    def test_no_second_runtime_or_live_effect_path_is_added(self) -> None:
        for forbidden in (
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.production.yml",
            "compose.production.yaml",
            "run-immutable-runtime.sh",
            "rollback-runtime.sh",
            "stop codestra-caddy",
            "restart codestra-caddy",
            "rm -f codestra-caddy",
            "-X POST",
            "--data-binary",
        ):
            self.assertNotIn(forbidden, self.all_source)

    def test_final_verdict_fails_closed(self) -> None:
        for token in (
            "if: always()",
            "verdict=NO_GO",
            "READ_ONLY_CANARY_GO",
            "CADDY_ONE_CLICK_PRODUCTION=NO_GO",
            "exit 1",
            "Full live-effect activation: **not authorized**",
        ):
            self.assertIn(token, self.workflow)


if __name__ == "__main__":
    unittest.main()
