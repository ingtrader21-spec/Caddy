#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  printf 'PROMOTION_GUARD=FAIL:%s\n' "$1" >&2
  exit 2
}

EVENT_NAME="${EVENT_NAME:-}"
BASE_BRANCH="${BASE_BRANCH:-}"
HEAD_BRANCH="${HEAD_BRANCH:-}"
HEAD_SHA="${HEAD_SHA:-}"
BASE_SHA="${BASE_SHA:-}"

if [[ "$EVENT_NAME" != "pull_request" ]]; then
  echo PROMOTION_GUARD=PASS
  exit 0
fi

[[ -n "$BASE_BRANCH" && -n "$HEAD_BRANCH" ]] || fail missing_branch_context

case "$BASE_BRANCH" in
  development)
    [[ "$HEAD_BRANCH" =~ ^(feat|fix|chore|docs|refactor)/ ]] || fail invalid_development_source
    ;;
  test)
    if [[ "$HEAD_BRANCH" == "development" ]]; then
      :
    elif [[ "$HEAD_BRANCH" =~ ^reconcile/development-to-test-[0-9]{8}([.-][A-Za-z0-9._-]+)?$ ]]; then
      [[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_head_sha
      [[ "$BASE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_base_sha
      command -v git >/dev/null 2>&1 || fail git_missing
      [[ "$(git rev-parse HEAD)" == "$HEAD_SHA" ]] || fail checkout_identity
      git fetch --no-tags --prune origin \
        +refs/heads/development:refs/remotes/origin/development \
        +refs/heads/test:refs/remotes/origin/test >/dev/null
      [[ "$(git rev-parse origin/test)" == "$BASE_SHA" ]] || fail stale_test_base
      read -r -a commit_line <<<"$(git rev-list --parents -n 1 "$HEAD_SHA")"
      [[ "${#commit_line[@]}" -eq 2 ]] || fail reconciliation_must_be_single_parent
      [[ "${commit_line[1]}" == "$BASE_SHA" ]] || fail reconciliation_parent_not_test
      head_tree="$(git rev-parse "$HEAD_SHA^{tree}")"
      development_tree="$(git rev-parse 'origin/development^{tree}')"
      [[ "$head_tree" == "$development_tree" ]] || fail development_tree_mismatch
      git diff --quiet "$HEAD_SHA" origin/development -- . || fail development_content_mismatch
      printf 'PROMOTION_RECONCILIATION=PASS test_parent=%s development_tree=%s\n' \
        "$BASE_SHA" "$development_tree"
    else
      fail invalid_test_source
    fi
    ;;
  staging)
    [[ "$HEAD_BRANCH" == "test" ]] || fail invalid_staging_source
    ;;
  production)
    [[ "$HEAD_BRANCH" == "staging" ]] || fail invalid_production_source
    ;;
  main)
    [[ "$HEAD_BRANCH" == "production" ]] || fail invalid_main_source
    ;;
  *)
    fail invalid_base
    ;;
esac

printf 'PROMOTION_GUARD=PASS route=%s->%s\n' "$HEAD_BRANCH" "$BASE_BRANCH"
