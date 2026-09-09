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
        env = os.environ | {
            "EVENT_NAME": "pull_request",
            "BASE_BRANCH": "development",
            "HEAD_BRANCH": "fix/example",
            "HEAD_SHA": "0" * 40,
            "BASE_SHA": "1" * 40,
        }
        result = run("bash", str(SCRIPT), cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PROMOTION_GUARD=PASS", result.stdout)

        env["BASE_BRANCH"] = "test"
        env["HEAD_BRANCH"] = "fix/not-a-promotion"
        result = run("bash", str(SCRIPT), cwd=ROOT, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid_test_source", result.stderr)

    def test_reconciliation_requires_exact_test_parent_and_development_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            remote = tmp / "remote.git"
            seed = tmp / "seed"
            runner = tmp / "runner"
            git("init", "--bare", str(remote), cwd=tmp)
            git("init", str(seed), cwd=tmp)
            git("config", "user.name", "Caddy Test", cwd=seed)
            git("config", "user.email", "caddy-test@example.invalid", cwd=seed)
            (seed / "state.txt").write_text("test\n", encoding="utf-8")
            git("add", "state.txt", cwd=seed)
            git("commit", "-m", "test base", cwd=seed)
            test_sha = git("rev-parse", "HEAD", cwd=seed)
            git("branch", "test", cwd=seed)
            git("checkout", "-b", "development", cwd=seed)
            (seed / "state.txt").write_text("development\n", encoding="utf-8")
            git("commit", "-am", "development source", cwd=seed)
            development_sha = git("rev-parse", "HEAD", cwd=seed)
            git("remote", "add", "origin", str(remote), cwd=seed)
            git("push", "origin", "test", "development", cwd=seed)

            git("clone", str(remote), str(runner), cwd=tmp)
            git("checkout", "--detach", test_sha, cwd=runner)
            development_tree = git("rev-parse", f"{development_sha}^{{tree}}", cwd=runner)
            commit_env = os.environ | {
                "GIT_AUTHOR_NAME": "Caddy Test",
                "GIT_AUTHOR_EMAIL": "caddy-test@example.invalid",
                "GIT_COMMITTER_NAME": "Caddy Test",
                "GIT_COMMITTER_EMAIL": "caddy-test@example.invalid",
            }
            reconciliation_sha = git(
                "commit-tree",
                development_tree,
                "-p",
                test_sha,
                "-m",
                "reconcile exact development tree",
                cwd=runner,
                env=commit_env,
            )
            git("checkout", "--detach", reconciliation_sha, cwd=runner)

            guard_env = os.environ | {
                "EVENT_NAME": "pull_request",
                "BASE_BRANCH": "test",
                "HEAD_BRANCH": "reconcile/development-to-test-20260909",
                "HEAD_SHA": reconciliation_sha,
                "BASE_SHA": test_sha,
            }
            result = run("bash", str(SCRIPT), cwd=runner, env=guard_env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PROMOTION_RECONCILIATION=PASS", result.stdout)

            git("checkout", "--detach", test_sha, cwd=runner)
            (runner / "state.txt").write_text("wrong\n", encoding="utf-8")
            git("add", "state.txt", cwd=runner)
            wrong_tree = git("write-tree", cwd=runner)
            wrong_sha = git(
                "commit-tree",
                wrong_tree,
                "-p",
                test_sha,
                "-m",
                "wrong tree",
                cwd=runner,
                env=commit_env,
            )
            git("checkout", "--detach", wrong_sha, cwd=runner)
            guard_env["HEAD_SHA"] = wrong_sha
            result = run("bash", str(SCRIPT), cwd=runner, env=guard_env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("development_tree_mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
