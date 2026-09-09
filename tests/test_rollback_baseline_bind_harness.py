from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RollbackBaselineBindHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = (ROOT / "tests/rollback-baseline-bind-test.sh").read_text(
            encoding="utf-8"
        )
        self.current = (ROOT / "tests/runtime-bind-test.sh").read_text(
            encoding="utf-8"
        )
        self.verify = (ROOT / "scripts/verify-rollback-baseline.sh").read_text(
            encoding="utf-8"
        )
        self.workflow = (ROOT / ".github/workflows/validate.yml").read_text(
            encoding="utf-8"
        )

    def test_current_image_proof_stays_network_isolated(self) -> None:
        self.assertIn("--network none", self.current)
        self.assertNotIn("--network host", self.current)
        self.assertIn("CADDY_RUNTIME_NETWORK=ISOLATED_NONE", self.current)

    def test_historical_host_bind_is_exact_serialized_and_preflighted(self) -> None:
        for token in (
            "config/release-baseline.v1.json",
            "codestra.caddy-release-baseline.v1",
            "item.get(\"mutable\") is False",
            "org.opencontainers.image.source",
            "org.opencontainers.image.revision",
            "RepoDigests",
            "flock",
            "bind_lock_timeout",
            "host_tcp_listener_in_use",
            "host_udp_listener_in_use",
            "--network host",
            "ROLLBACK_BIND_NETWORK=SERIALIZED_HOST",
            "host_listeners_not_released",
        ):
            self.assertIn(token, self.baseline)

    def test_historical_proof_retains_nonroot_security_and_guarded_readback(self) -> None:
        for token in (
            "--user 65532:65532",
            "--read-only",
            "--cap-drop ALL",
            "--cap-add NET_BIND_SERVICE",
            "--security-opt no-new-privileges:true",
            "process_snapshot()",
            "[[ -r \"$status\" ]] || return 1",
            "container_exited_before_socket_readback",
            "socket_readback_timeout",
            "0000000000000400",
            "ROLLBACK_BIND_EFFECTIVE_CAPABILITIES=NET_BIND_SERVICE_ONLY",
        ):
            self.assertIn(token, self.baseline)

    def test_rollback_uses_historical_proof_and_unified_compose(self) -> None:
        self.assertIn("rollback-baseline-bind-test.sh", self.verify)
        self.assertIn("deploy/compose.runtime.yaml", self.verify)
        self.assertIn("ROLLBACK_HISTORICAL_BIND=PASS", self.verify)
        self.assertIn("ROLLBACK_UNIFIED_COMPOSE_RENDER=PASS", self.verify)
        self.assertNotIn(
            '"$ROOT/tests/runtime-bind-test.sh" "$baseline_image"', self.verify
        )

    def test_pr_ci_is_package_free_and_protected_push_preserves_rollback_evidence(self) -> None:
        pr_jobs, rollback_and_aggregate = self.workflow.split(
            "  protected-rollback-gate:", 1
        )
        rollback_job, aggregate = rollback_and_aggregate.split("  validate:", 1)

        for forbidden in (
            "packages: read",
            "docker/login-action@",
            "verify-rollback-baseline.sh",
        ):
            self.assertNotIn(forbidden, pr_jobs)

        for token in (
            "name: immutable-release-gate",
            "CADDY_IMMUTABLE_PR_GATE=PASS",
            "PACKAGE_CREDENTIALS=NOT_GRANTED",
        ):
            self.assertIn(token, pr_jobs)

        for token in (
            "name: protected-rollback-gate",
            "if: github.event_name == 'push'",
            "packages: read",
            "Install Cosign for protected rollback verification",
            "Authenticate to GHCR for the exact rollback baseline",
            "scripts/verify-rollback-baseline.sh | tee rollback-baseline-ci.txt",
            "caddy-protected-rollback-${{ env.EXPECTED_SHA }}",
        ):
            self.assertIn(token, rollback_job)

        self.assertLess(
            rollback_job.index("Prove rollback credentials are bound to a protected branch push"),
            rollback_job.index("Authenticate to GHCR for the exact rollback baseline"),
        )
        self.assertIn('test "$ROLLBACK" = skipped', aggregate)
        self.assertIn("CADDY_PR_PACKAGE_CREDENTIALS=NOT_GRANTED", aggregate)
        self.assertIn('test "$ROLLBACK" = success', aggregate)
        self.assertIn("CADDY_PROTECTED_ROLLBACK=PASS", aggregate)


if __name__ == "__main__":
    unittest.main()
