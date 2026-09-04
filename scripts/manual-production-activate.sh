#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly DOCKER_BIN=/usr/bin/docker
readonly COSIGN_BIN=/usr/local/bin/cosign
readonly PYTHON_BIN=/usr/bin/python3
readonly JQ_BIN=/usr/bin/jq
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly SOURCE_SHA="${CADDY_ACTIVATION_SOURCE_SHA:-}"
readonly IMAGE="${CADDY_ACTIVATION_IMAGE:-}"
readonly IMAGE_DIGEST="${CADDY_ACTIVATION_IMAGE_DIGEST:-}"
readonly CONFIG_SHA256="${CADDY_ACTIVATION_CONFIG_SHA256:-}"
readonly RELEASE_EVIDENCE_SHA256="${CADDY_RELEASE_EVIDENCE_SHA256:-}"
readonly STAGING_EVIDENCE_SHA256="${CADDY_STAGING_EVIDENCE_SHA256:-}"
readonly ROLLBACK_REHEARSAL_SHA256="${CADDY_ROLLBACK_EVIDENCE_SHA256:-}"
readonly RUNTIME_ENV_FILE="${CADDY_PRODUCTION_ENV_FILE:-}"
readonly READONLY_RECEIPT="${CADDY_READONLY_RECEIPT:-readonly-evidence/one-click-production-receipt.json}"
readonly EVIDENCE_ROOT=/var/lib/codestra/caddy/evidence
readonly EVIDENCE_ID="${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}"
readonly BASELINE_FILE="$EVIDENCE_ROOT/caddy-orchestrator-${EVIDENCE_ID}-rollback-baseline.json"
readonly ROLLBACK_RESULT_FILE="$EVIDENCE_ROOT/caddy-orchestrator-${EVIDENCE_ID}-rollback-result.json"
readonly ACTIVATION_EVIDENCE=production-activation-evidence.json
readonly ACTIVATION_LOG=production-activation.txt
readonly FINAL_RUNTIME=final-production-runtime.json

phase=preflight
baseline_sha256=""
readonly_receipt_sha256=""
activation_output_sha256=""
final_runtime_sha256=""
rollback_status="NOT_REQUIRED"

fail() {
  printf 'CADDY_MANUAL_PRODUCTION_ACTIVATION=FAIL:%s\n' "$1" >&2
  exit 2
}

