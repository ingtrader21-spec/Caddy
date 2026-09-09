from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ManualRuntimePrivateRefReadbackTests(unittest.TestCase):
    def test_manual_release_path_never_refetches_after_credential_free_checkout(self):
        workflow = (ROOT / ".github/workflows/manual-production-orchestrator.yml").read_text()
        scripts = [
            ROOT / "scripts/manual-production-preflight.sh",
            ROOT / "scripts/manual-staging-certify.sh",
            ROOT / "scripts/manual-production-readonly-canary.sh",
        ]

        self.assertGreaterEqual(workflow.count("fetch-depth: 0"), 8)
        self.assertGreaterEqual(workflow.count("persist-credentials: false"), 8)
        self.assertGreaterEqual(workflow.count("clean: false"), 4)

        for path in scripts:
            text = path.read_text()
            self.assertNotIn("git fetch origin production", text, path.name)
            self.assertIn(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null",
                text,
                path.name,
            )
            self.assertIn("git rev-parse origin/production", text, path.name)

    def test_manual_release_refreshes_live_production_immediately_before_use(self):
        workflow = (ROOT / ".github/workflows/manual-production-orchestrator.yml").read_text()
        ordered_pairs = (
            (
                "name: Refresh current production authority immediately before preflight",
                "name: Verify branch governance, protected environments, source, signed digest, labels, attestation, and release identity",
            ),
            (
                "name: Refresh current production authority immediately before bounded staging use",
                "name: Deploy exact digest, certify bounded staging, and prove rollback",
            ),
            (
                "name: Refresh current production authority immediately before read-only canary use",
                "name: Verify all evidence and execute the read-only production canary",
            ),
            (
                "name: Refresh current production authority immediately before activation use",
                "name: Capture the live baseline and activate the exact signed digest",
            ),
        )
        for refresh, use in ordered_pairs:
            self.assertIn(refresh, workflow)
            self.assertIn(use, workflow)
            self.assertLess(workflow.index(refresh), workflow.index(use))

        self.assertGreaterEqual(workflow.count("ref: production"), 5)
        for token in (
            "CADDY_PRODUCTION_AUTHORITY_AT_PREFLIGHT_USE=PASS",
            "CADDY_PRODUCTION_AUTHORITY_AT_MANUAL_STAGING_USE=PASS",
            "CADDY_PRODUCTION_AUTHORITY_AT_MANUAL_CANARY_USE=PASS",
            "CADDY_PRODUCTION_AUTHORITY_AT_ACTIVATION_USE=PASS",
            "git status --porcelain --untracked-files=no",
        ):
            self.assertIn(token, workflow)

    def test_automatic_and_manual_runtime_paths_share_the_same_fail_closed_model(self):
        automatic = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()
        self.assertNotIn("git fetch origin production", automatic)
        self.assertGreaterEqual(
            automatic.count(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null"
            ),
            4,
        )
        for token in (
            "Refresh protected production authority immediately before bounded staging use",
            "Refresh protected production authority immediately before canary use",
        ):
            self.assertIn(token, automatic)


if __name__ == "__main__":
    unittest.main()
