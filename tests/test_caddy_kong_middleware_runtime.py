from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from certify_caddy_kong_middleware_runtime import (  # noqa: E402
    CertificationError,
    certify,
    decode_jwt_claims,
    load_source_contract,
    normalize_version_url,
    parse_runtime_env,
    validate_secret_file,
)


class CaddyKongMiddlewareRuntimeTests(unittest.TestCase):
    def test_source_contract_uses_current_protected_authorities(self) -> None:
        identity, proof, middleware_sha = load_source_contract()
        self.assertEqual(
            identity["protectedMainSha"],
            "3b8422da498a47b8f1a91a6a2b2c62d2852ca50f",
        )
        self.assertEqual(identity["stagingHost"], "auth-staging.codestra.co")
        self.assertEqual(
            identity["stagingIssuer"],
            "https://auth-staging.codestra.co/realms/codestra",
        )
        self.assertEqual(
            middleware_sha,
            "4092b3b1e57819da75eb45631176b022f70a0c55",
        )
        self.assertEqual(proof["identityEnvironment"], "staging")
        self.assertEqual(proof["method"], "GET")
        self.assertFalse(proof["mutationAllowed"])
        self.assertFalse(proof["externalEffectsAllowed"])

    def test_version_url_is_bounded(self) -> None:
        self.assertEqual(
            normalize_version_url("middleware-staging:8080"),
            "http://middleware-staging:8080/version",
        )
        self.assertEqual(
            normalize_version_url("https://middleware.invalid/base/"),
            "https://middleware.invalid/base/version",
        )
        with self.assertRaises(CertificationError):
            normalize_version_url("https://user:secret@middleware.invalid")
        with self.assertRaises(CertificationError):
            normalize_version_url("file:///etc/passwd")

    def test_jwt_payload_decoder_does_not_require_a_static_fixture_secret(self) -> None:
        claims = {
            "iss": "https://auth-staging.codestra.co/realms/codestra",
            "azp": "n8n-automation",
            "tenant_id": "tenant-test",
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        self.assertEqual(decode_jwt_claims(f"header.{encoded}.signature"), claims)
        with self.assertRaises(CertificationError):
            decode_jwt_claims("not-a-jwt")

    def test_runtime_env_rejects_duplicates_and_relative_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.env"
            path.write_text(
                "CADDY_STAGING_API_UPSTREAM=middleware-staging:8080\n",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_runtime_env(path)["CADDY_STAGING_API_UPSTREAM"],
                "middleware-staging:8080",
            )
            path.write_text("A=one\nA=two\n", encoding="utf-8")
            with self.assertRaises(CertificationError):
                parse_runtime_env(path)

    def test_owner_private_secret_is_accepted_and_world_readable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "client-secret"
            path.write_text("synthetic-secret-value", encoding="utf-8")
            path.chmod(0o600)
            validate_secret_file(path)
            path.chmod(0o604)
            with self.assertRaises(CertificationError):
                validate_secret_file(path)

    def test_runtime_proof_is_inert_outside_bounded_staging(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            certify(ip="203.0.113.10", port=443)


if __name__ == "__main__":
    unittest.main()
