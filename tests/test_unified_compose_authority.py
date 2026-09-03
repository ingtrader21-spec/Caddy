from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UnifiedComposeAuthorityTests(unittest.TestCase):
    def test_single_caddy_compose_authority(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validate_unified_compose.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("CADDY_UNIFIED_COMPOSE=PASS", result.stdout)
        self.assertIn("CADDY_COMPOSE_RUNTIME_OWNERS=1", result.stdout)

    def test_exact_and_merge_result_ci_execute_the_gate(self) -> None:
        validation = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        ci = (ROOT / "scripts/validate-ci.sh").read_text(encoding="utf-8")
        self.assertIn("validate-source:", validation)
        self.assertIn("validate-merge-result:", validation)
        self.assertGreaterEqual(validation.count("scripts/validate-ci.sh"), 2)
        self.assertIn("python3 -m unittest discover", ci)
        self.assertIn("docker compose -f deploy/compose.runtime.yaml config --quiet", ci)


if __name__ == "__main__":
    unittest.main()
