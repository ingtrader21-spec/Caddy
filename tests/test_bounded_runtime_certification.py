from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundedRuntimeCertificationTests(unittest.TestCase):
    def test_staging_source_certification_is_complete_and_non_live(self):
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        for token in (
            "name: staging-certification",
            "environment: staging-readonly",
            "scripts/validate-ci.sh",
            "scripts/build-release-inputs.sh",
            "tests/runtime-bind-test.sh",
            "tests/runtime-canary-test.sh",
            "scripts/verify-rollback-baseline.sh",
            "aquasecurity/trivy-action@",
            '"public_traffic_changed": False',
        ):
            self.assertIn(token, workflow)
        self.assertNotIn("run-immutable-runtime.sh", workflow)
        self.assertNotIn("docker compose up", workflow)

    def test_runtime_workflow_chains_the_same_signed_digest(self):
        workflow = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()
        for token in (
            "branches: [production]",
            "runs-on: [self-hosted, codestra-staging]",
            "environment: staging-readonly",
            "CADDY_STAGING_RUNNER_LABEL=codestra-staging",
            "bounded-staging-runtime-v2.sh",
            "staging_evidence_sha256",
            "needs: bounded-staging-runtime",
            "runs-on: [self-hosted, codestra-production-canary]",
            "environment: production-readonly-canary",
            "CADDY_PRODUCTION_RUNNER_LABEL=codestra-production-canary",
            "bounded-production-readonly-canary-v2.sh",
            "cosign verify",
            "cosign verify-attestation",
        ):
            self.assertIn(token, workflow)
        self.assertLess(
            workflow.index("name: bounded-staging-runtime"),
            workflow.index("name: production-readonly-canary"),
        )

    def test_staging_runtime_is_isolated_from_public_interfaces(self):
        script = (ROOT / "scripts/bounded-staging-runtime-v2.sh").read_text()
        for token in (
            "--network \"$NETWORK\"",
            "--ip \"$candidate_ip\"",
            "-p 127.0.0.1:18080:80/tcp",
            "-p 127.0.0.1:18443:443/tcp",
            "-p 127.0.0.1:18443:443/udp",
            "-p 127.0.0.1:12020:2020/tcp",
            "-p 127.0.0.1:28080:18080/tcp",
            "candidate_removed",
            '"public_traffic_changed": False',
            '"dns_changed": False',
            '"firewall_changed": False',
            '"ssh_changed": False',
        ):
            self.assertIn(token, script)
        self.assertNotIn("--network host", script)
        self.assertNotIn("run-immutable-runtime.sh", script)
        self.assertNotIn("rollback-runtime.sh", script)

    def test_production_canary_is_strictly_read_only_by_default(self):
        script = (ROOT / "scripts/bounded-production-readonly-canary-v2.sh").read_text()
        for token in (
            "caddy_readonly_validator.py",
            "pre-canary-runtime.json",
            "post-canary-runtime.json",
            "cmp -s pre-canary-runtime.json post-canary-runtime.json",
            "codestra-http3-probe",
            "websocket_probe.py",
            'readonly MODE="${CADDY_PRODUCTION_CANARY_MODE:-pre-activation}"',
            'post_activation = mode == "post-activation"',
            '"write_requests_sent": False',
            '"candidate_started_on_production": post_activation',
            '"live_runtime_is_candidate": post_activation',
            '"public_traffic_changed": False',
        ):
            self.assertIn(token, script)
        for forbidden in (
            "docker compose",
            "run-immutable-runtime.sh",
            "rollback-runtime.sh",
            "stop codestra-caddy",
            "rm -f codestra-caddy",
            "restart codestra-caddy",
            "-X POST",
            "--data-binary",
        ):
            self.assertNotIn(forbidden, script)

    def test_websocket_probe_keeps_release_http3_and_supports_staging_port(self):
        probe = (ROOT / "scripts/websocket_probe.py").read_text()
        for token in (
            "usage: websocket_probe.py HOST IP PATH [PORT]",
            "port = 18443",
            "if port == 443 and probe.is_file()",
            "codestra-http3-probe",
        ):
            self.assertIn(token, probe)


if __name__ == "__main__":
    unittest.main()
