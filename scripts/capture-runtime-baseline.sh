#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly DOCKER_BIN=/usr/bin/docker
readonly COSIGN_BIN=/usr/local/bin/cosign
readonly PYTHON_BIN=/usr/bin/python3
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly BASELINE_FILE="${CADDY_ROLLBACK_BASELINE_FILE:-}"
readonly CERTIFICATE_IDENTITY_REGEXP='^https://github.com/appolon1908-hue/Caddy/.github/workflows/(immutable-release|manual-production-orchestrator)\.yml@refs/heads/production$'
readonly CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'

fail() {
  printf 'CADDY_BASELINE_CAPTURE=FAIL:%s\n' "$1" >&2
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
  [[ "$owner" == '0:0' ]] && (( (mode_value & 0022) == 0 )) || \
    fail "executable_ownership:$requested"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required
[[ "$BASELINE_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline\.json$ ]] || \
  fail invalid_baseline_path
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || fail validator_unavailable
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN"; do
  trusted_executable "$binary"
done

state="$($DOCKER_BIN inspect --format '{{.State.Status}}' codestra-caddy 2>/dev/null || true)"
health="$($DOCKER_BIN inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"
[[ "$state" == running ]] || fail live_container_not_running
[[ "$health" == healthy ]] || fail live_container_not_healthy

image="$($DOCKER_BIN inspect --format '{{.Config.Image}}' codestra-caddy)"
source_sha="$($DOCKER_BIN inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
config_sha256="$($DOCKER_BIN inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
[[ "$image" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail live_image_not_immutable
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || fail live_source_sha
[[ "$config_sha256" =~ ^[0-9a-f]{64}$ ]] || fail live_config_sha256

"$DOCKER_BIN" pull "$image" >/dev/null
"$COSIGN_BIN" verify \
  --certificate-identity-regexp "$CERTIFICATE_IDENTITY_REGEXP" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$image" >/dev/null

image_source="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$image")"
image_revision="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
image_config="$($DOCKER_BIN image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$image")"
[[ "$image_source" == https://github.com/appolon1908-hue/Caddy ]] || fail image_source
[[ "$image_revision" == "$source_sha" ]] || fail image_revision
[[ "$image_config" == "$config_sha256" ]] || fail image_config

validation="$(mktemp)"
payload="$(mktemp)"
cleanup() { rm -f -- "$validation" "$payload"; }
trap cleanup EXIT
"$PYTHON_BIN" "$VALIDATOR" >"$validation"
validation_sha256="$(sha256sum "$validation" | awk '{print $1}')"
"$PYTHON_BIN" - "$validation" "$source_sha" "$image" "$config_sha256" <<'PY'
import json
import sys
from pathlib import Path

path, source, image, config = sys.argv[1:]
value = json.loads(Path(path).read_text(encoding="utf-8"))
assert value.get("schema") == "codestra.caddy-container-validation.v2"
assert value.get("source_sha") == source
assert value.get("image_reference") == image or value.get("image_digest") in image
assert value.get("config_sha256") == config
assert value.get("container_running") is True
assert value.get("container_health") == "healthy"
assert value.get("config_validation") == "PASS"
assert value.get("config_identity") == "PASS"
assert value.get("listener_ownership") == "CADDY_PROCESS_ONLY"
assert value.get("effective_access_log_redaction") == "PASS"
PY

captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PYTHON_BIN" - "$payload" "$source_sha" "$image" "$config_sha256" "$validation_sha256" "$captured_at" <<'PY'
import json
import sys
from pathlib import Path

path, source, image, config, validation, captured = sys.argv[1:]
value = {
    "schema": "codestra.caddy-runtime-rollback-baseline.v1",
    "source_sha": source,
    "image": image,
    "config_sha256": config,
    "validator_sha256": validation,
    "captured_at": captured,
    "container": "codestra-caddy",
    "container_running": True,
    "container_health": "healthy",
    "signature_verified": True,
    "listener_ownership": "CADDY_PROCESS_ONLY",
    "effective_access_log_redaction": "PASS",
    "mutable": False,
}
Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

install -d -m 0700 -o root -g root "$(dirname -- "$BASELINE_FILE")"
install -m 0600 -o root -g root "$payload" "$BASELINE_FILE"
[[ "$(stat -c '%u:%g:%a' -- "$BASELINE_FILE")" == 0:0:600 ]] || fail baseline_permissions

printf 'CADDY_BASELINE_CAPTURE=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nBASELINE_FILE=%s\nVALIDATOR_SHA256=%s\n' \
  "$source_sha" "$image" "$config_sha256" "$BASELINE_FILE" "$validation_sha256"
