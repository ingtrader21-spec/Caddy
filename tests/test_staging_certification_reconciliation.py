from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StagingCertificationReconciliationTests(unittest.TestCase):
    def test_production_pr_accepts_only_canonical_direct_or_governed_staging_source(self) -> None:
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        for token in (
            "github.event.pull_request.head.repo.full_name == github.repository",
            "HEAD_REPO: ${{ github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name || '' }}",
            "BASE_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || '' }}",
            'test "$HEAD_REPO" = "$GITHUB_REPOSITORY"',
            'test "$BASE_REF" = production',
            '[[ "$HEAD_REF" == staging ]]',
            "^reconcile/staging-to-production-[0-9]{8}",
            "CADDY_STAGING_INVOCATION=FAIL:invalid_production_source",
        ):
            self.assertIn(token, workflow)

    def test_reconciliation_is_revalidated_after_full_depth_credential_free_checkout(self) -> None:
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        checkout = "name: Check out exact staging source"
        route_proof = "name: Prove exact source and governed promotion identity"
        validate_source = "name: Validate the sole source and configuration authority"

        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("bash scripts/validate-promotion-route.sh", workflow)
        self.assertIn('BASE_BRANCH="$BASE_REF"', workflow)
        self.assertIn('HEAD_BRANCH="$HEAD_REF"', workflow)
        self.assertIn('HEAD_SHA="$SOURCE_SHA"', workflow)
        self.assertIn('BASE_SHA="$BASE_SHA"', workflow)
        self.assertLess(workflow.index(checkout), workflow.index(route_proof))
        self.assertLess(workflow.index(route_proof), workflow.index(validate_source))

    def test_isolated_pr_ci_has_no_package_or_runtime_environment_credentials(self) -> None:
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        source_part, rollback_and_gate = workflow.split("  rollback_certification:", 1)
        rollback_part, gate_part = rollback_and_gate.split("  certification_gate:", 1)
        bounded_runtime = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text()

        self.assertNotIn("environment: staging-readonly", workflow)
        self.assertNotIn("${{ vars.", source_part)
        self.assertIn("runs-on: ubuntu-24.04", source_part)
        self.assertIn("contents: read", source_part)
        self.assertNotIn("packages: read", source_part)
        self.assertNotIn("docker/login-action@", source_part)
        self.assertNotIn("verify-rollback-baseline.sh", source_part)

        self.assertIn("packages: read", rollback_part)
        self.assertIn("github.event_name == 'push' && github.ref == 'refs/heads/staging'", rollback_part)
        self.assertIn("docker/login-action@", rollback_part)
        self.assertIn("scripts/verify-rollback-baseline.sh", rollback_part)
        self.assertIn("CADDY_PRODUCTION_PR_PACKAGE_CREDENTIALS=NOT_GRANTED", gate_part)

        self.assertIn("runs-on: [self-hosted, codestra-staging]", bounded_runtime)
        self.assertIn("environment: staging-readonly", bounded_runtime)

    def test_documentation_distinguishes_source_ci_rollback_and_protected_runtime(self) -> None:
        docs = (ROOT / "docs/PRODUCTION-CERTIFICATION.md").read_text()

        self.assertIn(
            "source-certification job intentionally does **not** request the protected `staging-readonly` environment",
            docs,
        )
        self.assertIn("has only `contents: read` repository permission", docs)
        self.assertIn("It never authenticates to GHCR", docs)
        self.assertIn("Rollback rehearsal is a separate job", docs)
        self.assertIn("runs **only** for a push to the protected `staging` branch", docs)
        self.assertIn("Only that protected-push job receives `packages: read`", docs)
        self.assertIn(
            "Protected `staging-readonly` admission is reserved for the later self-hosted bounded staging runtime",
            docs,
        )
        self.assertIn("`codestra-staging` self-hosted runner", docs)
        self.assertIn("protected `production-readonly-canary` environment", docs)
        self.assertNotIn(
            "run `.github/workflows/staging-certification.yml` in the protected `staging-readonly` environment",
            docs,
        )


if __name__ == "__main__":
    unittest.main()
