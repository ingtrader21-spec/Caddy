#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
REVIEWED_SHA="${CADDY_REVIEWED_SHA:-}"
IMAGE_SHA256="${CADDY_IMAGE_SHA256:-}"
ROLLBACK_BASELINE_FILE="${CADDY_ROLLBACK_BASELINE_FILE:-}"
ROLLBACK_EVIDENCE_FILE="${CADDY_ROLLBACK_EVIDENCE_FILE:-}"
PRODUCTION_REMOTE_SHA="${CADDY_PRODUCTION_REMOTE_SHA:-}"
IMAGE_REPOSITORY='ghcr.io/appolon1908-hue/codestra-caddy'
COSIGN_BIN='/usr/local/bin/cosign'
DOCKER_BIN='/usr/bin/docker'
PYTHON_BIN='/usr/bin/python3'
ATTESTATION_VERIFIER="$ROOT/scripts/verify-image-attestation.py"
PKI_PREPARER="$ROOT/scripts/prepare-runtime-pki-permissions.sh"
CERTIFICATE_IDENTITY_REGEXP='^https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release\.yml@refs/heads/production$'
CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'
CADDY_DATA_DIR="${CADDY_DATA_DIR:-/var/lib/codestra/caddy/data}"
CADDY_CONFIG_DIR="${CADDY_CONFIG_DIR:-/var/lib/codestra/caddy/runtime-config}"

fail() {
  printf 'CADDY_ACTIVATION=FAIL:%s\n' "$1" >&2
  exit 1
}

