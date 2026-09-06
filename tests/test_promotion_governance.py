from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULESET = ROOT / "config/github/protected-branches-ruleset.json"
WORKFLOW = ROOT / ".github/workflows/apply-branch-ruleset.yml"


class PromotionGovernanceTests(unittest.TestCase):
    def test_ruleset_is_fail_closed_and_covers_the_full_promotion_chain(self) -> None:
        value = json.loads(RULESET.read_text(encoding="utf-8"))
        self.assertEqual(value["name"], "Protect Caddy promotion branches")
        self.assertEqual(value["target"], "branch")
        self.assertEqual(value["enforcement"], "active")
        self.assertEqual(value.get("bypass_actors"), [])
        self.assertEqual(
            set(value["conditions"]["ref_name"]["include"]),
            {
                "refs/heads/development",
                "refs/heads/test",
                "refs/heads/staging",
                "refs/heads/production",
                "refs/heads/main",
            },
        )
        self.assertEqual(value["conditions"]["ref_name"]["exclude"], [])

        rules = {item["type"]: item for item in value["rules"]}
        self.assertIn("deletion", rules)
        self.assertIn("non_fast_forward", rules)
        self.assertIn("required_linear_history", rules)

        pull_request = rules["pull_request"]["parameters"]
        self.assertEqual(pull_request["required_approving_review_count"], 1)
        self.assertIs(pull_request["dismiss_stale_reviews_on_push"], True)
        self.assertIs(pull_request["require_code_owner_review"], False)
        self.assertIs(pull_request["require_last_push_approval"], True)
        self.assertIs(pull_request["required_review_thread_resolution"], True)
        self.assertEqual(pull_request["allowed_merge_methods"], ["squash"])

        required = rules["required_status_checks"]["parameters"]
        self.assertIs(required["strict_required_status_checks_policy"], True)
        self.assertIs(required["do_not_enforce_on_create"], False)
        self.assertEqual(
            {item["context"] for item in required["required_status_checks"]},
            {
                "validate-source",
                "validate-merge-result",
                "promotion-guard",
                "immutable-release-gate",
            },
        )

    def test_application_is_explicit_main_only_and_uses_one_named_secret(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertIsNone(re.search(r"(?m)^  push:\s*$", source))
        self.assertIn("APPLY_CADDY_PROMOTION_RULESET", source)
        self.assertIn("github.ref == 'refs/heads/main'", source)
        self.assertIn("secrets.CODESTRA_REPOSITORY_ADMIN_TOKEN", source)
        for alias in (
            "CODESTRA_GITHUB_ADMIN_TOKEN",
            "GITHUB_ADMIN_TOKEN",
            "GH_ADMIN_TOKEN",
            "RULESET_TOKEN",
            "BRANCH_PROTECTION_TOKEN",
            "REPO_ADMIN_TOKEN",
            "PERSONAL_ACCESS_TOKEN",
        ):
            self.assertNotIn(f"secrets.{alias}", source)
        self.assertIn("missing_CODESTRA_REPOSITORY_ADMIN_TOKEN", source)
        self.assertIn("caddy-promotion-ruleset-readback.json", source)
        self.assertIn("CADDY_BRANCH_RULESET_READBACK=PASS", source)
        self.assertIn("CADDY_RUNTIME_CHANGED=NO", source)


if __name__ == "__main__":
    unittest.main()
