from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StagingCertificationReconciliationTests(unittest.TestCase):
    def test_production_pr_accepts_only_direct_or_governed_staging_source(self) -> None:
        workflow = (ROOT / ".github/workflows/staging-certification.yml").read_text()
        for token in (
            "BASE_SHA: ${{ github.event_name == 'pull_request' && github.event.pull_request.base.sha || '' }}",
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


if __name__ == "__main__":
    unittest.main()
