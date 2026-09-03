from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundedWorkflowSafetyTests(unittest.TestCase):
    def test_production_job_is_strictly_downstream_of_staging(self):
        workflow = (
            ROOT / ".github/workflows/bounded-runtime-certification.yml"
        ).read_text()
        production = workflow.split("  production-readonly-canary:", 1)[1]
        self.assertIn("needs: bounded-staging-runtime", production)
        self.assertIn("CADDY_CANARY_IMAGE: ${{ needs.bounded-staging-runtime.outputs.image }}", production)
        self.assertIn("CADDY_CANARY_SOURCE_SHA: ${{ needs.bounded-staging-runtime.outputs.source_sha }}", production)
        self.assertIn("CADDY_CANARY_CONFIG_SHA256: ${{ needs.bounded-staging-runtime.outputs.config_sha256 }}", production)

    def test_production_script_has_no_runtime_replacement_verb(self):
        script = (
            ROOT / "scripts/bounded-production-readonly-canary-v2.sh"
        ).read_text()
        forbidden_patterns = (
            r"docker(?:_cmd)?\s+(?:compose\s+)?up\b",
            r"docker(?:_cmd)?\s+run\s+-d\b",
            r"docker(?:_cmd)?\s+(?:stop|restart|kill|rm)\b",
            r"systemctl\s+(?:start|stop|restart|reload)\b",
        )
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, script), pattern)
        self.assertIn("cmp -s", script)

    def test_staging_script_uses_no_host_network(self):
        script = (ROOT / "scripts/bounded-staging-runtime-v2.sh").read_text()
        self.assertNotIn("--network host", script)
        self.assertIn("docker_cmd network create --driver bridge", script)
        self.assertGreaterEqual(script.count("-p 127.0.0.1:"), 5)


if __name__ == "__main__":
    unittest.main()
