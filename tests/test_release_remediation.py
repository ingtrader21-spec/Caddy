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
            "effective_access_log_redaction",
            'require_listener(sockets, "udp", public_bind, 443, runtime_pid)',
            'require_listener(sockets, "tcp", metrics_bind, 2020, runtime_pid)',
        ):
            self.assertIn(token, validator)
        self.assertNotIn("systemctl", validator)
        self.assertNotIn("caddy.service", validator)

    def test_release_is_manual_reusable_and_immutable(self):
        release = (ROOT / ".github/workflows/immutable-release.yml").read_text()
        trigger = release.split("\npermissions:", 1)[0]
        self.assertIn("workflow_call:", trigger)
        self.assertNotIn("\n  push:", trigger)
        for token in (
            "source_sha:",
            "Reject every source except the current protected production head",
            "scripts/build-release-inputs.sh",
            "tests/runtime-canary-test.sh",
            "cosign sign --yes",
            "cosign attest --yes",
            "sbom: true",
            "provenance: mode=max",
            "release_evidence_sha256",
            "rollback_evidence_sha256",
        ):
            self.assertIn(token, release)

    def test_static_and_captured_rollback_baselines_are_immutable(self):
        baseline = json.loads((ROOT / "config/release-baseline.v1.json").read_text())
        self.assertFalse(baseline["mutable"])
        self.assertTrue(
            baseline["image"].startswith(
                "ghcr.io/appolon1908-hue/codestra-caddy@sha256:"
            )
        )
        capture = (ROOT / "scripts/capture-runtime-baseline.sh").read_text()
        for token in (
            "codestra.caddy-runtime-rollback-baseline.v1",
            "CADDY_ROLLBACK_BASELINE_FILE",
            "signature_verified",
            "listener_ownership",
            "effective_access_log_redaction",
            "install -m 0600 -o root -g root",
            "CADDY_BASELINE_CAPTURE=PASS",
        ):
            self.assertIn(token, capture)
        rollback = (ROOT / "scripts/rollback-runtime.sh").read_text()
        for token in (
            "CADDY_ROLLBACK_BASELINE_FILE",
            "codestra.caddy-release-baseline.v1",
            "codestra.caddy-runtime-rollback-baseline.v1",
            '"$COSIGN_BIN" verify',
            "up -d --pull never --no-build",
            "hash_config_tree.py",
            "production-canary.sh",
        ):
            self.assertIn(token, rollback)
        baseline_check = (ROOT / "scripts/verify-rollback-baseline.sh").read_text()
        self.assertIn("CADDY_ROLLBACK_BASELINE=PASS", baseline_check)
        self.assertIn("runtime-bind-test.sh", baseline_check)

    def test_activation_requires_captured_baseline_and_exact_digest(self):
        activation = (ROOT / "scripts/run-immutable-runtime.sh").read_text()
        for token in (
            "CADDY_ROLLBACK_BASELINE_FILE",
            "rollback_baseline_required",
            "rollback-runtime.sh",
            "automatic_rollback",
            "final_identity_readback",
            "CADDY_ACTIVATION=PASS",
        ):
            self.assertIn(token, activation)
        self.assertNotIn("latest", activation)
        self.assertNotIn("--build", activation)

    def test_promotion_rules_have_no_bypass_and_replace_legacy_policies(self):
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
        apply_workflow = (ROOT / ".github/workflows/apply-branch-ruleset.yml").read_text()
        for token in (
            "CODESTRA_REPOSITORY_ADMIN_TOKEN",
            "Protect Caddy promotion branches",
            "AI automated production gates",
            "Protect main",
            "required_approving_review_count",
            "allowed_merge_methods",
            "--method DELETE",
            "CADDY_BRANCH_RULESET_APPLIED=PASS",
            "CADDY_LEGACY_MAIN_RULESETS_RETIRED=PASS",
        ):
            self.assertIn(token, apply_workflow)


if __name__ == "__main__":
    unittest.main()
