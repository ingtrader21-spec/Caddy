from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundedRuntimePrivateRefReadbackTests(unittest.TestCase):
    def test_private_runtime_jobs_refresh_authority_without_post_checkout_fetch(self):
        workflow = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()

        self.assertGreaterEqual(workflow.count("fetch-depth: 0"), 4)
        self.assertGreaterEqual(workflow.count("persist-credentials: false"), 4)
        self.assertNotIn("git fetch origin production", workflow)
        self.assertGreaterEqual(
            workflow.count(
                "git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null"
            ),
            4,
        )
        self.assertGreaterEqual(
            workflow.count("rev-parse origin/production"),
            4,
        )

        staging_refresh = (
            "name: Refresh protected production authority immediately before bounded staging use"
        )
        staging_use = (
            "name: Deploy and certify exact digest on the bounded staging runtime"
        )
        canary_refresh = (
            "name: Refresh protected production authority immediately before canary use"
        )
        canary_use = "name: Run bounded production read-only canary"

        for token in (
            staging_refresh,
            "path: .production-authority-staging",
            "CADDY_PRODUCTION_AUTHORITY_AT_STAGING_USE=PASS",
            canary_refresh,
            "path: .production-authority-canary",
            "CADDY_PRODUCTION_AUTHORITY_AT_CANARY_USE=PASS",
        ):
            self.assertIn(token, workflow)

        self.assertLess(workflow.index(staging_refresh), workflow.index(staging_use))
        self.assertLess(workflow.index(canary_refresh), workflow.index(canary_use))
        self.assertEqual(workflow.count('rm -rf -- "$authority"'), 2)


if __name__ == "__main__":
    unittest.main()