trusted_executable() {
  local requested="$1" resolved owner mode mode_value
  resolved="$(readlink -f -- "$requested")"
  [[ -x "$requested" && -n "$resolved" && -x "$resolved" && ! -L "$resolved" ]] || \
    fail "trusted_executable:$requested"
  owner="$(stat -c '%u:%g' -- "$resolved")"
  mode="$(stat -c '%a' -- "$resolved")"
  mode_value=$((8#$mode))
  [[ "$owner" == '0:0' ]] && (( (mode_value & 0022) == 0 )) || \
    fail "executable_ownership:$requested"
}

rollback_after_failure() {
  local reason="$1" rollback_output rollback_status
  set +e
  rollback_output="$($ROOT/scripts/rollback-runtime.sh 2>&1)"
  rollback_status=$?
  set -e
  printf '%s\n' "$rollback_output" >&2
  if [[ "$rollback_status" -eq 0 ]] && grep -q '^CADDY_ROLLBACK=PASS$' <<<"$rollback_output"; then
    fail "activation_rolled_back:$reason"
  fi
  fail "activation_and_rollback_failed:$reason"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required
[[ "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_image_digest
[[ "$ROLLBACK_BASELINE_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline\.json$ ]] || \
  fail rollback_baseline_required
[[ -f "$ROLLBACK_BASELINE_FILE" && ! -L "$ROLLBACK_BASELINE_FILE" ]] || fail rollback_baseline_file
[[ "$(stat -c '%u:%g:%a' -- "$ROLLBACK_BASELINE_FILE")" == 0:0:600 ]] || fail rollback_baseline_permissions
if [[ -n "$ROLLBACK_EVIDENCE_FILE" ]]; then
  [[ "$ROLLBACK_EVIDENCE_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-result\.json$ ]] || \
    fail rollback_evidence_path
fi
IMAGE_REF="${IMAGE_REPOSITORY}@sha256:${IMAGE_SHA256}"

for binary in "$COSIGN_BIN" "$DOCKER_BIN" "$PYTHON_BIN"; do
  trusted_executable "$binary"
done
[[ -x "$PKI_PREPARER" && ! -L "$PKI_PREPARER" ]] || fail pki_preparer_unavailable

GIT=(git -c "safe.directory=$ROOT" -C "$ROOT")
[[ -z "$(${GIT[@]} status --porcelain)" ]] || fail dirty_worktree
[[ "$(${GIT[@]} branch --show-current)" == production ]] || fail wrong_branch
head_sha="$(${GIT[@]} rev-parse HEAD)"
if [[ -n "$PRODUCTION_REMOTE_SHA" ]]; then
  [[ "$PRODUCTION_REMOTE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_remote_source_sha
  remote_sha="$PRODUCTION_REMOTE_SHA"
else
  "${GIT[@]}" fetch --quiet origin production
  remote_sha="$(${GIT[@]} rev-parse refs/remotes/origin/production)"
fi
[[ "$head_sha" == "$REVIEWED_SHA" && "$remote_sha" == "$REVIEWED_SHA" ]] || fail source_identity

for state_dir in "$CADDY_DATA_DIR" "$CADDY_CONFIG_DIR"; do
  [[ -d "$state_dir" && ! -L "$state_dir" ]] || fail "state_path:$state_dir"
  [[ "$(stat -c '%u:%g' -- "$state_dir")" == '65532:65532' ]] || fail "state_owner:$state_dir"
  mode="$(stat -c '%a' -- "$state_dir")"
  mode_value=$((8#$mode))
  (( (mode_value & 0200) != 0 && (mode_value & 0022) == 0 )) || fail "state_mode:$state_dir"
done

"$PKI_PREPARER"
for trust_dir in /etc/caddy/private/klyrow-events /etc/codestra/pki/middleware-private-ingress; do
  [[ -d "$trust_dir" && ! -L "$trust_dir" ]] || fail "trust_path:$trust_dir"
  [[ "$(stat -c '%u:%g:%a' -- "$trust_dir")" == '0:65532:750' ]] || fail "trust_directory_mode:$trust_dir"
  while IFS= read -r trust_file; do
    [[ "$(stat -c '%u:%g:%a' -- "$trust_file")" == '0:65532:440' ]] || fail "trust_file_mode:$trust_file"
  done < <(find "$trust_dir" -mindepth 1 -maxdepth 1 -type f -print | sort)
done

export CADDY_CONFIG_SHA256
CADDY_CONFIG_SHA256="$($PYTHON_BIN "$ROOT/scripts/hash_config_tree.py" "$ROOT/config")"
export CADDY_RELEASE_ID="production-$REVIEWED_SHA"
export CADDY_DATA_DIR CADDY_CONFIG_DIR CADDY_IMAGE_SHA256 CADDY_REVIEWED_SHA
export CADDY_ROLLBACK_BASELINE_FILE CADDY_ROLLBACK_EVIDENCE_FILE

"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet
"$COSIGN_BIN" verify \
  --certificate-identity-regexp "$CERTIFICATE_IDENTITY_REGEXP" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$IMAGE_REF" >/dev/null

attestation_output="$(mktemp)"
cleanup() { rm -f -- "$attestation_output"; }
trap cleanup EXIT
"$COSIGN_BIN" verify-attestation \
  --type https://codestra.co/attestations/caddy-source/v2 \
  --certificate-identity-regexp "$CERTIFICATE_IDENTITY_REGEXP" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  --output json "$IMAGE_REF" >"$attestation_output"
"$PYTHON_BIN" "$ATTESTATION_VERIFIER" \
  "$attestation_output" "$IMAGE_SHA256" \
  https://github.com/appolon1908-hue/Caddy \
  "$REVIEWED_SHA" "$CADDY_CONFIG_SHA256"

"$DOCKER_BIN" pull "$IMAGE_REF" >/dev/null
image_revision="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE_REF")"
image_source="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$IMAGE_REF")"
image_config="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$IMAGE_REF")"
[[ "$image_revision" == "$REVIEWED_SHA" ]] || fail image_revision
[[ "$image_source" == 'https://github.com/appolon1908-hue/Caddy' ]] || fail image_source
[[ "$image_config" == "$CADDY_CONFIG_SHA256" ]] || fail image_config

"$DOCKER_BIN" compose -f "$COMPOSE" run --rm --no-deps \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
"$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy

for _ in $(seq 1 60); do
  state="$("$DOCKER_BIN" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"
  [[ "$state" == healthy ]] && break
  sleep 2
done

if [[ "$("$DOCKER_BIN" inspect --format '{{.State.Health.Status}}' codestra-caddy 2>/dev/null || true)" != healthy ]]; then
  rollback_after_failure unhealthy_candidate
fi

if ! canary_output="$("$ROOT/scripts/production-canary.sh")"; then
  rollback_after_failure runtime_readback
fi

actual_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
actual_source="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
actual_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
if [[ "$actual_image" != "$IMAGE_REF" || "$actual_source" != "$REVIEWED_SHA" || "$actual_config" != "$CADDY_CONFIG_SHA256" ]]; then
  rollback_after_failure final_identity_readback
fi

printf '%s\n' "$canary_output"
printf 'CADDY_ACTIVATION=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nROLLBACK_BASELINE_FILE=%s\n' \
  "$REVIEWED_SHA" "$IMAGE_REF" "$CADDY_CONFIG_SHA256" "$ROLLBACK_BASELINE_FILE"
