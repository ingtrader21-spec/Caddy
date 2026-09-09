from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundedRuntimePrivateRefReadbackTests(unittest.TestCase):
    def test_private_runtime_jobs_use_checkout_refs_without_post_checkout_fetch(self):
        workflow = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()

        self.assertGreaterEqual(workflow.count("fetch-depth: 0"), 2)
        self.assertGreaterEqual(workflow.count("persist-credentials: false"), 2)
        self.assertNotIn("git fetch origin production", workflow)
        self.assertEqual(
            workflow.count(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null"
            ),
            2,
        )
        self.assertEqual(
            workflow.count('test "$(git rev-parse origin/production)" ='),
            2,
        )


if __name__ == "__main__":
    unittest.main()
