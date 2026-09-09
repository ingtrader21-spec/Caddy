from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "config/sites/staging-internal.caddy"
CONTRACT = ROOT / "config/caddy-kong-contract.v2.json"
BOUNDED = ROOT / "scripts/bounded-staging-runtime-v2.sh"
CERTIFIER = ROOT / "scripts/certify_caddy_kong_middleware_runtime.py"
CA_VERIFIER = ROOT / "scripts/verify_staging_ca_anchor.py"
MANUAL = ROOT / "scripts/manual-staging-certify.sh"


class StagingGatewayCertificationTests(unittest.TestCase):
    def test_staging_hosts_enumerate_reviewed_kong_families_and_fail_closed(self) -> None:
        source = STAGING.read_text(encoding="utf-8")
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        for prefix in contract["kongManagedPathPrefixes"]:
            self.assertEqual(source.count(prefix + "*"), 2, prefix)
        self.assertEqual(source.count("reverse_proxy {$CADDY_STAGING_KONG_UPSTREAM}"), 2)
        self.assertEqual(source.count('respond "Not Found" 404'), 2)
        self.assertIn("@private_callback path /api/v1/events/vicidial", source)
        self.assertIn("respond @private_callback 404", source)
        self.assertNotIn("reverse_proxy {$CADDY_KONG_UPSTREAM}", source)

    def test_runtime_identity_proof_has_bounded_staging_edge(self) -> None:
        spec = importlib.util.spec_from_file_location("certifier", CERTIFIER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.ALLOWED_ROUTE_HOSTS["bridge-staging.codestra.agency"], "staging")
        self.assertEqual(module.ALLOWED_ROUTE_HOSTS["api.codestra.co"], "canonical")
        source = CERTIFIER.read_text(encoding="utf-8")
        self.assertIn('CADDY_PROOF_API_HOST', source)
        self.assertIn('"edge_host": route_host', source)
        self.assertIn('"gateway_environment": gateway_environment', source)

    def test_bounded_runner_uses_external_ca_and_staging_identity_proof(self) -> None:
        source = BOUNDED.read_text(encoding="utf-8")
        self.assertIn('$DATA_SOURCE/caddy/pki/authorities/local/root.crt', source)
        self.assertIn('verify_staging_ca_anchor.py" "$expected_staging_ca" "$candidate_staging_ca"', source)
        self.assertIn('--cacert "$expected_staging_ca"', source)
        self.assertNotIn('--cacert "$candidate_staging_ca"', source)
        self.assertIn('CADDY_PROOF_API_HOST=bridge-staging.codestra.agency', source)
        self.assertIn('"staging_gateway_identity": "PASS"', source)
        self.assertIn('"staging_ca_anchor": "PASS"', source)

    def _certificate(self, directory: Path, name: str) -> Path:
        cert = directory / f"{name}.crt"
        key = directory / f"{name}.key"
        subprocess.run(
            [
                "/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "1", "-subj", f"/CN={name}", "-keyout", str(key), "-out", str(cert),
            ],
            check=True,
            capture_output=True,
        )
        return cert

    def test_ca_verifier_accepts_established_identity_and_rejects_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            expected = self._certificate(directory, "established-staging-ca")
            regenerated = self._certificate(directory, "regenerated-candidate-ca")
            same = subprocess.run(
                ["python3", str(CA_VERIFIER), str(expected), str(expected)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(same.returncode, 0, same.stderr)
            self.assertIn("STAGING_CA_ANCHOR=PASS", same.stdout)
            mismatch = subprocess.run(
                ["python3", str(CA_VERIFIER), str(expected), str(regenerated)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(mismatch.returncode, 2)
            self.assertIn("ca_identity_mismatch", mismatch.stderr)

    def test_ca_verifier_rejects_symlink_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            expected = self._certificate(directory, "established-staging-ca")
            link = directory / "linked.crt"
            link.symlink_to(expected)
            result = subprocess.run(
                ["python3", str(CA_VERIFIER), str(link), str(expected)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("expected_ca_not_regular", result.stderr)

    def test_manual_staging_packet_requires_staging_edge_identity(self) -> None:
        source = MANUAL.read_text(encoding="utf-8")
        self.assertIn('value["route"]["caddy_to_kong_to_middleware"] == "PASS"', source)


if __name__ == "__main__":
    unittest.main()
