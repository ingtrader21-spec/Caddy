from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/manual-production-orchestrator.yml"


class ManualProductionOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")

    def test_is_manual_and_requires_exact_production_head(self) -> None:
        for token in (
            "workflow_dispatch:",
            "RUN_CADDY_PRODUCTION",
            "test \"$GITHUB_REF\" = refs/heads/production",
            "git rev-parse origin/production",
            "test -z \"$(git status --porcelain)\"",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn("\n  push:\n", self.source)
        self.assertNotIn("\n  schedule:\n", self.source)

    def test_requires_canonical_branch_governance(self) -> None:
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
            self.assertIn(token, self.source)

    def test_verifies_exact_signed_release_and_evidence(self) -> None:
        for token in (
            "caddy-production-${source_sha}",
            "immutable-release.yml/runs",
            "caddy-release-evidence-${source_sha}",
            "org.opencontainers.image.revision",
            "io.codestra.caddy.config.sha256",
            "cosign verify",
            "cosign verify-attestation",
            "https://codestra.co/attestations/caddy-source/v2",
            "verified-image-signature.json",
            "verified-source-attestation.json",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn(":latest", self.source)

    def test_staging_and_rollback_use_protected_shared_runner(self) -> None:
        for token in (
            "runs-on: [self-hosted, codestra-staging]",
            "environment: staging-readonly",
            "bounded-staging-runtime-v2.sh",
            "verify-rollback-baseline.sh",
            "bounded-staging-runtime-evidence.json",
            "one-click-rollback-evidence.json",
            '"rollback_rehearsed":true',
            '"production_changed":false',
        ):
            self.assertIn(token, self.source)

    def test_production_canary_depends_on_staging_and_is_read_only(self) -> None:
        for token in (
            "needs: [verify-production-candidate, bounded-staging-and-rollback]",
            "runs-on: [self-hosted, codestra-production-canary]",
            "environment: production-readonly-canary",
            "CADDY_STAGING_EVIDENCE_SHA256",
            "CADDY_ROLLBACK_EVIDENCE_SHA256",
            "bounded-production-readonly-canary-v2.sh",
            "cmp -s pre-canary-runtime.json post-canary-runtime.json",
            ".write_requests_sent == false",
            ".candidate_started_on_production == false",
            ".public_traffic_changed == false",
            '"full_live_activation_authorized":false',
        ):
            self.assertIn(token, self.source)

    def test_workflow_reuses_single_runtime_authority(self) -> None:
        self.assertIn("deploy/compose.runtime.yaml", self.source)
        for forbidden in (
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.production.yml",
            "compose.production.yaml",
            "run-immutable-runtime.sh",
            "rollback-runtime.sh",
            "-X POST",
            "--data-binary",
            "stop codestra-caddy",
            "restart codestra-caddy",
            "rm -f codestra-caddy",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_final_verdict_fails_closed(self) -> None:
        for token in (
            "if: always()",
            "verdict=NO_GO",
            "READ_ONLY_CANARY_GO",
            "CADDY_ONE_CLICK_PRODUCTION=NO_GO",
            "exit 1",
            "Full live-effect activation: **not authorized**",
        ):
            self.assertIn(token, self.source)


if __name__ == "__main__":
    unittest.main()
