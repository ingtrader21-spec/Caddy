#!/usr/bin/env bash
set -Eeuo pipefail

for name in \
  CADDY_CANARY_SOURCE_SHA \
  CADDY_CANARY_IMAGE \
  CADDY_CANARY_IMAGE_DIGEST \
  CADDY_CANARY_CONFIG_SHA256 \
  CADDY_RELEASE_EVIDENCE_SHA256 \
  CADDY_STAGING_EVIDENCE_SHA256 \
  CADDY_ROLLBACK_EVIDENCE_SHA256 \
  CADDY_PRODUCTION_MTLS_CLIENT_CERT \
  CADDY_PRODUCTION_MTLS_CLIENT_KEY \
  CADDY_PRODUCTION_MTLS_CA_CERT \
  GITHUB_REPOSITORY; do
  [[ -n "${!name:-}" ]] || {
    echo "CADDY_PRODUCTION_READONLY_CANARY=FAIL:missing_${name}" >&2
    exit 2
  }
done

[[ "$CADDY_CANARY_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$CADDY_CANARY_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$CADDY_CANARY_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$CADDY_RELEASE_EVIDENCE_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$CADDY_STAGING_EVIDENCE_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$CADDY_ROLLBACK_EVIDENCE_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$CADDY_CANARY_IMAGE" == "ghcr.io/${GITHUB_REPOSITORY_OWNER}/codestra-caddy@${CADDY_CANARY_IMAGE_DIGEST}" ]]

for path in \
  "$CADDY_PRODUCTION_MTLS_CLIENT_CERT" \
  "$CADDY_PRODUCTION_MTLS_CLIENT_KEY" \
  "$CADDY_PRODUCTION_MTLS_CA_CERT"; do
  [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]]
  [[ -e "$path" ]]
done

[[ -s staging-evidence/bounded-staging-runtime-evidence.json ]]
[[ -s staging-evidence/one-click-rollback-evidence.json ]]
[[ "$(sha256sum staging-evidence/bounded-staging-runtime-evidence.json | awk '{print $1}')" == "$CADDY_STAGING_EVIDENCE_SHA256" ]]
[[ "$(sha256sum staging-evidence/one-click-rollback-evidence.json | awk '{print $1}')" == "$CADDY_ROLLBACK_EVIDENCE_SHA256" ]]
jq -e '
  .schema == "codestra.caddy.manual-rollback-evidence.v2" and
  .staging_certified == true and
  .caddy_kong_middleware_runtime_proven == true and
  .caddy_kong_middleware_runtime.route.method == "GET" and
  .caddy_kong_middleware_runtime.route.status == 404 and
  .caddy_kong_middleware_runtime.route.middleware_error_code == "command_not_found" and
  .caddy_kong_middleware_runtime.route.caddy_to_kong_to_middleware == "PASS" and
  .caddy_kong_middleware_runtime.middleware.environment == "staging" and
  .caddy_kong_middleware_runtime.application_mutations == 0 and
  .caddy_kong_middleware_runtime.provider_effects == 0 and
  .caddy_kong_middleware_runtime.external_effects_authorized == false and
  .caddy_kong_middleware_runtime.result == "PASS" and
  .rollback_rehearsed == true and
  .production_changed == false and
  .live_effects_enabled == false
' staging-evidence/one-click-rollback-evidence.json >/dev/null
middleware_runtime_evidence_sha256="$(jq -r '.middleware_runtime_evidence_sha256' staging-evidence/one-click-rollback-evidence.json)"
[[ "$middleware_runtime_evidence_sha256" =~ ^[0-9a-f]{64}$ ]]

[[ "$(git rev-parse HEAD)" == "$CADDY_CANARY_SOURCE_SHA" ]]
git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null
[[ "$(git rev-parse origin/production)" == "$CADDY_CANARY_SOURCE_SHA" ]]
[[ "$(python3 scripts/hash_config_tree.py config)" == "$CADDY_CANARY_CONFIG_SHA256" ]]
[[ -f deploy/compose.runtime.yaml ]]
[[ -z "$(git status --porcelain)" ]]

