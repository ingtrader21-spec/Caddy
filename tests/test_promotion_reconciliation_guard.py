from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-promotion-route.sh"


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = run("git", *args, cwd=cwd, env=env)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class PromotionReconciliationGuardTests(unittest.TestCase):
    def test_normal_protected_routes_remain_bounded(self) -> None:
        routes = (
            ("development", "fix/example", True),
            ("test", "development", True),
            ("staging", "test", True),
            ("production", "staging", True),
            ("main", "production", True),
            ("test", "fix/not-a-promotion", False),
            ("staging", "development", False),
            ("production", "test", False),
            ("main", "staging", False),
        )
        for base, head, should_pass in routes:
            with self.subTest(base=base, head=head):
                env = os.environ | {
                    "EVENT_NAME": "pull_request",
                    "BASE_BRANCH": base,
                    "HEAD_BRANCH": head,
                    "HEAD_SHA": "0" * 40,
                    "BASE_SHA": "1" * 40,
                }
                result = run("bash", str(SCRIPT), cwd=ROOT, env=env)
                if should_pass:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("PROMOTION_GUARD=PASS", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0)

    def _exercise_reconciliation(self, source_branch: str, destination_branch: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            remote = tmp / "remote.git"
            seed = tmp / "seed"
            runner = tmp / "runner"
            git("init", "--bare", str(remote), cwd=tmp)
            git("init", str(seed), cwd=tmp)
            git("config", "user.name", "Caddy Test", cwd=seed)
            git("config", "user.email", "caddy-test@example.invalid", cwd=seed)

            (seed / "state.txt").write_text(f"{destination_branch}\n", encoding="utf-8")
            git("add", "state.txt", cwd=seed)
            git("commit", "-m", f"{destination_branch} base", cwd=seed)
            destination_sha = git("rev-parse", "HEAD", cwd=seed)
            git("branch", destination_branch, cwd=seed)

            git("checkout", "-b", source_branch, cwd=seed)
            (seed / "state.txt").write_text(f"{source_branch}\n", encoding="utf-8")
            git("commit", "-am", f"{source_branch} source", cwd=seed)
            source_sha = git("rev-parse", "HEAD", cwd=seed)
            git("remote", "add", "origin", str(remote), cwd=seed)
            git("push", "origin", destination_branch, source_branch, cwd=seed)

            git("clone", str(remote), str(runner), cwd=tmp)
            git("checkout", "--detach", destination_sha, cwd=runner)
            source_tree = git("rev-parse", f"{source_sha}^{{tree}}", cwd=runner)
            commit_env = os.environ | {
                "GIT_AUTHOR_NAME": "Caddy Test",
                "GIT_AUTHOR_EMAIL": "caddy-test@example.invalid",
                "GIT_COMMITTER_NAME": "Caddy Test",
                "GIT_COMMITTER_EMAIL": "caddy-test@example.invalid",
            }
            reconciliation_sha = git(
                "commit-tree",
                source_tree,
                "-p",
                destination_sha,
                "-m",
                f"reconcile exact {source_branch} tree",
                cwd=runner,
                env=commit_env,
            )
            git("checkout", "--detach", reconciliation_sha, cwd=runner)

            guard_env = os.environ | {
                "EVENT_NAME": "pull_request",
                "BASE_BRANCH": destination_branch,
                "HEAD_BRANCH": f"reconcile/{source_branch}-to-{destination_branch}-20260909",
                "HEAD_SHA": reconciliation_sha,
                "BASE_SHA": destination_sha,
            }
            result = run("bash", str(SCRIPT), cwd=runner, env=guard_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PROMOTION_RECONCILIATION=PASS", result.stdout)
            self.assertIn(f"source_branch={source_branch}", result.stdout)

            # A changed tree may never use the reconciliation branch name as a bypass.
            git("checkout", "--detach", destination_sha, cwd=runner)
            (runner / "state.txt").write_text("wrong\n", encoding="utf-8")
            git("add", "state.txt", cwd=runner)
            wrong_tree = git("write-tree", cwd=runner)
            wrong_sha = git(
                "commit-tree",
                wrong_tree,
                "-p",
                destination_sha,
                "-m",
                "wrong tree",
                cwd=runner,
                env=commit_env,
            )
            git("checkout", "--detach", wrong_sha, cwd=runner)
            guard_env["HEAD_SHA"] = wrong_sha
            result = run("bash", str(SCRIPT), cwd=runner, env=guard_env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"{source_branch}_tree_mismatch", result.stderr)

            # A stale or unrelated parent must also fail even with the exact source tree.
            unrelated_parent = git(
                "commit-tree",
                source_tree,
                "-p",
                source_sha,
                "-m",
                "wrong parent",
                cwd=runner,
                env=commit_env,
            )
            git("checkout", "--detach", unrelated_parent, cwd=runner)
            guard_env["HEAD_SHA"] = unrelated_parent
            result = run("bash", str(SCRIPT), cwd=runner, env=guard_env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f"reconciliation_parent_not_{destination_branch}", result.stderr)

    def test_reconciliation_is_available_on_every_forward_protected_edge(self) -> None:
        for source, destination in (
            ("development", "test"),
            ("test", "staging"),
            ("staging", "production"),
            ("production", "main"),
        ):
            with self.subTest(source=source, destination=destination):
                self._exercise_reconciliation(source, destination)


if __name__ == "__main__":
    unittest.main()
