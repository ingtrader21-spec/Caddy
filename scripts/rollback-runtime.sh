#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
DEFAULT_BASELINE="$ROOT/config/release-baseline.v1.json"
BASELINE="${CADDY_ROLLBACK_BASELINE_FILE:-$DEFAULT_BASELINE}"
ROLLBACK_EVIDENCE_FILE="${CADDY_ROLLBACK_EVIDENCE_FILE:-}"
DOCKER_BIN=/usr/bin/docker
COSIGN_BIN=/usr/local/bin/cosign
PYTHON_BIN=/usr/bin/python3
CERTIFICATE_IDENTITY_REGEXP='^https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release\.yml@refs/heads/production$'
CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'

fail() { printf 'CADDY_ROLLBACK=FAIL:%s\n' "$1" >&2; exit 2; }

trusted_executable() {
  local requested="$1" resolved owner mode mode_value
  resolved="$(readlink -f -- "$requested")"
  [[ -x "$requested" && -n "$resolved" && -x "$resolved" && ! -L "$resolved" ]] || fail "trusted_binary:$requested"
  owner="$(stat -c '%u:%g' -- "$resolved")"
  mode="$(stat -c '%a' -- "$resolved")"
  mode_value=$((8#$mode))
  [[ "$owner" == 0:0 ]] && (( (mode_value & 0022) == 0 )) || fail "binary_ownership:$requested"
}

load_environment_file() {
  local path="$1" line key value
  declare -A allowed=() seen=()
  local required=(
    CADDY_PUBLIC_BIND CADDY_PRIVATE_METRICS_BIND CADDY_PRIVATE_INGRESS_BIND
    CADDY_KLYROW_SOURCE_CIDRS CADDY_VICIDIAL_SOURCE_CIDRS CADDY_STAGING_EVENT_SOURCE_CIDRS
    CADDY_KONG_UPSTREAM CADDY_REALTIME_UPSTREAM CADDY_KEYCLOAK_UPSTREAM
    CADDY_CRM_RESELLER_UPSTREAM CADDY_CRM_UPSTREAM CADDY_N8N_UPSTREAM
    CADDY_N8N_STAGING_UPSTREAM CADDY_STAGING_API_UPSTREAM CADDY_STAGING_PORTAL_UPSTREAM
    CADDY_STAGING_KEYCLOAK_UPSTREAM CADDY_STAGING_ODOO_UPSTREAM CADDY_MIDDLEWARE_CALLBACK_UPSTREAM
    CADDY_AGENT_GATEWAY_UPSTREAM CADDY_AGENT_UI_UPSTREAM CADDY_MONITORING_UPSTREAM
    CADDY_KLYROW_EVENTS_UPSTREAM CADDY_EDITOR_ADMIN_CIDRS CADDY_N8N_EDITOR_MAX_REQUEST_BODY
    CADDY_GRAFANA_UPSTREAM CADDY_SUPERSET_UPSTREAM CADDY_OPENBAO_UPSTREAM CADDY_OPENBAO_ALLOWED_CIDRS
  )
  for key in "${required[@]}"; do allowed["$key"]=1; done
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || fail rollback_environment_syntax
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    [[ -n "${allowed[$key]:-}" && -z "${seen[$key]:-}" && -n "$value" ]] || fail "rollback_environment:$key"
    export "$key=$value"
    seen["$key"]=1
  done < "$path"
  for key in "${required[@]}"; do [[ -n "${seen[$key]:-}" ]] || fail "rollback_environment_missing:$key"; done
}

write_rollback_evidence() {
  local canary_sha="$1" completed_at="$2" payload
  [[ -n "$ROLLBACK_EVIDENCE_FILE" ]] || return 0
  [[ "$ROLLBACK_EVIDENCE_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-result\.json$ ]] || fail rollback_evidence_path
  payload="$(mktemp)"
  "$PYTHON_BIN" - "$payload" "$baseline_schema" "$baseline_source" "$baseline_image" "$computed_config_sha" \
    "$baseline_release_id" "$BASELINE" "$baseline_environment_sha" "$canary_sha" "$completed_at" <<'PY'
import json
import sys
from pathlib import Path

(path, schema, source, image, config, release_id, baseline_file,
 environment_sha, canary_sha, completed) = sys.argv[1:]
value = {
    "schema": "codestra.caddy-runtime-rollback-result.v1",
    "baseline_schema": schema,
    "source_sha": source,
    "image": image,
    "config_sha256": config,
    "release_id": release_id,
    "baseline_file": baseline_file,
    "runtime_environment_sha256": environment_sha,
    "canary_output_sha256": canary_sha,
    "completed_at": completed,
    "container": "codestra-caddy",
    "container_health": "healthy",
    "signature_verified": True,
    "source_readback": "PASS",
    "image_readback": "PASS",
    "config_readback": "PASS",
    "release_readback": "PASS",
    "production_canary": "PASS",
    "result": "PASS",
}
Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  install -d -m 0700 -o root -g root "$(dirname -- "$ROLLBACK_EVIDENCE_FILE")"
  install -m 0600 -o root -g root "$payload" "$ROLLBACK_EVIDENCE_FILE"
  rm -f -- "$payload"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN"; do trusted_executable "$binary"; done
[[ -f "$BASELINE" && ! -L "$BASELINE" ]] || fail baseline_file
if [[ "$BASELINE" != "$DEFAULT_BASELINE" ]]; then
  [[ "$BASELINE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline\.json$ ]] || fail dynamic_baseline_path
  [[ "$(stat -c '%u:%g:%a' -- "$BASELINE")" == 0:0:600 ]] || fail dynamic_baseline_permissions
fi

readarray -t baseline < <("$PYTHON_BIN" - "$BASELINE" <<'PY'
import json, re, sys
item = json.load(open(sys.argv[1], encoding="utf-8"))
schema = item.get("schema")
assert schema in {"codestra.caddy-release-baseline.v1", "codestra.caddy-runtime-rollback-baseline.v1"}
assert re.fullmatch(r"[0-9a-f]{40}", item.get("source_sha", ""))
assert re.fullmatch(r"ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}", item.get("image", ""))
assert item.get("mutable") is False
config = item.get("config_sha256", "")
release_id = item.get("release_id", f"rollback-{item['source_sha']}")
env_file = item.get("runtime_environment_file", "")
env_sha = item.get("runtime_environment_sha256", "")
data_dir = item.get("data_dir", "")
config_dir = item.get("config_dir", "")
if schema == "codestra.caddy-runtime-rollback-baseline.v1":
    assert re.fullmatch(r"[0-9a-f]{64}", config)
    assert release_id and re.fullmatch(r"[^\r\n]+", release_id)
    assert env_file.startswith("/var/lib/codestra/caddy/evidence/")
    assert re.fullmatch(r"[0-9a-f]{64}", env_sha)
    assert data_dir.startswith("/") and config_dir.startswith("/")
    assert item.get("container") == "codestra-caddy"
    assert item.get("container_running") is True
    assert item.get("container_health") == "healthy"
    assert item.get("signature_verified") is True
    assert item.get("listener_ownership") == "CADDY_PROCESS_ONLY"
    assert item.get("effective_access_log_redaction") == "PASS"
print(schema); print(item["source_sha"]); print(item["image"]); print(config); print(release_id)
print(env_file); print(env_sha); print(data_dir); print(config_dir)
PY
)
[[ ${#baseline[@]} -eq 9 ]] || fail baseline_contract
baseline_schema="${baseline[0]}"; baseline_source="${baseline[1]}"; baseline_image="${baseline[2]}"
baseline_config_expected="${baseline[3]}"; baseline_release_id="${baseline[4]}"
baseline_environment_file="${baseline[5]}"; baseline_environment_sha="${baseline[6]}"
baseline_data_dir="${baseline[7]}"; baseline_config_dir="${baseline[8]}"
baseline_digest="${baseline_image##*@sha256:}"

if [[ "$baseline_schema" == codestra.caddy-runtime-rollback-baseline.v1 ]]; then
  [[ -f "$baseline_environment_file" && ! -L "$baseline_environment_file" ]] || fail rollback_environment_file
  [[ "$(stat -c '%u:%g:%a' -- "$baseline_environment_file")" == 0:0:600 ]] || fail rollback_environment_permissions
  [[ "$(sha256sum "$baseline_environment_file" | awk '{print $1}')" == "$baseline_environment_sha" ]] || fail rollback_environment_checksum
  load_environment_file "$baseline_environment_file"
  export CADDY_DATA_DIR="$baseline_data_dir" CADDY_CONFIG_DIR="$baseline_config_dir"
fi

"$COSIGN_BIN" verify --certificate-identity-regexp "$CERTIFICATE_IDENTITY_REGEXP" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" "$baseline_image" >/dev/null
"$DOCKER_BIN" pull "$baseline_image" >/dev/null
image_source="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$baseline_image")"
image_revision="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$baseline_image")"
image_config_sha="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$baseline_image")"
[[ "$image_source" == https://github.com/appolon1908-hue/Caddy ]] || fail image_source
[[ "$image_revision" == "$baseline_source" ]] || fail image_revision
[[ "$image_config_sha" =~ ^[0-9a-f]{64}$ ]] || fail image_config_label
[[ -z "$baseline_config_expected" || "$image_config_sha" == "$baseline_config_expected" ]] || fail captured_config_mismatch

work="$(mktemp -d)"; probe="codestra-caddy-rollback-probe-$$"
cleanup() { "$DOCKER_BIN" rm -f "$probe" >/dev/null 2>&1 || true; rm -rf -- "$work"; }
trap cleanup EXIT
mkdir -p "$work/config"
"$DOCKER_BIN" create --name "$probe" "$baseline_image" >/dev/null
"$DOCKER_BIN" cp "$probe:/etc/caddy/." "$work/config"
computed_config_sha="$($PYTHON_BIN "$ROOT/scripts/hash_config_tree.py" "$work/config")"
[[ "$computed_config_sha" == "$image_config_sha" ]] || fail image_config_identity
[[ -z "$baseline_config_expected" || "$computed_config_sha" == "$baseline_config_expected" ]] || fail captured_config_identity

export CADDY_IMAGE_SHA256="$baseline_digest" CADDY_REVIEWED_SHA="$baseline_source"
export CADDY_CONFIG_SHA256="$computed_config_sha" CADDY_RELEASE_ID="$baseline_release_id"
"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet
"$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy
for _ in $(seq 1 60); do
  state="$($DOCKER_BIN inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"
  [[ "$state" == healthy ]] && break
  sleep 2
done
[[ "$($DOCKER_BIN inspect --format '{{.State.Health.Status}}' codestra-caddy 2>/dev/null || true)" == healthy ]] || fail unhealthy
final_image="$($DOCKER_BIN inspect --format '{{.Config.Image}}' codestra-caddy)"
final_source="$($DOCKER_BIN inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
final_config="$($DOCKER_BIN inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
final_release="$($DOCKER_BIN inspect --format '{{index .Config.Labels "io.codestra.caddy.release.id"}}' codestra-caddy)"
[[ "$final_image" == "$baseline_image" && "$final_source" == "$baseline_source" ]] || fail image_or_source_readback
[[ "$final_config" == "$computed_config_sha" && "$final_release" == "$baseline_release_id" ]] || fail config_or_release_readback
rollback_canary="$($ROOT/scripts/production-canary.sh)" || fail rollback_canary
rollback_canary_sha256="$(printf '%s' "$rollback_canary" | sha256sum | awk '{print $1}')"
write_rollback_evidence "$rollback_canary_sha256" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s\n' "$rollback_canary"
printf 'CADDY_ROLLBACK=PASS\nBASELINE_SCHEMA=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nRELEASE_ID=%s\nBASELINE_FILE=%s\n' \
  "$baseline_schema" "$baseline_source" "$baseline_image" "$computed_config_sha" "$baseline_release_id" "$BASELINE"
