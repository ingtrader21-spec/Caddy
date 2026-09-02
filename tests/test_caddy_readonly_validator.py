import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "caddy_readonly_validator.py"
SPEC = importlib.util.spec_from_file_location("caddy_readonly_validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(validator)


class ReadonlyValidatorTests(unittest.TestCase):
    def test_all_credential_redactions_are_required(self):
        source = "\n".join(validator.REQUIRED_REDACTIONS)
        validator.require_redaction(source)
        for token in validator.REQUIRED_REDACTIONS:
            with self.assertRaises(validator.ValidationError):
                validator.require_redaction(source.replace(token, ""))

    def test_summary_contains_structure_but_not_values(self):
        raw = {
            "host": "api.codestra.co",
            "path": "/v1/*",
            "dial": "kong:8000",
            "headers": {"Authorization": ["secret-value"]},
            "read_timeout": "30s",
            "client_authentication": {"trusted_ca_certs": ["secret-ca"]},
        }
        result = validator.sanitized_summary(raw)
        rendered = repr(result)
        self.assertIn("api.codestra.co", rendered)
        self.assertIn("kong:8000", rendered)
        self.assertIn("Authorization", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("secret-ca", rendered)
        self.assertTrue(result["mtls_policy_present"])

    def test_unsafe_upstream_is_rejected(self):
        for dial in ("user:password@host:443", "host:443?token=value", "https://host:443"):
            with self.assertRaises(validator.ValidationError):
                validator.sanitized_summary({"dial": dial})


if __name__ == "__main__":
    unittest.main()