trusted_executable() {
  local requested="$1" resolved owner mode mode_value
  resolved="$(readlink -f -- "$requested")"
  [[ -x "$requested" && -n "$resolved" && -x "$resolved" && ! -L "$resolved" ]] || \
    fail "trusted_executable:$requested"
  owner="$(stat -c '%u:%g' -- "$resolved")"
  mode="$(stat -c '%a' -- "$resolved")"
  mode_value=$((8#$mode))
  [[ "$owner" == 0:0 ]] && (( (mode_value & 0022) == 0 )) || \
    fail "executable_ownership:$requested"
}

write_evidence() {
  local result="$1" reason="$2" candidate_live="$3" previous_restored="$4"
  local completed_at rollback_sha="" baseline_source="" baseline_image="" baseline_config=""
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ -f "$ROLLBACK_RESULT_FILE" && ! -L "$ROLLBACK_RESULT_FILE" ]]; then
    rollback_sha="$(sha256sum "$ROLLBACK_RESULT_FILE" | awk '{print $1}')"
    if "$JQ_BIN" -e '.schema == "codestra.caddy-runtime-rollback-result.v1" and .result == "PASS"' \
      "$ROLLBACK_RESULT_FILE" >/dev/null 2>&1; then
      rollback_status=PASS
    else
      rollback_status=FAIL
    fi
  fi
  if [[ -f "$BASELINE_FILE" && ! -L "$BASELINE_FILE" ]]; then
    baseline_source="$("$JQ_BIN" -r '.source_sha // empty' "$BASELINE_FILE")"
    baseline_image="$("$JQ_BIN" -r '.image // empty' "$BASELINE_FILE")"
    baseline_config="$("$JQ_BIN" -r '.config_sha256 // empty' "$BASELINE_FILE")"
  fi
  "$JQ_BIN" -n \
    --arg source_sha "$SOURCE_SHA" \
    --arg image "$IMAGE" \
    --arg image_digest "$IMAGE_DIGEST" \
    --arg config_sha256 "$CONFIG_SHA256" \
    --arg release_evidence_sha256 "$RELEASE_EVIDENCE_SHA256" \
    --arg staging_evidence_sha256 "$STAGING_EVIDENCE_SHA256" \
    --arg rollback_rehearsal_sha256 "$ROLLBACK_REHEARSAL_SHA256" \
    --arg readonly_receipt_sha256 "$readonly_receipt_sha256" \
    --arg baseline_file "$BASELINE_FILE" \
    --arg baseline_sha256 "$baseline_sha256" \
    --arg baseline_source_sha "$baseline_source" \
    --arg baseline_image "$baseline_image" \
    --arg baseline_config_sha256 "$baseline_config" \
    --arg rollback_result_file "$ROLLBACK_RESULT_FILE" \
    --arg rollback_result_sha256 "$rollback_sha" \
    --arg rollback_status "$rollback_status" \
    --arg activation_output_sha256 "$activation_output_sha256" \
    --arg final_runtime_sha256 "$final_runtime_sha256" \
    --arg phase "$phase" \
    --arg reason "$reason" \
    --arg completed_at "$completed_at" \
    --arg result "$result" \
    --argjson candidate_live "$candidate_live" \
    --argjson previous_restored "$previous_restored" \
    '{
      schema:"codestra.caddy.production-activation.v1",
      source_sha:$source_sha,
      image:$image,
      image_digest:$image_digest,
      config_sha256:$config_sha256,
      release_evidence_sha256:$release_evidence_sha256,
      staging_evidence_sha256:$staging_evidence_sha256,
      rollback_rehearsal_sha256:$rollback_rehearsal_sha256,
      readonly_receipt_sha256:$readonly_receipt_sha256,
      rollback_baseline:{file:$baseline_file,sha256:$baseline_sha256,source_sha:$baseline_source_sha,image:$baseline_image,config_sha256:$baseline_config_sha256},
      rollback_result:{file:$rollback_result_file,sha256:$rollback_result_sha256,status:$rollback_status},
      activation_output_sha256:$activation_output_sha256,
      final_runtime_sha256:$final_runtime_sha256,
      failed_phase:$phase,
      reason:$reason,
      automatic_rollback_armed:true,
      candidate_runtime_live:$candidate_live,
      previous_runtime_restored:$previous_restored,
      caddy_runtime_activation_authorized:true,
      application_writes_authorized:false,
      provider_delivery_authorized:false,
      email_authorized:false,
      sms_authorized:false,
      pstn_authorized:false,
      campaign_activation_authorized:false,
      dns_changed:false,
      firewall_changed:false,
      ssh_changed:false,
      unrelated_workloads_changed:false,
      completed_at:$completed_at,
      result:$result
    }' > "$ACTIVATION_EVIDENCE"
  activation_evidence_sha256="$(sha256sum "$ACTIVATION_EVIDENCE" | awk '{print $1}')"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf 'activation_evidence_sha256=%s\n' "$activation_evidence_sha256" >> "$GITHUB_OUTPUT"
  fi
}

