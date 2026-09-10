#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly DOCKER_BIN=/usr/bin/docker
readonly COSIGN_BIN=/usr/local/bin/cosign
readonly PYTHON_BIN=/usr/bin/python3
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly BASELINE_FILE="${CADDY_ROLLBACK_BASELINE_FILE:-}"
readonly ENVIRONMENT_FILE="${BASELINE_FILE%.json}-runtime.env"
readonly CERTIFICATE_IDENTITY_REGEXP='^https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release\.yml@refs/heads/production$'
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
  [[ "$owner" == 0:0 ]] && (( (mode_value & 0022) == 0 )) || \
    fail "executable_ownership:$requested"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required
[[ "$BASELINE_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline\.json$ ]] || \
  fail invalid_baseline_path
[[ "$ENVIRONMENT_FILE" =~ ^/var/lib/codestra/caddy/evidence/caddy-orchestrator-[A-Za-z0-9._-]+-rollback-baseline-runtime\.env$ ]] || \
  fail invalid_environment_path
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || fail validator_unavailable
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN"; do trusted_executable "$binary"; done

inspect="$(mktemp)"
validation="$(mktemp)"
payload="$(mktemp)"
environment_payload="$(mktemp)"
cleanup() { rm -f -- "$inspect" "$validation" "$payload" "$environment_payload"; }
trap cleanup EXIT
"$DOCKER_BIN" inspect codestra-caddy > "$inspect"

readarray -t runtime < <("$PYTHON_BIN" - "$inspect" "$environment_payload" <<'PY'
import json
import re
import sys
from pathlib import Path

inspect_path, environment_path = sys.argv[1:]
items = json.loads(Path(inspect_path).read_text(encoding="utf-8"))
assert len(items) == 1
container = items[0]
state = container.get("State") or {}
health = (state.get("Health") or {}).get("Status")
assert state.get("Running") is True
assert health == "healthy"
config = container.get("Config") or {}
labels = config.get("Labels") or {}
image = config.get("Image") or ""
source = labels.get("io.codestra.caddy.source.sha") or ""
config_sha = labels.get("io.codestra.caddy.config.sha256") or ""
release_id = labels.get("io.codestra.caddy.release.id") or ""
assert re.fullmatch(r"ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}", image)
assert re.fullmatch(r"[0-9a-f]{40}", source)
assert re.fullmatch(r"[0-9a-f]{64}", config_sha)
assert release_id and "\n" not in release_id
required = {
    "CADDY_PUBLIC_BIND", "CADDY_PRIVATE_METRICS_BIND", "CADDY_PRIVATE_INGRESS_BIND",
    "CADDY_KLYROW_SOURCE_CIDRS", "CADDY_VICIDIAL_SOURCE_CIDRS",
    "CADDY_STAGING_EVENT_SOURCE_CIDRS", "CADDY_KONG_UPSTREAM",
    "CADDY_REALTIME_UPSTREAM", "CADDY_KEYCLOAK_UPSTREAM",
    "CADDY_CRM_RESELLER_UPSTREAM", "CADDY_CRM_UPSTREAM", "CADDY_N8N_UPSTREAM",
    "CADDY_N8N_STAGING_UPSTREAM", "CADDY_STAGING_API_UPSTREAM",
    "CADDY_STAGING_PORTAL_UPSTREAM", "CADDY_STAGING_KEYCLOAK_UPSTREAM",
    "CADDY_STAGING_ODOO_UPSTREAM", "CADDY_MIDDLEWARE_CALLBACK_UPSTREAM",
    "CADDY_AGENT_GATEWAY_UPSTREAM", "CADDY_AGENT_UI_UPSTREAM",
    "CADDY_MONITORING_UPSTREAM", "CADDY_KLYROW_EVENTS_UPSTREAM",
    "CADDY_EDITOR_ADMIN_CIDRS", "CADDY_N8N_EDITOR_MAX_REQUEST_BODY",
    "CADDY_GRAFANA_UPSTREAM", "CADDY_SUPERSET_UPSTREAM", "CADDY_OPENBAO_UPSTREAM",
    "CADDY_OPENBAO_ALLOWED_CIDRS",
}
optional = {"CADDY_STAGING_KONG_UPSTREAM", "CADDY_GLITCHTIP_UPSTREAM"}
environment = {}
for entry in config.get("Env") or []:
    if "=" not in entry:
        continue
    key, value = entry.split("=", 1)
    if key in required | optional:
        assert value and "\n" not in value and "\r" not in value
        environment[key] = value
assert required <= set(environment) <= required | optional
Path(environment_path).write_text(
    "".join(f"{key}={environment[key]}\n" for key in sorted(environment)),
    encoding="utf-8",
)
mounts = {item.get("Destination"): item.get("Source") for item in container.get("Mounts") or []}
data_dir = mounts.get("/data") or ""
config_dir = mounts.get("/config") or ""
assert data_dir.startswith("/") and config_dir.startswith("/")
print(image)
print(source)
print(config_sha)
print(release_id)
print(data_dir)
print(config_dir)
PY
)
[[ ${#runtime[@]} -eq 6 ]] || fail live_runtime_contract
image="${runtime[0]}"
source_sha="${runtime[1]}"
config_sha256="${runtime[2]}"
release_id="${runtime[3]}"
data_dir="${runtime[4]}"
config_dir="${runtime[5]}"

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

"$PYTHON_BIN" "$VALIDATOR" > "$validation"
validation_sha256="$(sha256sum "$validation" | awk '{print $1}')"
"$PYTHON_BIN" - "$validation" "$source_sha" "$image" "$config_sha256" <<'PY'
import json
import sys
from pathlib import Path

path, source, image, config = sys.argv[1:]
value = json.loads(Path(path).read_text(encoding="utf-8"))
assert value.get("schema") == "codestra.caddy-container-validation.v2"
assert value.get("source_sha") == source
assert value.get("image_digest") and image.endswith("@" + value["image_digest"])
assert value.get("config_sha256") == config
assert value.get("container_running") is True
assert value.get("container_health") == "healthy"
assert value.get("config_validation") == "PASS"
assert value.get("config_identity") == "PASS"
assert value.get("listener_ownership") == "CADDY_PROCESS_ONLY"
assert value.get("effective_access_log_redaction") == "PASS"
PY

environment_sha256="$(sha256sum "$environment_payload" | awk '{print $1}')"
captured_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PYTHON_BIN" - "$payload" "$source_sha" "$image" "$config_sha256" "$release_id" \
  "$validation_sha256" "$ENVIRONMENT_FILE" "$environment_sha256" "$data_dir" "$config_dir" "$captured_at" <<'PY'
import json
import sys
from pathlib import Path

(path, source, image, config, release_id, validation, environment_file,
 environment_sha, data_dir, config_dir, captured) = sys.argv[1:]
value = {
    "schema": "codestra.caddy-runtime-rollback-baseline.v1",
    "source_sha": source,
    "image": image,
    "config_sha256": config,
    "release_id": release_id,
    "validator_sha256": validation,
    "runtime_environment_file": environment_file,
    "runtime_environment_sha256": environment_sha,
    "data_dir": data_dir,
    "config_dir": config_dir,
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
install -m 0600 -o root -g root "$environment_payload" "$ENVIRONMENT_FILE"
install -m 0600 -o root -g root "$payload" "$BASELINE_FILE"
[[ "$(stat -c '%u:%g:%a' -- "$BASELINE_FILE")" == 0:0:600 ]] || fail baseline_permissions
[[ "$(stat -c '%u:%g:%a' -- "$ENVIRONMENT_FILE")" == 0:0:600 ]] || fail environment_permissions

printf 'CADDY_BASELINE_CAPTURE=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nRELEASE_ID=%s\nBASELINE_FILE=%s\nENVIRONMENT_SHA256=%s\nVALIDATOR_SHA256=%s\n' \
  "$source_sha" "$image" "$config_sha256" "$release_id" "$BASELINE_FILE" "$environment_sha256" "$validation_sha256"
