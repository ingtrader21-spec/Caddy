#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly FULL_CANARY="$ROOT/scripts/bounded-production-readonly-canary-v2.sh"
readonly EVIDENCE_DIR=/var/lib/codestra/caddy/evidence
readonly OUTPUT_DIR="$ROOT/activation-evidence"
readonly DOCKER_BIN=/usr/bin/docker
readonly PYTHON_BIN=/usr/bin/python3
readonly MTLS_CLIENT_CERT="${CADDY_PRODUCTION_MTLS_CLIENT_CERT:-}"
readonly MTLS_CLIENT_KEY="${CADDY_PRODUCTION_MTLS_CLIENT_KEY:-}"
readonly MTLS_CA_CERT="${CADDY_PRODUCTION_MTLS_CA_CERT:-}"
readonly CANARY_MODE="${CADDY_PRODUCTION_CANARY_MODE:-post-activation}"
readonly ROLLBACK_ATTESTATION_FILE="${CADDY_ROLLBACK_ATTESTATION_FILE:-}"
readonly ROLLBACK_ATTESTATION_VERIFICATION_FILE="${CADDY_ROLLBACK_ATTESTATION_VERIFICATION_FILE:-}"

fail() {
  printf 'CADDY_PRODUCTION_CANARY=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
case "$CANARY_MODE" in
  post-activation|rollback) ;;
  *) fail invalid_canary_mode ;;
esac
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || fail validator_unavailable
[[ -x "$FULL_CANARY" && ! -L "$FULL_CANARY" ]] || fail full_canary_unavailable
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || fail dirty_worktree
[[ "$(git -C "$ROOT" branch --show-current)" == production ]] || fail wrong_branch
for path in "$MTLS_CLIENT_CERT" "$MTLS_CLIENT_KEY" "$MTLS_CA_CERT"; do
  [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]] || fail "unsafe_mtls_path:${path##*/}"
  [[ -f "$path" && ! -L "$path" && -r "$path" ]] || fail "invalid_mtls_file:${path##*/}"
done
if [[ "$CANARY_MODE" == rollback ]]; then
  for path in "$ROLLBACK_ATTESTATION_FILE" "$ROLLBACK_ATTESTATION_VERIFICATION_FILE"; do
    [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]] || fail rollback_attestation_path
    [[ -f "$path" && ! -L "$path" && -r "$path" ]] || fail rollback_attestation_file
    [[ "$(stat -c '%u:%g:%a' -- "$path")" == 0:0:600 ]] || fail rollback_attestation_permissions
  done
  grep -Fxq 'CADDY_SOURCE_ATTESTATION=PASS' "$ROLLBACK_ATTESTATION_VERIFICATION_FILE" || \
    fail rollback_attestation_verification
else
  [[ -z "$ROLLBACK_ATTESTATION_FILE" && -z "$ROLLBACK_ATTESTATION_VERIFICATION_FILE" ]] || \
    fail unexpected_rollback_attestation
