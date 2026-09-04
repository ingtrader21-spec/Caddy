#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly FULL_CANARY="$ROOT/scripts/bounded-production-readonly-canary-v2.sh"
readonly EVIDENCE_DIR=/var/lib/codestra/caddy/evidence
readonly DOCKER_BIN=/usr/bin/docker
readonly PYTHON_BIN=/usr/bin/python3
readonly MTLS_CLIENT_CERT="${CADDY_PRODUCTION_MTLS_CLIENT_CERT:-}"
readonly MTLS_CLIENT_KEY="${CADDY_PRODUCTION_MTLS_CLIENT_KEY:-}"
readonly MTLS_CA_CERT="${CADDY_PRODUCTION_MTLS_CA_CERT:-}"

fail() {
  printf 'CADDY_PRODUCTION_CANARY=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || fail validator_unavailable
[[ -x "$FULL_CANARY" && ! -L "$FULL_CANARY" ]] || fail full_canary_unavailable
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || fail dirty_worktree
[[ "$(git -C "$ROOT" branch --show-current)" == production ]] || fail wrong_branch
for path in "$MTLS_CLIENT_CERT" "$MTLS_CLIENT_KEY" "$MTLS_CA_CERT"; do
  [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]] || fail "unsafe_mtls_path:${path##*/}"
  [[ -f "$path" && ! -L "$path" && -r "$path" ]] || fail "invalid_mtls_file:${path##*/}"
done

root_prefix=()
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 || fail root_evidence_access
  root_prefix=(sudo -n)
