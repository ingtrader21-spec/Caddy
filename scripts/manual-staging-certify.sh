#!/usr/bin/env bash
set -Eeuo pipefail

for name in \
  CADDY_STAGING_IMAGE \
  CADDY_STAGING_SOURCE_SHA \
  CADDY_STAGING_CONFIG_SHA256 \
  CADDY_STAGING_ENV_FILE \
  CADDY_STAGING_DATA_SOURCE \
  CADDY_STAGING_MTLS_CLIENT_CERT \
  CADDY_STAGING_MTLS_CLIENT_KEY \
  CADDY_STAGING_MTLS_CA_CERT \
  GITHUB_REPOSITORY \
  GITHUB_OUTPUT; do
  [[ -n "${!name:-}" ]] || {
    echo "CADDY_BOUNDED_STAGING=FAIL:missing_${name}" >&2
    exit 2
  }
done

[[ "$CADDY_STAGING_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$CADDY_STAGING_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]]
[[ "$CADDY_STAGING_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]

for path in \
  "$CADDY_STAGING_ENV_FILE" \
  "$CADDY_STAGING_DATA_SOURCE" \
  "$CADDY_STAGING_MTLS_CLIENT_CERT" \
  "$CADDY_STAGING_MTLS_CLIENT_KEY" \
  "$CADDY_STAGING_MTLS_CA_CERT"; do
  [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]]
  [[ -e "$path" ]]
done

[[ "$(git rev-parse HEAD)" == "$CADDY_STAGING_SOURCE_SHA" ]]
git fetch origin production --depth=1
[[ "$(git rev-parse origin/production)" == "$CADDY_STAGING_SOURCE_SHA" ]]
[[ "$(python3 scripts/hash_config_tree.py config)" == "$CADDY_STAGING_CONFIG_SHA256" ]]
[[ -f deploy/compose.runtime.yaml ]]
[[ -z "$(git status --porcelain)" ]]
bash scripts/validate-ci.sh

docker pull "$CADDY_STAGING_IMAGE"
[[ "$(docker image inspect "$CADDY_STAGING_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == \
  "https://github.com/${GITHUB_REPOSITORY}" ]]
[[ "$(docker image inspect "$CADDY_STAGING_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$CADDY_STAGING_SOURCE_SHA" ]]
[[ "$(docker image inspect "$CADDY_STAGING_IMAGE" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')" == "$CADDY_STAGING_CONFIG_SHA256" ]]
[[ "$(docker image inspect "$CADDY_STAGING_IMAGE" --format '{{.Config.User}}')" == "65532:65532" ]]

identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/immutable-release.yml@refs/heads/production$"
cosign verify \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$CADDY_STAGING_IMAGE" > verified-staging-signature.json
cosign verify-attestation \
  --type https://codestra.co/attestations/caddy-source/v2 \
  --certificate-identity-regexp "$identity" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$CADDY_STAGING_IMAGE" > verified-staging-attestation.json

set -o pipefail
bash scripts/bounded-staging-runtime-v2.sh | tee bounded-staging-runtime.txt
bash scripts/verify-rollback-baseline.sh | tee bounded-staging-rollback.txt

[[ -s bounded-staging-runtime-evidence.json ]]
grep -F -- "$CADDY_STAGING_SOURCE_SHA" bounded-staging-runtime-evidence.json >/dev/null
grep -F -- "$CADDY_STAGING_CONFIG_SHA256" bounded-staging-runtime-evidence.json >/dev/null

staging_evidence_sha256="$(sha256sum bounded-staging-runtime-evidence.json | awk '{print $1}')"
rollback_output_sha256="$(sha256sum bounded-staging-rollback.txt | awk '{print $1}')"
compose_sha256="$(sha256sum deploy/compose.runtime.yaml | awk '{print $1}')"
baseline_sha256="$(sha256sum config/release-baseline.v1.json | awk '{print $1}')"

jq -n \
  --arg source_sha "$CADDY_STAGING_SOURCE_SHA" \
  --arg image "$CADDY_STAGING_IMAGE" \
  --arg config_sha256 "$CADDY_STAGING_CONFIG_SHA256" \
  --arg staging_evidence_sha256 "$staging_evidence_sha256" \
  --arg rollback_output_sha256 "$rollback_output_sha256" \
  --arg compose_sha256 "$compose_sha256" \
  --arg baseline_sha256 "$baseline_sha256" \
  '{
    schema:"codestra.caddy.manual-rollback-evidence.v1",
    source_sha:$source_sha,
    image:$image,
    config_sha256:$config_sha256,
    staging_evidence_sha256:$staging_evidence_sha256,
    rollback_output_sha256:$rollback_output_sha256,
    unified_compose_sha256:$compose_sha256,
    rollback_baseline_sha256:$baseline_sha256,
    staging_certified:true,
    rollback_rehearsed:true,
    production_changed:false,
    live_effects_enabled:false
  }' > one-click-rollback-evidence.json

rollback_evidence_sha256="$(sha256sum one-click-rollback-evidence.json | awk '{print $1}')"
{
  printf 'staging_evidence_sha256=%s\n' "$staging_evidence_sha256"
  printf 'rollback_evidence_sha256=%s\n' "$rollback_evidence_sha256"
} >> "$GITHUB_OUTPUT"

echo CADDY_BOUNDED_STAGING=PASS
echo CADDY_ROLLBACK_REHEARSAL=PASS
