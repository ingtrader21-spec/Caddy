from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDED = ROOT / "scripts/bounded-production-readonly-canary-v2.sh"
CANARY = ROOT / "scripts/production-canary.sh"
ACTIVATION = ROOT / "scripts/manual-production-activate.sh"
ROLLBACK = ROOT / "scripts/rollback-runtime.sh"
RUN = ROOT / "scripts/run-immutable-runtime.sh"
WORKFLOW = ROOT / ".github/workflows/manual-production-orchestrator.yml"
GITIGNORE = ROOT / ".gitignore"


class ProductionCanaryP1RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bounded = BOUNDED.read_text(encoding="utf-8")
        self.canary = CANARY.read_text(encoding="utf-8")
        self.activation = ACTIVATION.read_text(encoding="utf-8")
        self.rollback = ROLLBACK.read_text(encoding="utf-8")
        self.run = RUN.read_text(encoding="utf-8")
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.gitignore = GITIGNORE.read_text(encoding="utf-8")

    def command_assignment(self, name: str) -> str:
        start = self.bounded.index(f'{name}="$(')
        end = self.bounded.index("\n[[", start)
        return self.bounded[start:end]

    def test_activation_consumes_the_v2_readonly_receipt(self) -> None:
        self.assertIn(
            '.schema == "codestra.caddy.manual-production-orchestrator-receipt.v2"',
            self.activation,
        )
        self.assertIn(
            "Legacy codestra.caddy.manual-production-orchestrator-receipt.v1 packets are",
            self.activation,
        )

    def test_full_canary_has_explicit_pre_post_and_rollback_modes(self) -> None:
        for token in (
            "CADDY_PRODUCTION_CANARY_MODE",
            "pre-activation|post-activation|rollback",
            "live_runtime_is_expected_tuple",
            "live_runtime_is_candidate",
            '"rollback_validation": rollback_validation',
            '"candidate_started_on_production": post_activation',
            '"live_mtls_server_certificate_verified": True',
        ):
            self.assertIn(token, self.bounded)

    def test_rollback_does_not_claim_staging_certification(self) -> None:
        self.assertIn(
            'bounded_staging_runtime = "NOT_APPLICABLE" if rollback_validation else "PASS"',
            self.bounded,
        )
        self.assertIn(
            '"bounded_staging_runtime": bounded_staging_runtime',
            self.bounded,
        )
        self.assertIn(
            '[[ "$MODE" == rollback ]] && bounded_staging_runtime=NOT_APPLICABLE',
            self.bounded,
        )
        self.assertIn(
            '"BOUNDED_STAGING_RUNTIME=$bounded_staging_runtime"',
            self.bounded,
        )
        self.assertNotIn('"bounded_staging_runtime": "PASS"', self.bounded)

    def test_authenticated_mtls_probe_verifies_the_server_certificate(self) -> None:
        with_cert = self.command_assignment("with_cert")
        self.assertNotIn(" -k", with_cert)
        self.assertNotIn("-ksS", with_cert)
        self.assertIn('--cacert "$MTLS_CA_CERT"', with_cert)
        self.assertIn('--cert "$MTLS_CLIENT_CERT"', with_cert)
        self.assertIn('--key "$MTLS_CLIENT_KEY"', with_cert)

    def test_no_client_certificate_probe_still_verifies_the_server(self) -> None:
        without_cert = self.command_assignment("without_cert")
        self.assertNotIn(" -k", without_cert)
        self.assertNotIn("-ksS", without_cert)
        self.assertIn('--cacert "$MTLS_CA_CERT"', without_cert)
        self.assertNotIn('--cert "$MTLS_CLIENT_CERT"', without_cert)

    def test_replacement_path_reruns_the_complete_fixed_target_suite(self) -> None:
        for token in (
            "bounded-production-readonly-canary-v2.sh",
            'readonly CANARY_MODE="${CADDY_PRODUCTION_CANARY_MODE:-post-activation}"',
            'export CADDY_PRODUCTION_CANARY_MODE="$CANARY_MODE"',
            "full_fixed_target_canary",
            'assert value["live_runtime_is_candidate"] is post_activation',
            'assert value["candidate_started_on_production"] is post_activation',
            'assert value["live_mtls_server_certificate_verified"] is True',
            "FULL_FIXED_TARGET_CANARY=PASS",
        ):
            self.assertIn(token, self.canary)
        self.assertIn('canary_output="$("$ROOT/scripts/production-canary.sh")"', self.run)
        self.assertLess(
            self.canary.index('export CADDY_PRODUCTION_CANARY_MODE="$CANARY_MODE"'),
            self.canary.index("CADDY_PRODUCTION_CANARY=PASS"),
        )

    def test_rollback_validates_restored_image_independently_of_checkout(self) -> None:
        for token in (
            'if [[ "$MODE" != rollback ]]; then',
            'image_probe="$(docker_cmd create "$IMAGE")"',
            'docker_cmd cp "$image_probe:/etc/caddy/." "$work/image-config"',
            "image_config_identity",
            'expected_tuple_live = mode in {"post-activation", "rollback"}',
            'rollback_validation = mode == "rollback"',
        ):
            self.assertIn(token, self.bounded)
        for token in (
            "CADDY_PRODUCTION_CANARY_MODE=rollback",
            "rollback-canary-evidence.json",
            "rollback-canary.SHA256SUMS",
            "restored_image_validated_independently_of_checkout",
            'assert value["live_runtime_is_expected_tuple"] is True',
            'assert value["rollback_validation"] is True',
            'assert value["live_runtime_is_candidate"] is False',
        ):
            self.assertIn(token, self.rollback)

    def test_rollback_verifies_source_attestation_before_replacement(self) -> None:
        for token in (
            "verify-attestation",
            "https://codestra.co/attestations/caddy-source/v2",
            "verify-image-attestation.py",
            "CADDY_SOURCE_ATTESTATION=PASS",
            "source_attestation_verified",
            "attested_source_sha",
            "attested_image_digest",
            "attested_config_sha256",
        ):
            self.assertIn(token, self.rollback)
        self.assertLess(
            self.rollback.index('"$COSIGN_BIN" verify-attestation'),
            self.rollback.index('"$DOCKER_BIN" compose -f "$COMPOSE" up'),
        )

    def test_protected_activation_environment_requires_mtls_paths(self) -> None:
        for token in (
            "CADDY_PRODUCTION_MTLS_CLIENT_CERT",
            "CADDY_PRODUCTION_MTLS_CLIENT_KEY",
            "CADDY_PRODUCTION_MTLS_CA_CERT",
            "protected_mtls_path",
            "protected_mtls_file",
        ):
            self.assertIn(token, self.activation)

    def test_activation_binds_post_replacement_evidence_before_pass(self) -> None:
        for token in (
            "post-activation-canary-evidence.json",
            "post_activation_canary_sha256",
            '.canary_mode == "post-activation"',
            ".live_runtime_is_candidate == true",
            ".candidate_started_on_production == true",
            ".live_mtls_server_certificate_verified == true",
            ".write_requests_sent == false",
            "post_activation_evidence_invalid",
        ):
            self.assertIn(token, self.activation)
        self.assertLess(
            self.activation.index("phase=post_activation_canary_evidence"),
            self.activation.index("phase=complete"),
        )

    def test_complete_canary_packets_are_staged_for_artifact_upload(self) -> None:
        for token in (
            'readonly OUTPUT_DIR="$ROOT/activation-evidence"',
            'manifest_name="${evidence_prefix}-canary.SHA256SUMS"',
            'sha256sum --check --strict "$manifest_name"',
            "ARTIFACT_PACKET_MANIFEST_SHA256",
        ):
            self.assertIn(token, self.canary)
        self.assertIn("activation-evidence/", self.gitignore)
        self.assertIn("release-evidence/", self.gitignore)
        self.assertIn("staging-evidence/", self.gitignore)
        self.assertIn("readonly-evidence/", self.gitignore)
        self.assertIn("path: activation-evidence/", self.workflow)
        self.assertNotIn("rm -rf activation-evidence", self.workflow)

    def test_rollback_manifest_is_complete_before_receipt_is_bound(self) -> None:
        for token in (
            "CADDY_ROLLBACK_ATTESTATION_FILE",
            "CADDY_ROLLBACK_ATTESTATION_VERIFICATION_FILE",
            'manifest_files+=("$rollback_attestation_name" "$rollback_attestation_verification_name")',
            'data["rollback_source_attestation_sha256"]',
            'data["rollback_source_attestation_verification_sha256"]',
            "ROLLBACK_SOURCE_ATTESTATION_SHA256",
            "ROLLBACK_SOURCE_ATTESTATION_VERIFICATION_SHA256",
        ):
            self.assertIn(token, self.canary)
        self.assertLess(
            self.canary.index(
                'manifest_files+=("$rollback_attestation_name" "$rollback_attestation_verification_name")'
            ),
            self.canary.index('packet_manifest_sha256="$('),
        )
        self.assertNotIn(">> rollback-canary.SHA256SUMS", self.rollback)

    def test_rollback_receipt_binds_the_uploaded_canary_packet(self) -> None:
        for token in (
            "canary_evidence_sha256",
            "canary_packet_manifest_sha256",
            "ROLLBACK_CANARY_MANIFEST_SHA256",
            "sha256sum --check --strict rollback-canary.SHA256SUMS",
            "rollback-source-attestation.verified.json",
            "rollback-source-attestation-verification.txt",
            "source_attestation_sha256",
            "source_attestation_verification_sha256",
            "ROLLBACK_SOURCE_ATTESTATION_SHA256",
            "ROLLBACK_SOURCE_ATTESTATION_VERIFICATION_SHA256",
            "rollback_canary_manifest_claim",
            'receipt["artifact_packet_manifest_sha256"] == manifest_sha',
            'receipt["rollback_source_attestation_sha256"] == attestation_sha',
            'receipt["rollback_source_attestation_verification_sha256"] == attestation_verification_sha',
        ):
            self.assertIn(token, self.rollback)

    def test_rollback_manifest_has_an_exact_evidence_member_set(self) -> None:
        for name in (
            "rollback-canary-evidence.json",
            "rollback-canary-runtime-before.json",
            "rollback-canary-runtime-after.json",
            "rollback-canary.txt",
            "rollback-source-attestation.verified.json",
            "rollback-source-attestation-verification.txt",
        ):
            self.assertIn(name, self.rollback)
        self.assertIn("assert len(entries) == len(expected)", self.rollback)
        self.assertIn("assert set(entries) == expected", self.rollback)

    def test_activation_rolls_back_on_termination_after_mutation_starts(self) -> None:
        for token in (
            "cleanup_and_rollback_on_exit",
            "trap cleanup_and_rollback_on_exit EXIT HUP INT TERM",
            "mutation_armed=true",
            "termination_rolled_back",
            "termination_rollback_failed",
        ):
            self.assertIn(token, self.run)
        self.assertLess(
            self.run.index("mutation_armed=true"),
            self.run.index('compose -f "$COMPOSE" up -d'),
        )
        self.assertLess(
            self.run.index("CADDY_ACTIVATION=PASS"),
            self.run.rindex("mutation_armed=false"),
        )


if __name__ == "__main__":
    unittest.main()
