from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/caddy_manual_orchestrator.py"
WORKFLOW_PATH = ROOT / ".github/workflows/manual-production-orchestrator.yml"

spec = importlib.util.spec_from_file_location("caddy_manual_orchestrator", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SOURCE_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE = f"ghcr.io/appolon1908-hue/codestra-caddy@{IMAGE_DIGEST}"
CONFIG_SHA = "c" * 64


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def child_run(path: Path, workflow: str, run_id: int = 100) -> None:
    write_json(
        path,
        {
            "schema": "codestra.caddy.child-workflow-run.v1",
            "repository": "appolon1908-hue/Caddy",
            "workflow_path": workflow,
            "source_sha": SOURCE_SHA,
            "run_id": run_id,
            "run_attempt": 1,
            "status": "completed",
            "conclusion": "success",
            "head_branch": "production",
            "event": "push",
            "html_url": f"https://github.com/appolon1908-hue/Caddy/actions/runs/{run_id}",
            "policy": "reuse-success",
            "reused_success": True,
        },
    )


class RunSelectionTests(unittest.TestCase):
    def test_select_exact_run_rejects_wrong_branch_sha_event_and_path(self) -> None:
        good = {
            "id": 9,
            "run_attempt": 1,
            "path": ".github/workflows/immutable-release.yml",
            "head_sha": SOURCE_SHA,
            "head_branch": "production",
            "event": "push",
        }
        runs = [
            {**good, "id": 1, "head_branch": "main"},
            {**good, "id": 2, "head_sha": "d" * 40},
            {**good, "id": 3, "event": "workflow_dispatch"},
            {**good, "id": 4, "path": ".github/workflows/validate.yml"},
            good,
        ]
        selected = module.select_exact_run(
            runs, ".github/workflows/immutable-release.yml", SOURCE_SHA
        )
        self.assertEqual(selected["id"], 9)

    def test_only_existing_release_and_bounded_runtime_are_allowlisted(self) -> None:
        self.assertEqual(
            module.ALLOWED_WORKFLOWS,
            {
                ".github/workflows/immutable-release.yml",
                ".github/workflows/bounded-runtime-certification.yml",
            },
        )

    def test_adopted_run_timeout_is_not_cancelled(self) -> None:
        class FakeAPI:
            def __init__(self) -> None:
                self.cancelled = False

            def request(self, method: str, path: str, payload=None):
                if method == "POST" and path.endswith("/cancel"):
                    self.cancelled = True
                return {
                    "status": "queued",
                    "id": 5,
                    "run_attempt": 1,
                }

        fake = FakeAPI()
        with mock.patch.object(module.time, "monotonic", side_effect=[0.0, 10.0]), \
             mock.patch.object(module.time, "sleep", return_value=None):
            with self.assertRaises(module.OrchestrationError):
                module.wait_for_completion(
                    fake,
                    5,
                    deadline=5.0,
                    cancel_on_timeout=False,
                )
        self.assertFalse(fake.cancelled)


class EvidenceVerificationTests(unittest.TestCase):
    def test_release_evidence_binds_exact_source_digest_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "release"
            evidence.mkdir()
            values = {
                "SOURCE_SHA": SOURCE_SHA,
                "IMAGE_DIGEST": IMAGE_DIGEST,
                "CONFIG_SHA256": CONFIG_SHA,
                **{gate: "PASS" for gate in module.PASS_RELEASE_GATES},
            }
            (evidence / "caddy-release-evidence.txt").write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            (evidence / "config-sha256.txt").write_text(CONFIG_SHA + "\n")
            run = root / "run.json"
            child_run(run, ".github/workflows/immutable-release.yml")
            receipt = module.verify_release_evidence(
                directory=evidence,
                run_json=run,
                source_sha=SOURCE_SHA,
                output_path=root / "receipt.json",
            )
            self.assertEqual(receipt["image"], IMAGE)
            self.assertEqual(receipt["result"], "PASS")

    def test_release_evidence_rejects_failed_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "release"
            evidence.mkdir()
            values = {
                "SOURCE_SHA": SOURCE_SHA,
                "IMAGE_DIGEST": IMAGE_DIGEST,
                "CONFIG_SHA256": CONFIG_SHA,
                **{gate: "PASS" for gate in module.PASS_RELEASE_GATES},
            }
            values["SIGNATURE"] = "FAIL"
            (evidence / "caddy-release-evidence.txt").write_text(
                "".join(f"{key}={value}\n" for key, value in values.items()),
                encoding="utf-8",
            )
            (evidence / "config-sha256.txt").write_text(CONFIG_SHA + "\n")
            run = root / "run.json"
            child_run(run, ".github/workflows/immutable-release.yml")
            with self.assertRaises(module.OrchestrationError):
                module.verify_release_evidence(
                    directory=evidence,
                    run_json=run,
                    source_sha=SOURCE_SHA,
                    output_path=root / "receipt.json",
                )

    def test_runtime_evidence_binds_staging_to_unchanged_readonly_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging_dir = root / "staging"
            canary_dir = root / "canary"
            staging_dir.mkdir()
            canary_dir.mkdir()

            staging = {
                "schema": "codestra.caddy.bounded-staging-runtime.v2",
                "source_sha": SOURCE_SHA,
                "image": IMAGE,
                "config_sha256": CONFIG_SHA,
                "runtime_config_sha256": CONFIG_SHA,
                "module_set_sha256": "d" * 64,
                "isolated_network": True,
                "host_bindings_loopback_only": True,
                "nonroot_readonly_runtime": "PASS",
                "tcp_80_443_udp_443": "PASS",
                "http2_http3_websocket": "PASS",
                "certificate_expiry": "PASS",
                "redirects_hsts_limits": "PASS",
                "editor_openbao_denial": "PASS",
                "mtls_handshake_and_denial": "PASS",
                "sanitized_logs": "PASS",
                "candidate_removed": True,
                "public_traffic_changed": False,
                "dns_changed": False,
                "firewall_changed": False,
                "ssh_changed": False,
                "result": "PASS",
            }
            staging_path = staging_dir / "bounded-staging-runtime-evidence.json"
            write_json(staging_path, staging)

            runtime_snapshot = {
                "schema": "codestra.caddy-container-validation.v2",
                "source_sha": "e" * 40,
                "image_digest": "sha256:" + "f" * 64,
                "config_sha256": "0" * 64,
                "container_health": "healthy",
            }
            pre = canary_dir / "pre-canary-runtime.json"
            post = canary_dir / "post-canary-runtime.json"
            write_json(pre, runtime_snapshot)
            post.write_bytes(pre.read_bytes())
            snapshot_sha = hashlib.sha256(pre.read_bytes()).hexdigest()

            canary = {
                "schema": "codestra.caddy.production-readonly-canary.v2",
                "candidate_source_sha": SOURCE_SHA,
                "candidate_image": IMAGE,
                "candidate_config_sha256": CONFIG_SHA,
                "candidate_signature_and_attestation": "PASS",
                "bounded_staging_runtime": "PASS",
                "candidate_offline_config_validation": "PASS",
                "live_container_validation_before": "PASS",
                "live_container_validation_after": "PASS",
                "live_runtime_snapshot_before_sha256": snapshot_sha,
                "live_runtime_snapshot_after_sha256": snapshot_sha,
                "live_runtime_unchanged": True,
                "live_redirect_hsts_certificate": "PASS",
                "live_http2_http3_websocket": "PASS",
                "live_editor_openbao_denial": "PASS",
                "live_mtls_handshake_and_denial": "PASS",
                "write_requests_sent": False,
                "candidate_started_on_production": False,
                "public_traffic_changed": False,
                "dns_changed": False,
                "firewall_changed": False,
                "ssh_changed": False,
                "result": "PASS",
            }
            write_json(canary_dir / "production-canary-evidence.json", canary)
            staging_sha = hashlib.sha256(staging_path.read_bytes()).hexdigest()
            (canary_dir / "staging-evidence-identity.txt").write_text(
                f"STAGING_EVIDENCE_SHA256={staging_sha}\n", encoding="utf-8"
            )
            run = root / "run.json"
            child_run(run, ".github/workflows/bounded-runtime-certification.yml", 200)

            receipt = module.verify_runtime_evidence(
                staging_directory=staging_dir,
                canary_directory=canary_dir,
                run_json=run,
                source_sha=SOURCE_SHA,
                image=IMAGE,
                config_sha256=CONFIG_SHA,
                output_path=root / "receipt.json",
            )
            self.assertEqual(receipt["result"], "PASS")
            self.assertTrue(receipt["live_runtime_unchanged"])

            post.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(module.OrchestrationError):
                module.verify_runtime_evidence(
                    staging_directory=staging_dir,
                    canary_directory=canary_dir,
                    run_json=run,
                    source_sha=SOURCE_SHA,
                    image=IMAGE,
                    config_sha256=CONFIG_SHA,
                    output_path=root / "tampered.json",
                )


class WorkflowSourceTests(unittest.TestCase):
    def test_manual_workflow_preserves_existing_protected_authorities(self) -> None:
        source = WORKFLOW_PATH.read_text(encoding="utf-8")
        for token in (
            "workflow_dispatch:",
            "actions: write",
            "test \"$GITHUB_REF\" = refs/heads/main",
            "branches/main",
            "branches/production",
            "working-directory: candidate",
            "run: bash scripts/validate-ci.sh",
            "candidate/deploy/compose.runtime.yaml",
            ".github/workflows/immutable-release.yml",
            ".github/workflows/bounded-runtime-certification.yml",
            "caddy-release-evidence-$SOURCE_SHA",
            "caddy-bounded-staging-runtime-$SOURCE_SHA",
            "caddy-production-readonly-canary-$SOURCE_SHA",
            "production-orchestration-verdict",
            "result=NO_GO",
            "protected_environments_preserved",
            "direct_production_runtime_mutation",
        ):
            self.assertIn(token, source)
        for forbidden in (
            "docker compose up",
            "run-immutable-runtime.sh",
            "rollback-runtime.sh",
            "update-ref",
            "--force",
            "environment: production-activation",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
