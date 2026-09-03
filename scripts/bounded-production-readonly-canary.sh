#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly CANDIDATE_TEST="$ROOT/tests/runtime-canary-test.sh"
readonly DOCKER=/usr/bin/docker
readonly PYTHON=/usr/bin/python3
readonly CURL=/usr/bin/curl
readonly OPENSSL=/usr/bin/openssl
readonly IMAGE="${CADDY_CANARY_IMAGE:-}"
readonly SOURCE_SHA="${CADDY_CANARY_SOURCE_SHA:-}"
readonly CONFIG_SHA256="${CADDY_CANARY_CONFIG_SHA256:-}"

fail() {
  printf 'CADDY_PRODUCTION_READONLY_CANARY=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$IMAGE" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail invalid_image
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_config_sha256
for path in "$DOCKER" "$PYTHON" "$CURL" "$OPENSSL" "$VALIDATOR" "$CANDIDATE_TEST"; do
  [[ -e "$path" && ! -L "$path" ]] || fail "trusted_path:${path##*/}"
done
[[ -x "$VALIDATOR" && -x "$CANDIDATE_TEST" ]] || fail executable_contract

root_prefix=()
if "$DOCKER" info >/dev/null 2>&1; then
  :
elif command -v sudo >/dev/null 2>&1 && sudo -n "$DOCKER" info >/dev/null 2>&1; then
  root_prefix=(sudo -n)
else
  fail docker_access
fi

docker_cmd() {
  "${root_prefix[@]}" "$DOCKER" "$@"
}

run_validator() {
  local output="$1"
  "${root_prefix[@]}" "$PYTHON" "$VALIDATOR" >"$output"
}

work="$(mktemp -d)"
cleanup() {
  rm -rf -- "$work"
}
trap cleanup EXIT

# This is a read-only snapshot of the fixed live container. It fails closed if
# the live runtime is not the canonical immutable container authority.
run_validator pre-canary-runtime.json
pre_sha256="$(sha256sum pre-canary-runtime.json | awk '{print $1}')"

# Prove the candidate tuple before any isolated container is started.
docker_cmd pull "$IMAGE" >/dev/null
image_source="$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')"
image_revision="$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
image_config="$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')"
image_user="$(docker_cmd image inspect "$IMAGE" --format '{{.Config.User}}')"
[[ "$image_source" == https://github.com/appolon1908-hue/Caddy ]] || fail candidate_source
[[ "$image_revision" == "$SOURCE_SHA" ]] || fail candidate_revision
[[ "$image_config" == "$CONFIG_SHA256" ]] || fail candidate_config
[[ "$image_user" == 65532:65532 ]] || fail candidate_user
[[ "$("$PYTHON" "$ROOT/scripts/hash_config_tree.py" "$ROOT/config")" == "$CONFIG_SHA256" ]] || fail source_config

# Run the signed candidate only on the isolated loopback addresses and mock
# upstreams defined by the repository's exact-head canary. It never replaces,
# reloads, stops, or joins the live Caddy container.
if [[ ${#root_prefix[@]} -eq 0 ]]; then
  "$CANDIDATE_TEST" "$IMAGE" | tee production-readonly-candidate.txt
else
  sudo -n env \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    GITHUB_RUN_ID="${GITHUB_RUN_ID:-manual}" \
    bash "$CANDIDATE_TEST" "$IMAGE" | tee production-readonly-candidate.txt
fi

grep -qx 'CANARY_CERTIFICATION=PASS' production-readonly-candidate.txt || fail candidate_certification

# Probe only read-only endpoints through the existing live edge. No public DNS,
# firewall, listener, process, configuration, or traffic allocation is changed.
live_env="$(docker_cmd inspect codestra-caddy --format '{{json .Config.Env}}')"
public_bind="$("$PYTHON" - "$live_env" <<'PY'
import json
import sys

values = {}
for entry in json.loads(sys.argv[1]):
    if "=" in entry:
        key, value = entry.split("=", 1)
        values[key] = value
value = values.get("CADDY_PUBLIC_BIND", "")
if not value:
    raise SystemExit(2)
print(value)
PY
)"

api_headers="$work/api.headers"
api_body="$work/api.body"
api_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --dump-header "$api_headers" --output "$api_body" --write-out '%{http_code}' \
  --resolve "api.codestra.co:443:${public_bind}" \
  https://api.codestra.co/api/v1/health)"
case "$api_status" in
  200|204|301|302|307|308|401|403) ;;
  *) fail "live_kong_status:${api_status}" ;;
esac
grep -Eqi '^strict-transport-security: max-age=31536000' "$api_headers" || fail live_hsts

version_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/version.body" --write-out '%{http_code}' \
  --resolve "api.codestra.co:443:${public_bind}" \
  https://api.codestra.co/version)"
[[ "$version_status" == 200 ]] || fail "live_realtime_status:${version_status}"

auth_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/keycloak.json" --write-out '%{http_code}' \
  --resolve "auth.codestra.co:443:${public_bind}" \
  https://auth.codestra.co/realms/codestra/.well-known/openid-configuration)"
[[ "$auth_status" == 200 ]] || fail "live_keycloak_status:${auth_status}"
"$PYTHON" - "$work/keycloak.json" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("issuer") != "https://auth.codestra.co/realms/codestra":
    raise SystemExit(2)
PY

"$OPENSSL" s_client -connect "${public_bind}:443" -servername api.codestra.co -alpn h2 </dev/null 2>/dev/null \
  | grep -q 'ALPN protocol: h2' || fail live_http2

# The live immutable tuple and effective configuration must be byte-identical
# after the isolated candidate and read-only probes.
run_validator post-canary-runtime.json
post_sha256="$(sha256sum post-canary-runtime.json | awk '{print $1}')"
cmp -s pre-canary-runtime.json post-canary-runtime.json || fail live_runtime_changed

"$PYTHON" - \
  "$SOURCE_SHA" "$IMAGE" "$CONFIG_SHA256" \
  "$pre_sha256" "$post_sha256" \
  "$api_status" "$version_status" "$auth_status" <<'PY'
import json
import sys
from pathlib import Path

(
    source_sha,
    image,
    config_sha256,
    pre_sha256,
    post_sha256,
    api_status,
    version_status,
    auth_status,
) = sys.argv[1:]
pre = json.loads(Path("pre-canary-runtime.json").read_text(encoding="utf-8"))
post = json.loads(Path("post-canary-runtime.json").read_text(encoding="utf-8"))
if pre != post:
    raise SystemExit(2)
evidence = {
    "schema": "codestra.caddy.production-readonly-canary.v1",
    "candidate_source_sha": source_sha,
    "candidate_image": image,
    "candidate_config_sha256": config_sha256,
    "candidate_signature": "PASS",
    "candidate_attestation": "PASS",
    "candidate_isolated_certification": "PASS",
    "live_container_validation_before": "PASS",
    "live_container_validation_after": "PASS",
    "live_runtime_snapshot_before_sha256": pre_sha256,
    "live_runtime_snapshot_after_sha256": post_sha256,
    "live_runtime_unchanged": True,
    "live_source_sha": pre["source_sha"],
    "live_image_digest": pre["image_digest"],
    "live_config_sha256": pre["config_sha256"],
    "live_health": pre["container_health"],
    "live_listener_ownership": pre["listener_ownership"],
    "live_kong_readonly_status": int(api_status),
    "live_realtime_readonly_status": int(version_status),
    "live_keycloak_readonly_status": int(auth_status),
    "live_http2": "PASS",
    "public_traffic_changed": False,
    "dns_changed": False,
    "firewall_changed": False,
    "ssh_changed": False,
    "result": "PASS",
}
Path("production-canary-evidence.json").write_text(
    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

printf '%s\n' \
  'CADDY_PRODUCTION_READONLY_CANARY=PASS' \
  "CANDIDATE_SOURCE_SHA=$SOURCE_SHA" \
  "CANDIDATE_IMAGE=$IMAGE" \
  "CANDIDATE_CONFIG_SHA256=$CONFIG_SHA256" \
  "LIVE_RUNTIME_UNCHANGED_SHA256=$post_sha256" \
  'PUBLIC_TRAFFIC_CHANGED=false'
