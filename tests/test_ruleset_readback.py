from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.verify_ruleset_readback import PolicyMismatch, compare_policy, unique_object

ROOT = Path(__file__).resolve().parents[1]


class RulesetReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = json.loads(
            (ROOT / "config/github/protected-branches-ruleset.json").read_text()
        )
        self.actual = copy.deepcopy(self.expected)

    def test_api_metadata_and_reordering_are_accepted(self) -> None:
        self.actual.update(id=123, source_type="Repository")
        self.actual["rules"].reverse()
        self.actual["conditions"]["ref_name"]["include"].reverse()
        compare_policy(self.expected, self.actual)

    def test_weakened_policy_is_rejected(self) -> None:
        mutations = (
            lambda p: p["conditions"]["ref_name"]["exclude"].append("refs/heads/main"),
            lambda p: p["bypass_actors"].append({"actor_id": 1, "actor_type": "Team"}),
            lambda p: p.update(enforcement="evaluate"),
            lambda p: self.rule(p, "required_status_checks").update(strict_required_status_checks_policy=False),
            lambda p: self.rule(p, "required_status_checks").update(do_not_enforce_on_create=True),
            lambda p: self.rule(p, "pull_request").update(required_approving_review_count=0),
            lambda p: self.rule(p, "pull_request").update(require_last_push_approval=False),
            lambda p: self.rule(p, "pull_request").update(dismiss_stale_reviews_on_push=False),
            lambda p: self.rule(p, "pull_request").update(require_last_push_approval=1),
            lambda p: self.rule(p, "required_status_checks")["required_status_checks"].pop(),
            lambda p: p["rules"].pop(),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                actual = copy.deepcopy(self.expected)
                mutate(actual)
                with self.assertRaises(PolicyMismatch):
                    compare_policy(self.expected, actual)

    def test_duplicate_list_entry_cannot_replace_a_required_rule(self) -> None:
        self.actual["rules"][0] = copy.deepcopy(self.actual["rules"][1])
        with self.assertRaises(PolicyMismatch):
            compare_policy(self.expected, self.actual)

    def test_missing_field_is_rejected(self) -> None:
        del self.actual["conditions"]["ref_name"]["exclude"]
        with self.assertRaises(PolicyMismatch):
            compare_policy(self.expected, self.actual)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(PolicyMismatch):
            json.loads('{"enforcement":"active","enforcement":"disabled"}',
                       object_pairs_hook=unique_object)

    @staticmethod
    def rule(policy: dict, name: str) -> dict:
        return next(rule["parameters"] for rule in policy["rules"] if rule["type"] == name)


if __name__ == "__main__":
    unittest.main()
