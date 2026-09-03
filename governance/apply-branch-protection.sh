#!/usr/bin/env bash
set -Eeuo pipefail

repository="${1:-appolon1908-hue/Caddy}"
owner="${repository%%/*}"
repo="${repository#*/}"
required_common='["exact-head-validation","merge-result-validation","promotion-guard","immutable-release-gate"]'

apply() {
  local branch="$1"
  local contexts="$required_common"
  if [[ "$branch" == production ]]; then
    contexts='["exact-head-validation","merge-result-validation","promotion-guard","immutable-release-gate","staging-certification"]'
  elif [[ "$branch" == main ]]; then
    contexts='["validate","exact-head-validation","merge-result-validation","promotion-guard","immutable-release-gate"]'
  fi
  jq -n --argjson contexts "$contexts" '{
    required_status_checks:{strict:true,contexts:$contexts},
    enforce_admins:true,
    required_pull_request_reviews:{
      dismissal_restrictions:{users:[],teams:[],apps:[]},
      dismiss_stale_reviews:true,
      require_code_owner_reviews:false,
      required_approving_review_count:0,
      require_last_push_approval:false,
      bypass_pull_request_allowances:{users:[],teams:[],apps:[]}
    },
    restrictions:null,
    required_linear_history:false,
    allow_force_pushes:false,
    allow_deletions:false,
    block_creations:false,
    required_conversation_resolution:true,
    lock_branch:false,
    allow_fork_syncing:false
  }' | gh api --method PUT \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "/repos/${owner}/${repo}/branches/${branch}/protection" --input - >/dev/null
  gh api "/repos/${owner}/${repo}/branches/${branch}" --jq \
    '{name,protected,required_checks:.protection.required_status_checks.contexts}'
}

for branch in development test staging production main; do
  apply "$branch"
done
