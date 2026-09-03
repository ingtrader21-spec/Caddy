# Branch protection contract

`config/github/protected-branches-ruleset.json` is the machine-readable policy for `development`, `test`, `staging`, `production`, and `main`.

The policy blocks branch deletion and non-fast-forward updates; requires a pull request, blocks direct pushes, dismisses stale reviews, and requires resolved review threads; no human approval is required for an exact-head green promotion; permits merge commits so promotion ancestry remains auditable; requires `validate-source`, `validate-merge-result`, `promotion-guard`, and `immutable-release-gate`; and has no bypass actor.

Repository rules are an account-level GitHub setting. The JSON contract must be applied through an authenticated repository-administration channel and read back from GitHub before any branch is called protected. Merely committing this file does not change GitHub settings. `.github/workflows/apply-branch-ruleset.yml` applies and verifies it only when the repository has the dedicated `CODESTRA_GITHUB_ADMIN_TOKEN` secret.
