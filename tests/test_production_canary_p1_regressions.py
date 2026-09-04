from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUNDED = ROOT / "scripts/bounded-production-readonly-canary-v2.sh"
CANARY = ROOT / "scripts/production-canary.sh"
ACTIVATION = ROOT / "scripts/manual-production-activate.sh"
RUN = ROOT / "scripts/run-immutable-runtime.sh"


class ProductionCanaryP1RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bounded = BOUNDED.read_text(encoding="utf-8")
        self.canary = CANARY.read_text(encoding="utf-8")
        self.activation = ACTIVATION.read_text(encoding="utf-8")
        self.run = RUN.read_text(encoding="utf-8")

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

    def test_full_canary_has_explicit_pre_and_post_activation_modes(self) -> None:
        for token in (
            "CADDY_PRODUCTION_CANARY_MODE",
            "pre-activation",
            "post-activation",
            "live_runtime_is_candidate",
            '"candidate_started_on_production": post_activation',
            '"live_mtls_server_certificate_verified": True',
        ):
            self.assertIn(token, self.bounded)

    def test_authenticated_mtls_probe_verifies_the_server_certificate(self) -> None:
        with_cert = self.command_assignment("with_cert")
        self.assertNotIn("-k", with_cert)
        self.assertIn('--cacert "$MTLS_CA_CERT"', with_cert)
        self.assertIn('--cert "$MTLS_CLIENT_CERT"', with_cert)
        self.assertIn('--key "$MTLS_CLIENT_KEY"', with_cert)

    def test_no_client_certificate_probe_still_verifies_the_server(self) -> None:
        without_cert = self.command_assignment("without_cert")
        self.assertNotIn("-k", without_cert)
        self.assertIn('--cacert "$MTLS_CA_CERT"', without_cert)
        self.assertNotIn('--cert "$MTLS_CLIENT_CERT"', without_cert)

    def test_replacement_path_reruns_the_complete_fixed_target_suite(self) -> None:
        for token in (
            "bounded-production-readonly-canary-v2.sh",
            "CADDY_PRODUCTION_CANARY_MODE=post-activation",
            "post_activation_full_canary",
            "post-activation-canary-evidence.json",
            '"live_runtime_is_candidate"] is True',
            '"candidate_started_on_production"] is True',
            '"live_mtls_server_certificate_verified"] is True',
            "FULL_POST_ACTIVATION_CANARY=PASS",
        ):
            self.assertIn(token, self.canary)
        self.assertIn('canary_output="$("$ROOT/scripts/production-canary.sh")"', self.run)
        self.assertLess(
            self.canary.index("CADDY_PRODUCTION_CANARY_MODE=post-activation"),
            self.canary.index("CADDY_PRODUCTION_CANARY=PASS"),
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


if __name__ == "__main__":
    unittest.main()