fi
if [[ -e "$OUTPUT_DIR" ]]; then
  [[ -d "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || fail evidence_output_directory
fi
install -d -m 0700 "$OUTPUT_DIR"
cd "$ROOT"

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

# Read back the exact immutable tuple and public bind from the running container
# without printing protected environment values.
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

# Re-run the complete fixed-target production suite after replacement or
# restoration. Rollback mode validates the restored signed image independently
# of the still-candidate repository checkout.
set +e
(
  cd "$work"
  export CADDY_PRODUCTION_CANARY_MODE="$CANARY_MODE"
  export CADDY_CANARY_IMAGE="$actual_image"
  export CADDY_CANARY_SOURCE_SHA="$actual_source"
  export CADDY_CANARY_CONFIG_SHA256="$actual_config"
  export CADDY_PRODUCTION_MTLS_CLIENT_CERT="$MTLS_CLIENT_CERT"
  export CADDY_PRODUCTION_MTLS_CLIENT_KEY="$MTLS_CLIENT_KEY"
  export CADDY_PRODUCTION_MTLS_CA_CERT="$MTLS_CA_CERT"
  "$FULL_CANARY"
) >"$work/full-canary.txt" 2>&1
full_canary_status=$?
set -e
cat "$work/full-canary.txt"
[[ "$full_canary_status" -eq 0 ]] || fail "${CANARY_MODE}_full_canary"

for file in \
  production-canary-evidence.json \
  pre-canary-runtime.json \
  post-canary-runtime.json; do
  [[ -s "$work/$file" && ! -L "$work/$file" ]] || fail "full_canary_evidence_missing:$file"
done

"$PYTHON_BIN" - \
  "$work/production-canary-evidence.json" \
  "$CANARY_MODE" \
  "$actual_source" \
  "$actual_image" \
  "$actual_config" <<'PY'
import json
import sys
from pathlib import Path

path, mode, source_sha, image, config_sha256 = sys.argv[1:]
value = json.loads(Path(path).read_text(encoding="utf-8"))
post_activation = mode == "post-activation"
rollback = mode == "rollback"
expected_staging = "NOT_APPLICABLE" if rollback else "PASS"
assert value["schema"] == "codestra.caddy.production-readonly-canary.v2"
assert value["canary_mode"] == mode
assert value["candidate_source_sha"] == source_sha
assert value["candidate_image"] == image
assert value["candidate_config_sha256"] == config_sha256
assert value["expected_source_sha"] == source_sha
assert value["expected_image"] == image
assert value["expected_config_sha256"] == config_sha256
assert value["expected_image_config_sha256"] == config_sha256
assert value["bounded_staging_runtime"] == expected_staging
assert value["live_source_sha"] == source_sha
assert value["live_image_digest"] == image.rsplit("@", 1)[1]
assert value["live_config_sha256"] == config_sha256
assert value["live_runtime_is_expected_tuple"] is True
assert value["live_runtime_is_candidate"] is post_activation
assert value["rollback_validation"] is rollback
assert value["candidate_started_on_production"] is post_activation
assert value["live_runtime_unchanged"] is True
assert value["live_mtls_server_certificate_verified"] is True
assert value["live_mtls_handshake_and_denial"] == "PASS"
assert value["write_requests_sent"] is False
assert value["public_traffic_changed"] is False
assert value["result"] == "PASS"
PY

full_canary_sha256="$(sha256sum "$work/production-canary-evidence.json" | awk '{print $1}')"
if [[ "$CANARY_MODE" == post-activation ]]; then
  evidence_prefix=post-activation
else
  evidence_prefix=rollback
fi
evidence_name="${evidence_prefix}-canary-evidence.json"
before_name="${evidence_prefix}-canary-runtime-before.json"
after_name="${evidence_prefix}-canary-runtime-after.json"
log_name="${evidence_prefix}-canary.txt"
manifest_name="${evidence_prefix}-canary.SHA256SUMS"
rollback_attestation_name=rollback-source-attestation.verified.json
rollback_attestation_verification_name=rollback-source-attestation-verification.txt
install -m 0600 "$work/production-canary-evidence.json" "$OUTPUT_DIR/$evidence_name"
install -m 0600 "$work/pre-canary-runtime.json" "$OUTPUT_DIR/$before_name"
install -m 0600 "$work/post-canary-runtime.json" "$OUTPUT_DIR/$after_name"
install -m 0600 "$work/full-canary.txt" "$OUTPUT_DIR/$log_name"
manifest_files=("$evidence_name" "$before_name" "$after_name" "$log_name")
rollback_attestation_sha256=NOT_APPLICABLE
rollback_attestation_verification_sha256=NOT_APPLICABLE
if [[ "$CANARY_MODE" == rollback ]]; then
  install -m 0600 "$ROLLBACK_ATTESTATION_FILE" "$OUTPUT_DIR/$rollback_attestation_name"
  install -m 0600 "$ROLLBACK_ATTESTATION_VERIFICATION_FILE" "$OUTPUT_DIR/$rollback_attestation_verification_name"
  manifest_files+=("$rollback_attestation_name" "$rollback_attestation_verification_name")
  rollback_attestation_sha256="$(sha256sum "$OUTPUT_DIR/$rollback_attestation_name" | awk '{print $1}')"
  rollback_attestation_verification_sha256="$(sha256sum "$OUTPUT_DIR/$rollback_attestation_verification_name" | awk '{print $1}')"
fi
(
  cd "$OUTPUT_DIR"
  sha256sum "${manifest_files[@]}" >"$manifest_name.tmp"
  mv -f "$manifest_name.tmp" "$manifest_name"
  sha256sum --check --strict "$manifest_name"
)
packet_manifest_sha256="$(sha256sum "$OUTPUT_DIR/$manifest_name" | awk '{print $1}')"

# Keep compatibility copies for the activation wrapper while the complete,
# checksummed packet remains staged in activation-evidence/ for artifact upload.
install -m 0600 "$OUTPUT_DIR/$evidence_name" "$ROOT/$evidence_name"
install -m 0600 "$OUTPUT_DIR/$before_name" "$ROOT/$before_name"
install -m 0600 "$OUTPUT_DIR/$after_name" "$ROOT/$after_name"
install -m 0600 "$OUTPUT_DIR/$log_name" "$ROOT/$log_name"
install -m 0600 "$OUTPUT_DIR/$manifest_name" "$ROOT/$manifest_name"

"$PYTHON_BIN" - "$temporary" "$CANARY_MODE" "$full_canary_sha256" "$packet_manifest_sha256" \
  "$rollback_attestation_sha256" "$rollback_attestation_verification_sha256" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
(
    mode,
    evidence_sha256,
    packet_manifest_sha256,
    rollback_attestation_sha256,
    rollback_attestation_verification_sha256,
) = sys.argv[2:]
data = json.loads(path.read_text(encoding="utf-8"))
data["http3_canary"] = "PASS"
data["http3_host"] = "api.codestra.co"
data["full_fixed_target_canary"] = "PASS"
data["production_canary_mode"] = mode
data["full_canary_evidence_sha256"] = evidence_sha256
data["artifact_packet_manifest_sha256"] = packet_manifest_sha256
data["rollback_source_attestation_sha256"] = rollback_attestation_sha256
data["rollback_source_attestation_verification_sha256"] = (
    rollback_attestation_verification_sha256
)
data["full_post_activation_canary"] = (
    "PASS" if mode == "post-activation" else "NOT_APPLICABLE"
)
data["rollback_fixed_target_canary"] = (
    "PASS" if mode == "rollback" else "NOT_APPLICABLE"
)
path.write_text(
    json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

as_root install -d -m 0700 "$EVIDENCE_DIR"
final="$EVIDENCE_DIR/caddy-production-${CANARY_MODE}-canary-$stamp.json"
as_root install -m 0600 "$temporary" "$final"
rm -f -- "$temporary"
trap 'rm -rf -- "$work"' EXIT

printf '%s\n' "$http3_output"
printf 'CADDY_PRODUCTION_CANARY=PASS\nCADDY_PRODUCTION_CANARY_MODE=%s\nEVIDENCE=%s\nARTIFACT_PACKET_DIR=%s\nARTIFACT_PACKET_MANIFEST_SHA256=%s\nROLLBACK_SOURCE_ATTESTATION_SHA256=%s\nROLLBACK_SOURCE_ATTESTATION_VERIFICATION_SHA256=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nFULL_CANARY_SHA256=%s\nLISTENER_OWNERSHIP=CADDY_PROCESS_ONLY\nEFFECTIVE_LOG_REDACTION=PASS\nHTTP3=PASS\nFULL_FIXED_TARGET_CANARY=PASS\n' \
  "$CANARY_MODE" "$final" "$OUTPUT_DIR" "$packet_manifest_sha256" \
  "$rollback_attestation_sha256" "$rollback_attestation_verification_sha256" \
  "$actual_source" "$actual_image" "$actual_config" "$full_canary_sha256"
