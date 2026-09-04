#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
DEFAULT_BASELINE="$ROOT/config/release-baseline.v1.json"
BASELINE="${CADDY_ROLLBACK_BASELINE_FILE:-$DEFAULT_BASELINE}"
DOCKER_BIN='/usr/bin/docker'
COSIGN_BIN='/usr/local/bin/cosign'
PYTHON_BIN='/usr/bin/python3'
CERTIFICATE_IDENTITY_REGEXP='^https://github.com/appolon1908-hue/Caddy/.github/workflows/(immutable-release|manual-production-orchestrator)\.yml@refs/heads/production$'
CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'

fail() {
  printf 'CADDY_ROLLBACK=FAIL:%s\n' "$1" >&2
  exit 2
}

trusted_executable() {
  local requested="$1" resolved owner mode mode_value
  resolved="$(readlink -f -- "$requested")"
  [[ -x "$requested" && -n "$resolved" && -x "$resolved" && ! -L "$resolved" ]] || \
    fail "trusted_binary:$requested"
  owner="$(stat -c '%u:%g' -- "$resolved")"
  mode="$(stat -c '%a' -- "$resolved")"
  mode_value=$((8#$mode))
  [[ "$owner" == '0:0' ]] && (( (mode_value & 0022) == 0 )) || \
    fail "binary_ownership:$requested"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN"; do
  trusted_executable "$binary"
done
[[ -f "$BASELINE" && ! -L "$BASELINE" ]] || fail baseline_file
if [[ "$BASELINE" != "$DEFAULT_BASELINE" ]]; then
  [[ "$BASELINE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline\.json$ ]] || \
    fail dynamic_baseline_path
  [[ "$(stat -c '%u:%g:%a' -- "$BASELINE")" == 0:0:600 ]] || fail dynamic_baseline_permissions
fi

readarray -t baseline < <("$PYTHON_BIN" - "$BASELINE" <<'PY'
import json
import re
import sys

item = json.load(open(sys.argv[1], encoding="utf-8"))
schema = item.get("schema")
assert schema in {
    "codestra.caddy-release-baseline.v1",
    "codestra.caddy-runtime-rollback-baseline.v1",
}
assert re.fullmatch(r"[0-9a-f]{40}", item.get("source_sha", ""))
assert re.fullmatch(
    r"ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}",
    item.get("image", ""),
)
assert item.get("mutable") is False
config = item.get("config_sha256", "")
if schema == "codestra.caddy-runtime-rollback-baseline.v1":
    assert re.fullmatch(r"[0-9a-f]{64}", config)
    assert item.get("container") == "codestra-caddy"
    assert item.get("container_running") is True
    assert item.get("container_health") == "healthy"
    assert item.get("signature_verified") is True
    assert item.get("listener_ownership") == "CADDY_PROCESS_ONLY"
    assert item.get("effective_access_log_redaction") == "PASS"
print(schema)
print(item["source_sha"])
print(item["image"])
print(config)
PY
)
[[ ${#baseline[@]} -eq 4 ]] || fail baseline_contract
baseline_schema="${baseline[0]}"
baseline_source="${baseline[1]}"
baseline_image="${baseline[2]}"
baseline_config_expected="${baseline[3]}"
baseline_digest="${baseline_image##*@sha256:}"

"$COSIGN_BIN" verify \
  --certificate-identity-regexp "$CERTIFICATE_IDENTITY_REGEXP" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$baseline_image" >/dev/null
"$DOCKER_BIN" pull "$baseline_image" >/dev/null
image_source="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$baseline_image")"
image_revision="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$baseline_image")"
image_config_sha="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$baseline_image")"
[[ "$image_source" == 'https://github.com/appolon1908-hue/Caddy' ]] || fail image_source
[[ "$image_revision" == "$baseline_source" ]] || fail image_revision
[[ "$image_config_sha" =~ ^[0-9a-f]{64}$ ]] || fail image_config_label
if [[ -n "$baseline_config_expected" ]]; then
  [[ "$image_config_sha" == "$baseline_config_expected" ]] || fail captured_config_mismatch
fi

work="$(mktemp -d)"
probe="codestra-caddy-rollback-probe-$$"
cleanup() {
  "$DOCKER_BIN" rm -f "$probe" >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT
mkdir -p "$work/config"
"$DOCKER_BIN" create --name "$probe" "$baseline_image" >/dev/null
"$DOCKER_BIN" cp "$probe:/etc/caddy/." "$work/config"
computed_config_sha="$($PYTHON_BIN "$ROOT/scripts/hash_config_tree.py" "$work/config")"
[[ "$computed_config_sha" == "$image_config_sha" ]] || fail image_config_identity
if [[ -n "$baseline_config_expected" ]]; then
  [[ "$computed_config_sha" == "$baseline_config_expected" ]] || fail captured_config_identity
fi

export CADDY_IMAGE_SHA256="$baseline_digest"
export CADDY_REVIEWED_SHA="$baseline_source"
export CADDY_CONFIG_SHA256="$computed_config_sha"
export CADDY_RELEASE_ID="rollback-$baseline_source"
"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet
"$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy

for _ in $(seq 1 60); do
  state="$("$DOCKER_BIN" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"
  [[ "$state" == healthy ]] && break
  sleep 2
done
[[ "$("$DOCKER_BIN" inspect --format '{{.State.Health.Status}}' codestra-caddy 2>/dev/null || true)" == healthy ]] || fail unhealthy

final_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
final_source="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
final_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
[[ "$final_image" == "$baseline_image" ]] || fail image_readback
[[ "$final_source" == "$baseline_source" ]] || fail source_readback
[[ "$final_config" == "$computed_config_sha" ]] || fail config_readback

rollback_canary="$($ROOT/scripts/production-canary.sh)" || fail rollback_canary
printf '%s\n' "$rollback_canary"
printf 'CADDY_ROLLBACK=PASS\nBASELINE_SCHEMA=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nBASELINE_FILE=%s\n' \
  "$baseline_schema" "$baseline_source" "$baseline_image" "$computed_config_sha" "$BASELINE"
