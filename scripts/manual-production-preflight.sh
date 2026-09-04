#!/usr/bin/env bash
set -Eeuo pipefail

confirmation="${1:-}"
expected_confirmation="${EXPECTED_CONFIRMATION:-RUN_CADDY_PRODUCTION}"

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_REPOSITORY_OWNER:?GITHUB_REPOSITORY_OWNER is required}"
: "${GITHUB_REF:?GITHUB_REF is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

[[ "$confirmation" == "$expected_confirmation" ]]
[[ "$GITHUB_REF" == "refs/heads/production" ]]
[[ "$GITHUB_SHA" =~ ^[0-9a-f]{40}$ ]]

[[ "$(git rev-parse HEAD)" == "$GITHUB_SHA" ]]
git fetch origin production --depth=1
[[ "$(git rev-parse origin/production)" == "$GITHUB_SHA" ]]
[[ -z "$(git status --porcelain)" ]]

bash scripts/validate-ci.sh

canonical_name='Protect Caddy promotion branches'
ruleset_id="$(
  gh api "repos/${GITHUB_REPOSITORY}/rulesets" \
    --jq ".[] | select(.name == \"$canonical_name\" and .enforcement == \"active\") | .id" \
    | head -n1
)"
[[ "$ruleset_id" =~ ^[0-9]+$ ]]
gh api "repos/${GITHUB_REPOSITORY}/rulesets/${ruleset_id}" > canonical-ruleset.json

expected_refs='refs/heads/development,refs/heads/main,refs/heads/production,refs/heads/staging,refs/heads/test'
expected_checks='immutable-release-gate,promotion-guard,validate-merge-result,validate-source'
jq -e --arg refs "$expected_refs" --arg checks "$expected_checks" '
  .name == "Protect Caddy promotion branches" and
  .target == "branch" and
  .enforcement == "active" and
  (.bypass_actors | length) == 0 and
  ([.conditions.ref_name.include[]] | sort | join(",")) == $refs and
  ([.rules[] | select(.type == "pull_request") | .parameters.required_approving_review_count][0]) == 1 and
  ([.rules[] | select(.type == "pull_request") | .parameters.dismiss_stale_reviews_on_push][0]) == true and
  ([.rules[] | select(.type == "pull_request") | .parameters.require_last_push_approval][0]) == true and
  ([.rules[] | select(.type == "pull_request") | .parameters.required_review_thread_resolution][0]) == true and
  ([.rules[] | select(.type == "pull_request") | .parameters.allowed_merge_methods[]] | join(",")) == "squash" and
  ([.rules[] | select(.type == "required_linear_history")] | length) == 1 and
  ([.rules[] | select(.type == "non_fast_forward")] | length) == 1 and
  ([.rules[] | select(.type == "deletion")] | length) == 1 and
  ([.rules[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context] | sort | join(",")) == $checks
' canonical-ruleset.json >/dev/null

source_sha="$GITHUB_SHA"
config_sha256="$(python3 scripts/hash_config_tree.py config)"
release_tag="caddy-production-${source_sha}"

gh api "repos/${GITHUB_REPOSITORY}/releases/tags/${release_tag}" > release.json
[[ "$(jq -r '.target_commitish' release.json)" == "$source_sha" ]]
[[ "$(jq -r '.draft' release.json)" == false ]]
[[ "$(jq -r '.prerelease' release.json)" == false ]]

image="$(
  jq -r '.body' release.json \
    | grep -Eo "ghcr\.io/${GITHUB_REPOSITORY_OWNER}/codestra-caddy@sha256:[0-9a-f]{64}" \
    | head -n1
)"
[[ -n "$image" ]]
image_digest="${image##*@}"
[[ "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]]

gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/immutable-release.yml/runs?branch=production&per_page=100" > immutable-runs.json
release_run_id="$(
  jq -r --arg sha "$source_sha" \
    '[.workflow_runs[] | select(.head_sha == $sha and .status == "completed" and .conclusion == "success")] | sort_by(.id) | last | .id // empty' \
    immutable-runs.json
)"
[[ "$release_run_id" =~ ^[0-9]+$ ]]

docker pull "$image"
[[ "$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == \
  "https://github.com/${GITHUB_REPOSITORY}" ]]
[[ "$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$source_sha" ]]
[[ "$(docker image inspect "$image" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')" == "$config_sha256" ]]
[[ "$(docker image inspect "$image" --format '{{.Config.User}}')" == "65532:65532" ]]

identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/immutable-release.yml@refs/heads/production$"
cosign verify \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$image" > verified-image-signature.json
cosign verify-attestation \
  --type https://codestra.co/attestations/caddy-source/v2 \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$image" > verified-source-attestation.json

gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${release_run_id}/artifacts" > release-artifacts.json
artifact_name="caddy-release-evidence-${source_sha}"
artifact_id="$(
  jq -r --arg name "$artifact_name" \
    '.artifacts[] | select(.name == $name and .expired == false) | .id' \
    release-artifacts.json \
    | head -n1
)"
[[ "$artifact_id" =~ ^[0-9]+$ ]]

jq -n \
  --arg source_sha "$source_sha" \
  --arg image "$image" \
  --arg image_digest "$image_digest" \
  --arg config_sha256 "$config_sha256" \
  --arg release_run_id "$release_run_id" \
  --arg artifact_id "$artifact_id" \
  '{
    schema:"codestra.caddy.manual-production-candidate.v1",
    source_sha:$source_sha,
    image:$image,
    image_digest:$image_digest,
    config_sha256:$config_sha256,
    release_run_id:($release_run_id|tonumber),
    release_artifact_id:($artifact_id|tonumber),
    branch_ruleset_verified:true,
    bypass_actors:0,
    required_approvals:1,
    require_last_push_approval:true,
    merge_method:"squash",
    linear_history:true,
    signature_verified:true,
    source_attestation_verified:true
  }' > exact-production-candidate.json

{
  printf 'source_sha=%s\n' "$source_sha"
  printf 'image=%s\n' "$image"
  printf 'image_digest=%s\n' "$image_digest"
  printf 'config_sha256=%s\n' "$config_sha256"
  printf 'release_run_id=%s\n' "$release_run_id"
  printf 'artifact_id=%s\n' "$artifact_id"
} >> "$GITHUB_OUTPUT"

echo CADDY_CANONICAL_BRANCH_RULESET=PASS
echo CADDY_EXACT_SIGNED_PRODUCTION_CANDIDATE=PASS
