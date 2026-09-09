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

        self.assertGreaterEqual(workflow.count("fetch-depth: 0"), 4)
        self.assertGreaterEqual(workflow.count("persist-credentials: false"), 4)

        for path in scripts:
            text = path.read_text()
            self.assertNotIn("git fetch origin production", text, path.name)
            self.assertIn(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null",
                text,
                path.name,
            )
            self.assertIn(
                "git rev-parse origin/production",
                text,
                path.name,
            )

    def test_automatic_and_manual_runtime_paths_share_the_same_fail_closed_model(self):
        automatic = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()
        self.assertNotIn("git fetch origin production", automatic)
        self.assertEqual(
            automatic.count(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null"
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
