from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/manual-production-orchestrator.yml"
PREFLIGHT = ROOT / "scripts/manual-production-preflight.sh"
STAGING = ROOT / "scripts/manual-staging-certify.sh"
READONLY = ROOT / "scripts/manual-production-readonly-canary.sh"
ACTIVATION = ROOT / "scripts/manual-production-activate.sh"
CAPTURE = ROOT / "scripts/capture-runtime-baseline.sh"
RUN = ROOT / "scripts/run-immutable-runtime.sh"
ROLLBACK = ROOT / "scripts/rollback-runtime.sh"


class ManualProductionOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.preflight = PREFLIGHT.read_text(encoding="utf-8")
        self.staging = STAGING.read_text(encoding="utf-8")
        self.readonly = READONLY.read_text(encoding="utf-8")
        self.activation = ACTIVATION.read_text(encoding="utf-8")
        self.capture = CAPTURE.read_text(encoding="utf-8")
        self.run = RUN.read_text(encoding="utf-8")
        self.rollback = ROLLBACK.read_text(encoding="utf-8")
        self.all_source = "\n".join(
            (
                self.workflow,
                self.preflight,
                self.staging,
                self.readonly,
                self.activation,
                self.capture,
                self.run,
                self.rollback,
            )
        )

    def test_cd_is_one_manual_exact_production_entrypoint(self) -> None:
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("RUN_CADDY_PRODUCTION", self.workflow)
        self.assertNotIn("\n  push:\n", self.workflow)
        self.assertNotIn("\n  schedule:\n", self.workflow)
        for token in (
            '[[ "$GITHUB_REF" == refs/heads/production ]]',
            "git rev-parse origin/production",
            '[[ -z "$(git status --porcelain)" ]]',
            "bash scripts/validate-ci.sh",
        ):
            self.assertIn(token, self.preflight)

    def test_preflight_requires_governance_and_three_protected_environments(self) -> None:
        for token in (
            "Protect Caddy promotion branches",
            "bypass_actors",
            "refs/heads/development",
            "refs/heads/test",
            "refs/heads/staging",
            "refs/heads/production",
            "refs/heads/main",
            "required_approving_review_count",
            "require_last_push_approval",
            "validate-source",
            "validate-merge-result",
            "promotion-guard",
            "immutable-release-gate",
            "staging-readonly production-readonly-canary production-activation",
            ".deployment_branch_policy.protected_branches == true",
        ):
            self.assertIn(token, self.preflight)
        for token in (
            "environment: staging-readonly",
            "environment: production-readonly-canary",
            "environment: production-activation",
            "runs-on: [self-hosted, codestra-staging]",
            "runs-on: [self-hosted, codestra-production-canary]",
            "runs-on: [self-hosted, codestra-production]",
        ):
            self.assertIn(token, self.workflow)

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

    def test_staging_and_historical_rollback_precede_production(self) -> None:
        for token in (
            "scripts/manual-staging-certify.sh",
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
            self.assertIn(token, self.workflow + self.staging)
        self.assertLess(
            self.workflow.index("bounded-staging-and-rollback:"),
            self.workflow.index("production-readonly-canary:"),
        )

    def test_production_readonly_canary_is_unchanged_and_write_free(self) -> None:
        for token in (
            "needs: [verify-production-candidate, bounded-staging-and-rollback]",
            "CADDY_STAGING_EVIDENCE_SHA256",
            "CADDY_ROLLBACK_EVIDENCE_SHA256",
            "scripts/manual-production-readonly-canary.sh",
            "bounded-production-readonly-canary-v2.sh",
            "cmp -s pre-canary-runtime.json post-canary-runtime.json",
            ".write_requests_sent == false",
            ".candidate_started_on_production == false",
            ".public_traffic_changed == false",
            "production_canary_read_only:true",
            "full_live_activation_authorized:false",
        ):
            self.assertIn(token, self.workflow + self.readonly)

    def test_activation_requires_the_readonly_receipt_and_captured_live_baseline(self) -> None:
        for token in (
            "needs: [verify-production-candidate, bounded-staging-and-rollback, production-readonly-canary]",
            "CADDY_PRODUCTION_ENV_FILE",
            "scripts/manual-production-activate.sh",
            "scripts/capture-runtime-baseline.sh",
            "scripts/run-immutable-runtime.sh",
            "production-activation-evidence.json",
            "automatic_rollback_armed",
            "candidate_runtime_live",
        ):
            self.assertIn(token, self.workflow + self.activation)
        for token in (
            "codestra.caddy.manual-production-orchestrator-receipt.v1",
            ".staging_certified == true",
            ".rollback_rehearsed == true",
            ".production_canary_read_only == true",
            ".write_requests_sent == false",
            '.verdict == "READ_ONLY_CANARY_PASS"',
        ):
            self.assertIn(token, self.activation)

    def test_runtime_environment_is_parsed_without_shell_evaluation(self) -> None:
        for token in (
            "runtime_environment_syntax",
            "runtime_environment_duplicate",
            "runtime_environment_missing",
            'export "$key=$value"',
            "0:0:600",
        ):
            self.assertIn(token, self.activation)
        self.assertNotIn('source "$RUNTIME_ENV_FILE"', self.activation)
        self.assertNotIn("eval ", self.activation)

    def test_captured_baseline_contains_exact_runtime_identity(self) -> None:
        for token in (
            "codestra.caddy-runtime-rollback-baseline.v1",
            "runtime_environment_file",
            "runtime_environment_sha256",
            "data_dir",
            "config_dir",
            "release_id",
            "signature_verified",
            "listener_ownership",
            "effective_access_log_redaction",
            "install -m 0600 -o root -g root",
            "CADDY_BASELINE_CAPTURE=PASS",
        ):
            self.assertIn(token, self.capture)

    def test_activation_automatically_rolls_back_and_propagates_rollback_failure(self) -> None:
        for token in (
            "CADDY_ROLLBACK_BASELINE_FILE",
            "CADDY_ROLLBACK_EVIDENCE_FILE",
            "rollback_after_failure",
            "activation_rolled_back",
            "activation_and_rollback_failed",
            "final_identity_readback",
            "CADDY_ACTIVATION=PASS",
        ):
            self.assertIn(token, self.run)
        for token in (
            "codestra.caddy-runtime-rollback-result.v1",
            "runtime_environment_sha256",
            "release_readback",
            "production_canary",
            "up -d --pull never --no-build",
            "CADDY_ROLLBACK=PASS",
        ):
            self.assertIn(token, self.rollback)

    def test_every_post_mutation_failure_has_a_rollback_path(self) -> None:
        for token in (
            'if ! "$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy',
            "rollback_after_failure compose_up",
            "rollback_after_failure unhealthy_candidate",
            "rollback_after_failure runtime_readback",
            "rollback_after_failure final_identity_inspect",
            "rollback_after_failure final_identity_readback",
        ):
            self.assertIn(token, self.run)
        for token in (
            "rollback_wrapper_failure activation_failed_without_rollback_proof",
            "rollback_wrapper_failure activation_receipt_missing",
            "rollback_wrapper_failure final_runtime_validator_failed",
            "rollback_wrapper_failure final_runtime_readback_failed",
            "rollback_wrapper_failure activation_evidence_write_failed",
            "CADDY_MANUAL_PRODUCTION_ACTIVATION=NO_GO:ROLLBACK_FAILED",
        ):
            self.assertIn(token, self.activation)

    def test_wrapper_rollback_remains_armed_through_final_receipt(self) -> None:
        for token in (
            "trap rollback_wrapper_on_exit EXIT HUP INT TERM",
            "wrapper_terminated_before_durable_receipt",
            "wrapper_rollback_armed=true",
        ):
            self.assertIn(token, self.activation)
        self.assertLess(
            self.activation.index("wrapper_rollback_armed=true"),
            self.activation.index('bash "$ROOT/scripts/run-immutable-runtime.sh"'),
        )
        self.assertLess(
            self.activation.index("CADDY_MANUAL_PRODUCTION_ACTIVATION=PASS"),
            self.activation.rindex("wrapper_rollback_armed=false"),
        )
        self.assertIn(
            "CADDY_ACTIVATION_SIGNAL_ROLLBACK_OWNER=wrapper",
            self.activation,
        )
        self.assertIn("termination_rollback_delegated", self.run)

    def test_stale_rollback_proof_is_removed_before_activation(self) -> None:
        reset = 'rm -f -- "$ROLLBACK_RESULT_FILE"'
        activation = 'bash "$ROOT/scripts/run-immutable-runtime.sh"'
        self.assertIn("invalid_evidence_id", self.activation)
        self.assertIn(reset, self.activation)
        self.assertLess(
            self.activation.index('baseline_sha256="$(sha256sum "$BASELINE_FILE"'),
            self.activation.index(reset),
        )
        self.assertLess(self.activation.index(reset), self.activation.index(activation))
        self.assertLess(
            self.activation.index("rollback_result_reset_failed"),
            self.activation.index("wrapper_rollback_armed=true"),
        )

    def test_unified_compose_remains_the_only_runtime(self) -> None:
        self.assertIn("deploy/compose.runtime.yaml", self.all_source)
        for forbidden in (
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.production.yml",
            "compose.production.yaml",
            "--build",
            "update-ref",
            "--force",
            "-X POST",
            "--data-binary",
        ):
            self.assertNotIn(forbidden, self.all_source)

    def test_final_verdict_is_full_caddy_go_but_not_application_write_authority(self) -> None:
        for token in (
            "if: always()",
            "verdict=NO_GO",
            "FULL_PRODUCTION_GO",
            "CADDY_ONE_CLICK_PRODUCTION=NO_GO",
            "CADDY_ONE_CLICK_PRODUCTION=FULL_PRODUCTION_GO",
            "caddy_runtime_live",
            "application_writes_authorized:false",
            "provider_delivery_authorized:false",
        ):
            self.assertIn(token, self.workflow)


if __name__ == "__main__":
    unittest.main()
