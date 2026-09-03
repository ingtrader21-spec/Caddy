from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseRemediationTests(unittest.TestCase):
    def test_single_deployable_tree_and_closed_api_fallback(self):
        self.assertFalse((ROOT / "candidate").exists())
        self.assertFalse((ROOT / "config/sites/current-production.caddy").exists())
        for source in (
            (ROOT / "config/sites/api.codestra.co.caddy").read_text(),
            (ROOT / "config/sites/legacy-api.codestra.agency.caddy").read_text(),
        ):
            self.assertIn("{$CADDY_KONG_UPSTREAM}", source)
            self.assertIn('respond "Not Found" 404', source)
            self.assertNotIn("CADDY_LEGACY_API_UPSTREAM", source)
            self.assertNotIn("127.0.0.1:18101", source)

    def test_every_access_log_uses_complete_shared_redactor(self):
        for directory in (ROOT / "config/sites", ROOT / "config/conf.d"):
            for path in directory.glob("*.caddy"):
                source = path.read_text()
                if "log {" in source:
                    self.assertIn("import sanitized_access_log", source, str(path))
        redactor = (ROOT / "config/snippets/logging.caddy").read_text()
        for token in (
            "request>headers>Authorization delete",
            "request>headers>Proxy-Authorization delete",
            "request>headers>Cookie delete",
            "request>headers>Apikey delete",
            "request>headers>X-Api-Key delete",
            "request>headers>X-Auth-Request-Access-Token delete",
            "delete api-key",
            "delete api_key",
            "delete apikey",
            "delete client_secret",
            "delete code",
            "delete id_token",
            "delete refresh_token",
            "delete session_state",
            "delete state",
            "resp_headers>Set-Cookie delete",
            "resp_headers>X-Auth-Request-Access-Token delete",
        ):
            self.assertIn(token, redactor)

    def test_container_runtime_is_digest_pinned_and_nonroot(self):
        compose = (ROOT / "deploy/compose.runtime.yaml").read_text()
        for token in (
            "container_name: codestra-caddy",
            "@sha256:${CADDY_IMAGE_SHA256:",
            'user: "65532:65532"',
            "read_only: true",
            "cap_drop:\n      - ALL",
            "cap_add:\n      - NET_BIND_SERVICE",
            "no-new-privileges:true",
            "network_mode: host",
        ):
            self.assertIn(token, compose)
        self.assertNotIn("ports:", compose)
        self.assertNotIn("latest", compose)

    def test_runtime_validator_targets_actual_container_and_process(self):
        validator = (ROOT / "scripts/caddy_readonly_validator.py").read_text()
        for token in (
            'CONTAINER = "codestra-caddy"',
            '[DOCKER, "inspect", CONTAINER]',
            '[DOCKER, "image", "inspect", image_reference]',
            '[DOCKER, "exec", CONTAINER',
            '[DOCKER, "cp"',
            '[DOCKER, "top", CONTAINER',
            "org.opencontainers.image.revision",
            "io.codestra.caddy.config.sha256",
            "list-modules",
            "caddy_host_pid",
            "listener_ownership",
            'require_listener(sockets, "udp", public_bind, 443, runtime_pid)',
            'require_listener(sockets, "tcp", metrics_bind, 2020, runtime_pid)',
        ):
            self.assertIn(token, validator)
        self.assertNotIn("systemctl", validator)
        self.assertNotIn("caddy.service", validator)

    def test_release_and_rollback_are_immutable(self):
        release = (ROOT / ".github/workflows/immutable-release.yml").read_text()
        for token in (
            "branches: [production]",
            "scripts/build-release-inputs.sh",
            "tests/runtime-canary-test.sh",
            "cosign sign --yes",
            "cosign attest --yes",
            "sbom: true",
            "provenance: mode=max",
        ):
            self.assertIn(token, release)
        baseline = json.loads((ROOT / "config/release-baseline.v1.json").read_text())
        self.assertFalse(baseline["mutable"])
        self.assertTrue(
            baseline["image"].startswith(
                "ghcr.io/appolon1908-hue/codestra-caddy@sha256:"
            )
        )
        rollback = (ROOT / "scripts/rollback-runtime.sh").read_text()
        self.assertIn('"$COSIGN_BIN" verify', rollback)
        self.assertIn("up -d --pull never --no-build", rollback)
        self.assertIn("hash_config_tree.py", rollback)
        baseline_check = (ROOT / "scripts/verify-rollback-baseline.sh").read_text()
        self.assertIn("CADDY_ROLLBACK_BASELINE=PASS", baseline_check)
        self.assertIn("runtime-bind-test.sh", baseline_check)

    def test_promotion_rules_have_no_bypass(self):
        ruleset = json.loads(
            (ROOT / "config/github/protected-branches-ruleset.json").read_text()
        )
        self.assertEqual(ruleset["bypass_actors"], [])
        checks = next(
            rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
        )
        self.assertEqual(
            {item["context"] for item in checks["parameters"]["required_status_checks"]},
            {
                "validate-source",
                "validate-merge-result",
                "promotion-guard",
                "immutable-release-gate",
            },
        )


if __name__ == "__main__":
    unittest.main()
