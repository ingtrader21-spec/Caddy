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
git rev-parse --verify --quiet refs/remotes/origin/production >/dev/null
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
[[ -s caddy-kong-middleware-runtime-evidence.json ]]
[[ -s bounded-staging-runtime-evidence.json ]]
python3 - <<'PY'
import json
from pathlib import Path

value = json.loads(Path("caddy-kong-middleware-runtime-evidence.json").read_text())
assert value["schema"] == "codestra.caddy-kong-middleware-runtime.v1"
assert value["gateway_environment"] == "staging"
assert value["route"]["edge_host"] == "bridge-staging.codestra.agency"
assert value["route"]["gateway_environment"] == "staging"
assert value["route"]["method"] == "GET"
assert value["route"]["status"] == 404
assert value["route"]["middleware_error_code"] == "command_not_found"
assert value["route"]["caddy_to_kong_to_middleware"] == "PASS"
assert value["middleware"]["environment"] == "staging"
assert value["application_mutations"] == 0
assert value["provider_effects"] == 0
assert value["external_effects_authorized"] is False
assert value["result"] == "PASS"

bounded = json.loads(Path("bounded-staging-runtime-evidence.json").read_text())
assert bounded["staging_gateway_identity"] == "PASS"
assert bounded["staging_ca_anchor"] == "PASS"
assert len(bounded["staging_gateway_identity_evidence_sha256"]) == 64
assert len(bounded["staging_ca_anchor_sha256"]) == 64
assert bounded["public_traffic_changed"] is False
assert bounded["result"] == "PASS"
PY
bash scripts/verify-rollback-baseline.sh | tee bounded-staging-rollback.txt

grep -F -- "$CADDY_STAGING_SOURCE_SHA" bounded-staging-runtime-evidence.json >/dev/null
grep -F -- "$CADDY_STAGING_CONFIG_SHA256" bounded-staging-runtime-evidence.json >/dev/null

staging_evidence_sha256="$(sha256sum bounded-staging-runtime-evidence.json | awk '{print $1}')"
middleware_runtime_evidence_sha256="$(sha256sum caddy-kong-middleware-runtime-evidence.json | awk '{print $1}')"
rollback_output_sha256="$(sha256sum bounded-staging-rollback.txt | awk '{print $1}')"
compose_sha256="$(sha256sum deploy/compose.runtime.yaml | awk '{print $1}')"
baseline_sha256="$(sha256sum config/release-baseline.v1.json | awk '{print $1}')"

jq -n \
  --arg source_sha "$CADDY_STAGING_SOURCE_SHA" \
  --arg image "$CADDY_STAGING_IMAGE" \
  --arg config_sha256 "$CADDY_STAGING_CONFIG_SHA256" \
  --arg staging_evidence_sha256 "$staging_evidence_sha256" \
  --arg middleware_runtime_evidence_sha256 "$middleware_runtime_evidence_sha256" \
  --arg rollback_output_sha256 "$rollback_output_sha256" \
  --arg compose_sha256 "$compose_sha256" \
  --arg baseline_sha256 "$baseline_sha256" \
  --slurpfile middleware_runtime caddy-kong-middleware-runtime-evidence.json \
  '{
    schema:"codestra.caddy.manual-rollback-evidence.v2",
    source_sha:$source_sha,
    image:$image,
    config_sha256:$config_sha256,
    staging_evidence_sha256:$staging_evidence_sha256,
    middleware_runtime_evidence_sha256:$middleware_runtime_evidence_sha256,
    caddy_kong_middleware_runtime:$middleware_runtime[0],
    rollback_output_sha256:$rollback_output_sha256,
    unified_compose_sha256:$compose_sha256,
    rollback_baseline_sha256:$baseline_sha256,
    staging_certified:true,
    caddy_kong_middleware_runtime_proven:true,
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
echo CADDY_KONG_MIDDLEWARE_RUNTIME=PASS
echo CADDY_ROLLBACK_REHEARSAL=PASS