load_runtime_environment() {
  local line key value
  declare -A allowed=()
  declare -A seen=()
  local required=(
    CADDY_PUBLIC_BIND
    CADDY_PRIVATE_METRICS_BIND
    CADDY_PRIVATE_INGRESS_BIND
    CADDY_KLYROW_SOURCE_CIDRS
    CADDY_VICIDIAL_SOURCE_CIDRS
    CADDY_STAGING_EVENT_SOURCE_CIDRS
    CADDY_KONG_UPSTREAM
    CADDY_REALTIME_UPSTREAM
    CADDY_KEYCLOAK_UPSTREAM
    CADDY_CRM_RESELLER_UPSTREAM
    CADDY_CRM_UPSTREAM
    CADDY_N8N_UPSTREAM
    CADDY_N8N_STAGING_UPSTREAM
    CADDY_STAGING_API_UPSTREAM
    CADDY_STAGING_PORTAL_UPSTREAM
    CADDY_STAGING_KEYCLOAK_UPSTREAM
    CADDY_STAGING_ODOO_UPSTREAM
    CADDY_MIDDLEWARE_CALLBACK_UPSTREAM
    CADDY_AGENT_GATEWAY_UPSTREAM
    CADDY_AGENT_UI_UPSTREAM
    CADDY_MONITORING_UPSTREAM
    CADDY_KLYROW_EVENTS_UPSTREAM
    CADDY_EDITOR_ADMIN_CIDRS
    CADDY_N8N_EDITOR_MAX_REQUEST_BODY
    CADDY_GRAFANA_UPSTREAM
    CADDY_SUPERSET_UPSTREAM
    CADDY_OPENBAO_UPSTREAM
    CADDY_OPENBAO_ALLOWED_CIDRS
  )
  local optional=(CADDY_DATA_DIR CADDY_CONFIG_DIR)
  for key in "${required[@]}" "${optional[@]}"; do allowed["$key"]=1; done

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || fail runtime_environment_syntax
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    [[ -n "${allowed[$key]:-}" ]] || fail "runtime_environment_key:$key"
    [[ -z "${seen[$key]:-}" ]] || fail "runtime_environment_duplicate:$key"
    [[ -n "$value" && "$value" != *$'\n'* ]] || fail "runtime_environment_value:$key"
    export "$key=$value"
    seen["$key"]=1
  done < "$RUNTIME_ENV_FILE"

  for key in "${required[@]}"; do
    [[ -n "${seen[$key]:-}" ]] || fail "runtime_environment_missing:$key"
  done
  export CADDY_DATA_DIR="${CADDY_DATA_DIR:-/var/lib/codestra/caddy/data}"
  export CADDY_CONFIG_DIR="${CADDY_CONFIG_DIR:-/var/lib/codestra/caddy/runtime-config}"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail dedicated_root_runner_required
[[ "${GITHUB_REF:-}" == refs/heads/production ]] || fail wrong_workflow_ref
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || fail invalid_image_digest
[[ "$IMAGE" == "ghcr.io/appolon1908-hue/codestra-caddy@$IMAGE_DIGEST" ]] || fail image_identity
[[ "$CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_config_sha256
for digest in "$RELEASE_EVIDENCE_SHA256" "$STAGING_EVIDENCE_SHA256" "$ROLLBACK_REHEARSAL_SHA256"; do
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || fail invalid_evidence_sha256
done
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN" "$JQ_BIN"; do trusted_executable "$binary"; done
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || fail validator_unavailable

[[ "$RUNTIME_ENV_FILE" = /* && -f "$RUNTIME_ENV_FILE" && ! -L "$RUNTIME_ENV_FILE" ]] || fail runtime_environment_file
[[ "$(stat -c '%u:%g:%a' -- "$RUNTIME_ENV_FILE")" == 0:0:600 ]] || fail runtime_environment_permissions
[[ -f "$READONLY_RECEIPT" && ! -L "$READONLY_RECEIPT" ]] || fail readonly_receipt_missing

GIT=(git -c "safe.directory=$ROOT" -C "$ROOT")
[[ "$(${GIT[@]} branch --show-current)" == production ]] || fail checkout_not_production
[[ "$(${GIT[@]} rev-parse HEAD)" == "$SOURCE_SHA" ]] || fail checkout_source_mismatch
[[ -z "$(${GIT[@]} status --porcelain)" ]] || fail dirty_worktree
[[ "$(python3 "$ROOT/scripts/hash_config_tree.py" "$ROOT/config")" == "$CONFIG_SHA256" ]] || fail source_config_mismatch
[[ -f "$ROOT/deploy/compose.runtime.yaml" ]] || fail unified_compose_missing

readonly_receipt_sha256="$(sha256sum "$READONLY_RECEIPT" | awk '{print $1}')"
"$JQ_BIN" -e \
  --arg source "$SOURCE_SHA" \
  --arg image "$IMAGE" \
  --arg digest "$IMAGE_DIGEST" \
  --arg config "$CONFIG_SHA256" \
  --arg release "$RELEASE_EVIDENCE_SHA256" \
  --arg staging "$STAGING_EVIDENCE_SHA256" \
  --arg rollback "$ROLLBACK_REHEARSAL_SHA256" '
    .schema == "codestra.caddy.manual-production-orchestrator-receipt.v1" and
    .source_sha == $source and .image == $image and .image_digest == $digest and
    .config_sha256 == $config and .release_evidence_sha256 == $release and
    .staging_evidence_sha256 == $staging and .rollback_evidence_sha256 == $rollback and
    .staging_certified == true and .rollback_rehearsed == true and
    .production_canary_read_only == true and .write_requests_sent == false and
    .public_traffic_changed == false and .full_live_activation_authorized == false and
    .verdict == "READ_ONLY_CANARY_PASS"
  ' "$READONLY_RECEIPT" >/dev/null || fail readonly_receipt_contract

load_runtime_environment
export CADDY_REVIEWED_SHA="$SOURCE_SHA"
export CADDY_IMAGE_SHA256="${IMAGE_DIGEST#sha256:}"
export CADDY_PRODUCTION_REMOTE_SHA="$SOURCE_SHA"
export CADDY_ROLLBACK_BASELINE_FILE="$BASELINE_FILE"
export CADDY_ROLLBACK_EVIDENCE_FILE="$ROLLBACK_RESULT_FILE"

phase=baseline_capture
set +e
bash "$ROOT/scripts/capture-runtime-baseline.sh" > baseline-capture.txt 2>&1
baseline_status=$?
set -e
cat baseline-capture.txt
if [[ "$baseline_status" -ne 0 ]]; then
  write_evidence NO_GO baseline_capture_failed false false
  exit 1
fi
[[ -f "$BASELINE_FILE" && ! -L "$BASELINE_FILE" ]] || fail baseline_not_written
baseline_sha256="$(sha256sum "$BASELINE_FILE" | awk '{print $1}')"

phase=activation
set +e
bash "$ROOT/scripts/run-immutable-runtime.sh" > "$ACTIVATION_LOG" 2>&1
activation_status=$?
set -e
cat "$ACTIVATION_LOG"
activation_output_sha256="$(sha256sum "$ACTIVATION_LOG" | awk '{print $1}')"
if [[ "$activation_status" -ne 0 ]]; then
  previous_restored=false
  if [[ -f "$ROLLBACK_RESULT_FILE" ]] && "$JQ_BIN" -e '.result == "PASS"' "$ROLLBACK_RESULT_FILE" >/dev/null 2>&1; then
    previous_restored=true
  fi
  write_evidence NO_GO activation_failed false "$previous_restored"
  exit 1
fi

grep -q '^CADDY_ACTIVATION=PASS$' "$ACTIVATION_LOG" || {
  write_evidence NO_GO activation_receipt_missing false false
  exit 1
}

phase=final_runtime_readback
"$PYTHON_BIN" "$VALIDATOR" > "$FINAL_RUNTIME"
final_runtime_sha256="$(sha256sum "$FINAL_RUNTIME" | awk '{print $1}')"
"$JQ_BIN" -e \
  --arg source "$SOURCE_SHA" \
  --arg digest "$IMAGE_DIGEST" \
  --arg config "$CONFIG_SHA256" '
    .schema == "codestra.caddy-container-validation.v2" and
    .source_sha == $source and .image_digest == $digest and .config_sha256 == $config and
    .container_running == true and .container_health == "healthy" and
    .config_validation == "PASS" and .config_identity == "PASS" and
    .listener_ownership == "CADDY_PROCESS_ONLY" and
    .effective_access_log_redaction == "PASS"
  ' "$FINAL_RUNTIME" >/dev/null || {
  set +e
  bash "$ROOT/scripts/rollback-runtime.sh" > final-readback-rollback.txt 2>&1
  rollback_exit=$?
  set -e
  cat final-readback-rollback.txt
  previous_restored=false
  [[ "$rollback_exit" -eq 0 ]] && previous_restored=true
  write_evidence NO_GO final_runtime_readback_failed false "$previous_restored"
  exit 1
}

phase=complete
write_evidence PASS NONE true false
printf 'CADDY_MANUAL_PRODUCTION_ACTIVATION=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nROLLBACK_BASELINE_SHA256=%s\n' \
  "$SOURCE_SHA" "$IMAGE" "$CONFIG_SHA256" "$baseline_sha256"