fi
as_root() { "${root_prefix[@]}" "$@"; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="$(mktemp)"
work="$(mktemp -d)"
cleanup() { rm -f -- "$temporary"; rm -rf -- "$work"; }
trap cleanup EXIT

"$PYTHON_BIN" "$VALIDATOR" >"$temporary"
"$PYTHON_BIN" - "$temporary" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data.get("schema") == "codestra.caddy-container-validation.v2"
assert data.get("config_validation") == "PASS"
assert data.get("config_identity") == "PASS"
assert data.get("container_running") is True
assert data.get("container_health") == "healthy"
assert data.get("caddy_process_count") == 1
assert data.get("listener_ownership") == "CADDY_PROCESS_ONLY"
assert data.get("effective_access_log_redaction") == "PASS"
assert int(data.get("effective_access_log_count") or 0) >= 5
listeners = set(data.get("listeners") or [])
requirements = (
    ("tcp/", ":80@caddy-pid"),
    ("tcp/", ":443@caddy-pid"),
    ("udp/", ":443@caddy-pid"),
    ("tcp/", ":2020@caddy-pid"),
    ("tcp/", ":18080@caddy-pid"),
)
for prefix, suffix in requirements:
    assert any(item.startswith(prefix) and item.endswith(suffix) for item in listeners), (
        prefix,
        suffix,
        listeners,
    )
PY

# Read back the exact immutable tuple and public bind from the newly running
# container without printing protected environment values.
actual_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
actual_source="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
actual_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
public_bind="$("$DOCKER_BIN" inspect --format '{{range .Config.Env}}{{println .}}{{end}}' codestra-caddy | sed -n 's/^CADDY_PUBLIC_BIND=//p' | head -n1)"
[[ "$actual_image" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail actual_image
[[ "$actual_source" =~ ^[0-9a-f]{40}$ ]] || fail actual_source
[[ "$actual_config" =~ ^[0-9a-f]{64}$ ]] || fail actual_config
[[ "$public_bind" =~ ^[0-9A-Fa-f:.]+$ ]] || fail public_bind

http3_output="$("$DOCKER_BIN" exec codestra-caddy /usr/bin/codestra-http3-probe api.codestra.co "$public_bind" /api/v1/health)"
grep -q '^CADDY_HTTP3_CANARY=PASS ' <<<"$http3_output" || fail http3

# Re-run the complete fixed-target production suite only after the replacement
# container is healthy. Any failure propagates to run-immutable-runtime.sh,
# which invokes the signed rollback path.
set +e
(
  cd "$work"
  export CADDY_PRODUCTION_CANARY_MODE=post-activation
  export CADDY_CANARY_IMAGE="$actual_image"
  export CADDY_CANARY_SOURCE_SHA="$actual_source"
  export CADDY_CANARY_CONFIG_SHA256="$actual_config"
  export CADDY_PRODUCTION_MTLS_CLIENT_CERT="$MTLS_CLIENT_CERT"
  export CADDY_PRODUCTION_MTLS_CLIENT_KEY="$MTLS_CLIENT_KEY"
  export CADDY_PRODUCTION_MTLS_CA_CERT="$MTLS_CA_CERT"
  "$FULL_CANARY"
) >"$work/post-activation-canary.txt" 2>&1
full_canary_status=$?
set -e
cat "$work/post-activation-canary.txt"
[[ "$full_canary_status" -eq 0 ]] || fail post_activation_full_canary

for file in \
  production-canary-evidence.json \
  pre-canary-runtime.json \
  post-canary-runtime.json; do
  [[ -s "$work/$file" && ! -L "$work/$file" ]] || fail "post_activation_evidence_missing:$file"
done

"$PYTHON_BIN" - \
  "$work/production-canary-evidence.json" \
  "$actual_source" \
  "$actual_image" \
  "$actual_config" <<'PY'
import json
import sys
from pathlib import Path

path, source_sha, image, config_sha256 = sys.argv[1:]
value = json.loads(Path(path).read_text(encoding="utf-8"))
assert value["schema"] == "codestra.caddy.production-readonly-canary.v2"
assert value["canary_mode"] == "post-activation"
assert value["candidate_source_sha"] == source_sha
assert value["candidate_image"] == image
assert value["candidate_config_sha256"] == config_sha256
assert value["live_source_sha"] == source_sha
assert value["live_image_digest"] == image.rsplit("@", 1)[1]
assert value["live_config_sha256"] == config_sha256
assert value["live_runtime_is_candidate"] is True
assert value["candidate_started_on_production"] is True
assert value["live_runtime_unchanged"] is True
assert value["live_mtls_server_certificate_verified"] is True
assert value["live_mtls_handshake_and_denial"] == "PASS"
assert value["write_requests_sent"] is False
assert value["public_traffic_changed"] is False
assert value["result"] == "PASS"
PY

post_activation_sha256="$(sha256sum "$work/production-canary-evidence.json" | awk '{print $1}')"
"$PYTHON_BIN" - "$temporary" "$post_activation_sha256" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["http3_canary"] = "PASS"
data["http3_host"] = "api.codestra.co"
data["full_post_activation_canary"] = "PASS"
data["post_activation_canary_sha256"] = sys.argv[2]
path.write_text(
    json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

install -m 0600 "$work/production-canary-evidence.json" post-activation-canary-evidence.json
install -m 0600 "$work/pre-canary-runtime.json" post-activation-runtime-before.json
install -m 0600 "$work/post-canary-runtime.json" post-activation-runtime-after.json
install -m 0600 "$work/post-activation-canary.txt" post-activation-canary.txt

as_root install -d -m 0700 "$EVIDENCE_DIR"
final="$EVIDENCE_DIR/caddy-production-canary-$stamp.json"
as_root install -m 0600 "$temporary" "$final"
rm -f -- "$temporary"
trap 'rm -rf -- "$work"' EXIT

printf '%s\n' "$http3_output"
printf 'CADDY_PRODUCTION_CANARY=PASS\nEVIDENCE=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nPOST_ACTIVATION_CANARY_SHA256=%s\nLISTENER_OWNERSHIP=CADDY_PROCESS_ONLY\nEFFECTIVE_LOG_REDACTION=PASS\nHTTP3=PASS\nFULL_POST_ACTIVATION_CANARY=PASS\n' \
  "$final" "$actual_source" "$actual_image" "$actual_config" "$post_activation_sha256"