docker pull "$CADDY_CANARY_IMAGE"
[[ "$(docker image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == \
  "https://github.com/${GITHUB_REPOSITORY}" ]]
[[ "$(docker image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$CADDY_CANARY_SOURCE_SHA" ]]
[[ "$(docker image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')" == "$CADDY_CANARY_CONFIG_SHA256" ]]
[[ "$(docker image inspect "$CADDY_CANARY_IMAGE" --format '{{.Config.User}}')" == "65532:65532" ]]

identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/immutable-release.yml@refs/heads/production$"
cosign verify \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$CADDY_CANARY_IMAGE" > verified-production-signature.json
cosign verify-attestation \
  --type https://codestra.co/attestations/caddy-source/v2 \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$CADDY_CANARY_IMAGE" > verified-production-attestation.json

set -o pipefail
bash scripts/bounded-production-readonly-canary-v2.sh | tee production-readonly-canary.txt

[[ -s production-canary-evidence.json ]]
[[ -s pre-canary-runtime.json ]]
[[ -s post-canary-runtime.json ]]
cmp -s pre-canary-runtime.json post-canary-runtime.json
jq -e '.write_requests_sent == false and .candidate_started_on_production == false and .public_traffic_changed == false' \
  production-canary-evidence.json >/dev/null
grep -F -- "$CADDY_CANARY_SOURCE_SHA" production-canary-evidence.json >/dev/null

production_evidence_sha256="$(sha256sum production-canary-evidence.json | awk '{print $1}')"
pre_post_runtime_sha256="$(sha256sum pre-canary-runtime.json | awk '{print $1}')"

jq -n \
  --arg source_sha "$CADDY_CANARY_SOURCE_SHA" \
  --arg image "$CADDY_CANARY_IMAGE" \
  --arg image_digest "$CADDY_CANARY_IMAGE_DIGEST" \
  --arg config_sha256 "$CADDY_CANARY_CONFIG_SHA256" \
  --arg release_evidence_sha256 "$CADDY_RELEASE_EVIDENCE_SHA256" \
  --arg staging_evidence_sha256 "$CADDY_STAGING_EVIDENCE_SHA256" \
  --arg rollback_evidence_sha256 "$CADDY_ROLLBACK_EVIDENCE_SHA256" \
  --arg middleware_runtime_evidence_sha256 "$middleware_runtime_evidence_sha256" \
  --arg production_evidence_sha256 "$production_evidence_sha256" \
  --arg pre_post_runtime_sha256 "$pre_post_runtime_sha256" \
  --slurpfile rollback staging-evidence/one-click-rollback-evidence.json \
  '{
    schema:"codestra.caddy.manual-production-orchestrator-receipt.v2",
    source_sha:$source_sha,
    image:$image,
    image_digest:$image_digest,
    config_sha256:$config_sha256,
    release_evidence_sha256:$release_evidence_sha256,
    staging_evidence_sha256:$staging_evidence_sha256,
    rollback_evidence_sha256:$rollback_evidence_sha256,
    middleware_runtime_evidence_sha256:$middleware_runtime_evidence_sha256,
    caddy_kong_middleware_runtime:$rollback[0].caddy_kong_middleware_runtime,
    production_evidence_sha256:$production_evidence_sha256,
    pre_post_runtime_sha256:$pre_post_runtime_sha256,
    staging_certified:true,
    caddy_kong_middleware_runtime_proven:true,
    rollback_rehearsed:true,
    production_canary_read_only:true,
    write_requests_sent:false,
    public_traffic_changed:false,
    full_live_activation_authorized:false,
    verdict:"READ_ONLY_CANARY_PASS"
  }' > one-click-production-receipt.json

echo CADDY_PRODUCTION_READONLY_CANARY=PASS
echo CADDY_KONG_MIDDLEWARE_RUNTIME_BOUND=PASS
echo CADDY_FULL_LIVE_ACTIVATION_AUTHORIZED=false
