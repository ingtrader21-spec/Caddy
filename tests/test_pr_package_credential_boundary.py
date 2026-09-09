from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PullRequestPackageCredentialBoundaryTests(unittest.TestCase):
    def test_required_pr_checks_never_receive_package_credentials(self) -> None:
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        pr_jobs, rollback_and_aggregate = workflow.split("  protected-rollback-gate:", 1)
        rollback_job, aggregate = rollback_and_aggregate.split("  validate:", 1)

        for token in (
            "name: validate-source",
            "name: validate-merge-result",
            "name: promotion-guard",
            "name: immutable-release-gate",
            "permissions:\n      contents: read",
            "CADDY_IMMUTABLE_PR_GATE=PASS",
            "PACKAGE_CREDENTIALS=NOT_GRANTED",
        ):
            self.assertIn(token, pr_jobs)

        for forbidden in (
            "packages: read",
            "docker/login-action@",
            "verify-rollback-baseline.sh",
        ):
            self.assertNotIn(forbidden, pr_jobs)

        for token in (
            "name: protected-rollback-gate",
            "if: github.event_name == 'push'",
            "packages: read",
            "docker/login-action@",
            "scripts/verify-rollback-baseline.sh",
            "development|test|staging|production|main",
        ):
            self.assertIn(token, rollback_job)

        self.assertIn('test "$ROLLBACK" = skipped', aggregate)
        self.assertIn("CADDY_PR_PACKAGE_CREDENTIALS=NOT_GRANTED", aggregate)
        self.assertIn('test "$ROLLBACK" = success', aggregate)
        self.assertIn("CADDY_PROTECTED_ROLLBACK=PASS", aggregate)

    def test_production_pr_staging_certification_is_package_free(self) -> None:
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        source_job, rollback_and_gate = workflow.split("  rollback_certification:", 1)
        rollback_job, gate = rollback_and_gate.split("  certification_gate:", 1)

        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            source_job,
        )
        self.assertIn('test "$HEAD_REPO" = "$GITHUB_REPOSITORY"', source_job)
        for forbidden in (
            "packages: read",
            "docker/login-action@",
            "verify-rollback-baseline.sh",
        ):
            self.assertNotIn(forbidden, source_job)

        self.assertIn(
            "github.event_name == 'push' && github.ref == 'refs/heads/staging'",
            rollback_job,
        )
        self.assertIn("packages: read", rollback_job)
        self.assertIn("docker/login-action@", rollback_job)
        self.assertIn("scripts/verify-rollback-baseline.sh", rollback_job)
        self.assertIn("CADDY_PRODUCTION_PR_PACKAGE_CREDENTIALS=NOT_GRANTED", gate)

    def test_documentation_matches_the_required_pr_credential_boundary(self) -> None:
        docs = (ROOT / "docs/PRODUCTION-CERTIFICATION.md").read_text()
        for token in (
            "## Required PR validation credential boundary",
            "every pull-request job credential-light",
            "only `contents: read`",
            "never receive `packages: read`",
            "separate `protected-rollback-gate`",
            "runs only for pushes to one of the five protected promotion branches",
            "## Protected staging rollback certification",
            "Only that protected-push job receives `packages: read`",
        ):
            self.assertIn(token, docs)


if __name__ == "__main__":
    unittest.main()
