from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CertificationEvidenceFailClosedTests(unittest.TestCase):
    def test_rollback_validation_has_nonroot_writable_sandbox(self):
        script = (ROOT / "scripts/verify-rollback-baseline.sh").read_text()
        for token in (
            "--network none",
            "--env XDG_DATA_HOME=/data --env XDG_CONFIG_HOME=/config",
            "--tmpfs /run/caddy:uid=65532,gid=65532,mode=0700",
            "--tmpfs /var/log/caddy:uid=65532,gid=65532,mode=0700",
            "--tmpfs /data:uid=65532,gid=65532,mode=0700",
            "--tmpfs /config:uid=65532,gid=65532,mode=0700",
            "CADDY_ROLLBACK_REHEARSAL=PASS",
        ):
            self.assertIn(token, script)

    def test_redaction_gate_rejects_missing_unreadable_or_failed_searches(self):
        script = (ROOT / "tests/runtime-canary-test.sh").read_text()
        for token in (
            "CADDY_CANARY_LOGS=FAIL:no_access_logs",
            "CADDY_CANARY_LOGS=FAIL:read_access_logs",
            "CADDY_CANARY_LOGS=FAIL:unreadable_access_log",
            "sudo -n chown -R",
            "grep -R -F --quiet",
            "grep_status=$?",
            'case "$grep_status" in',
            "CADDY_CANARY_LOGS=FAIL:grep_error",
        ):
            self.assertIn(token, script)
        self.assertNotIn('! grep -R -F "$secret"', script)

    def test_bounded_staging_redaction_rejects_log_read_errors(self):
        script = (ROOT / "scripts/bounded-staging-runtime-v2.sh").read_text()
        for token in (
            "BOUNDED_STAGING_LOGS=FAIL:no_access_logs",
            "BOUNDED_STAGING_LOGS=FAIL:read_access_logs",
            "BOUNDED_STAGING_LOGS=FAIL:unreadable_access_log",
            "BOUNDED_STAGING_LOGS=FAIL:grep_error",
            "grep -R -F --quiet",
            "grep_status=$?",
            'case "$grep_status" in',
        ):
            self.assertIn(token, script)
        self.assertNotIn('! grep -R -F "$secret"', script)


if __name__ == "__main__":
    unittest.main()
