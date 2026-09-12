import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class KyyowIngressTests(unittest.TestCase):
    def test_contract_has_exact_public_host_family(self):
        contract = json.loads((ROOT / "config/kyyow-ingress.v1.json").read_text())
        self.assertEqual(set(contract["publicHosts"]), {
            "app.kyyow.com", "api.kyyow.com", "search.kyyow.com",
            "docs.kyyow.com", "auth.kyyow.com", "status.kyyow.com"
        })

    def test_validator_passes(self):
        result = subprocess.run(
            ["python3", "scripts/validate_kyyow_ingress.py"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("KYYOW_INGRESS_CONTRACT=PASS", result.stdout)

if __name__ == "__main__":
    unittest.main()
