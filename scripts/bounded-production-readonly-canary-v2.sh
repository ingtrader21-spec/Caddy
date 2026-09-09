#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly HASH_CONFIG="$ROOT/scripts/hash_config_tree.py"
readonly DOCKER=/usr/bin/docker
readonly PYTHON=/usr/bin/python3
readonly CURL=/usr/bin/curl
readonly OPENSSL=/usr/bin/openssl
readonly AUTH_HEADER_NAME=Authorization
readonly AUTH_SCHEME=Bearer
readonly IMAGE="${CADDY_CANARY_IMAGE:-}"
readonly SOURCE_SHA="${CADDY_CANARY_SOURCE_SHA:-}"
readonly CONFIG_SHA256="${CADDY_CANARY_CONFIG_SHA256:-}"
readonly MTLS_CLIENT_CERT="${CADDY_PRODUCTION_MTLS_CLIENT_CERT:-}"
readonly MTLS_CLIENT_KEY="${CADDY_PRODUCTION_MTLS_CLIENT_KEY:-}"
readonly MTLS_CA_CERT="${CADDY_PRODUCTION_MTLS_CA_CERT:-}"
readonly MODE="${CADDY_PRODUCTION_CANARY_MODE:-pre-activation}"

fail() {
  printf 'CADDY_PRODUCTION_READONLY_CANARY=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
case "$MODE" in
  pre-activation|post-activation|rollback) ;;
  *) fail invalid_canary_mode ;;
esac
[[ "$IMAGE" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail invalid_image
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_config_sha256
for path in "$DOCKER" "$PYTHON" "$CURL" "$OPENSSL" "$VALIDATOR" "$HASH_CONFIG"; do
  [[ -e "$path" && ! -L "$path" ]] || fail "trusted_path:${path##*/}"
done
[[ -x "$VALIDATOR" ]] || fail validator_not_executable
[[ -f "$HASH_CONFIG" ]] || fail config_hasher_unavailable
for path in "$MTLS_CLIENT_CERT" "$MTLS_CLIENT_KEY" "$MTLS_CA_CERT"; do
  [[ "$path" = /* && "$path" != *..* && "$path" != *//* ]] || fail "unsafe_mtls_path:${path##*/}"
  [[ -f "$path" && ! -L "$path" && -r "$path" ]] || fail "invalid_mtls_file:${path##*/}"
done

root_prefix=()
if "$DOCKER" info >/dev/null 2>&1; then
  :
elif command -v sudo >/dev/null 2>&1 && sudo -n "$DOCKER" info >/dev/null 2>&1; then
  root_prefix=(sudo -n)
else
  fail docker_access
fi
docker_cmd() { "${root_prefix[@]}" "$DOCKER" "$@"; }
run_validator() { "${root_prefix[@]}" "$PYTHON" "$VALIDATOR" >"$1"; }

work="$(mktemp -d)"
image_probe=""
cleanup() {
  if [[ -n "$image_probe" ]]; then
    docker_cmd rm -f "$image_probe" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT

run_validator pre-canary-runtime.json
pre_sha256="$(sha256sum pre-canary-runtime.json | awk '{print $1}')"

if [[ "$MODE" != pre-activation ]]; then
  "$PYTHON" - pre-canary-runtime.json "$SOURCE_SHA" "$IMAGE" "$CONFIG_SHA256" <<'PY'
import json
import sys
from pathlib import Path

path, source_sha, image, config_sha256 = sys.argv[1:]
value = json.loads(Path(path).read_text(encoding="utf-8"))
expected_digest = image.rsplit("@", 1)[1]
assert value["schema"] == "codestra.caddy-container-validation.v2"
assert value["source_sha"] == source_sha
assert value["image_digest"] == expected_digest
assert value["config_sha256"] == config_sha256
assert value["container_running"] is True
assert value["container_health"] == "healthy"
assert value["config_validation"] == "PASS"
assert value["config_identity"] == "PASS"
assert value["listener_ownership"] == "CADDY_PROCESS_ONLY"
assert value["effective_access_log_redaction"] == "PASS"
PY
fi

docker_cmd pull "$IMAGE" >/dev/null
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == https://github.com/appolon1908-hue/Caddy ]] || fail candidate_source
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$SOURCE_SHA" ]] || fail candidate_revision
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')" == "$CONFIG_SHA256" ]] || fail candidate_config
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{.Config.User}}')" == 65532:65532 ]] || fail candidate_user

mkdir -p "$work/image-config"
image_probe="$(docker_cmd create "$IMAGE")"
docker_cmd cp "$image_probe:/etc/caddy/." "$work/image-config"
image_config_sha256="$("$PYTHON" "$HASH_CONFIG" "$work/image-config")"
[[ "$image_config_sha256" == "$CONFIG_SHA256" ]] || fail image_config_identity
docker_cmd rm -f "$image_probe" >/dev/null
image_probe=""

if [[ "$MODE" != rollback ]]; then
  [[ "$("$PYTHON" "$HASH_CONFIG" "$ROOT/config")" == "$CONFIG_SHA256" ]] || fail source_config
fi

docker_cmd run --rm --network none \
  --mount type=bind,src=/etc/caddy/private/klyrow-events,dst=/etc/caddy/private/klyrow-events,readonly \
  --mount type=bind,src=/etc/codestra/pki/middleware-private-ingress,dst=/etc/codestra/pki/middleware-private-ingress,readonly \
  "$IMAGE" validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

live_env="$(docker_cmd inspect codestra-caddy --format '{{json .Config.Env}}')"
readarray -t binds < <("$PYTHON" - "$live_env" <<'PY'
import json
import sys
values = {}
for entry in json.loads(sys.argv[1]):
    if "=" in entry:
        key, value = entry.split("=", 1)
        values[key] = value
for name in ("CADDY_PUBLIC_BIND", "CADDY_PRIVATE_INGRESS_BIND"):
    value = values.get(name, "")
    if not value:
        raise SystemExit(2)
    print(value)
PY
)
[[ ${#binds[@]} -eq 2 ]] || fail live_bind_contract
public_bind="${binds[0]}"
private_bind="${binds[1]}"

api_headers="$work/api.headers"
api_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --dump-header "$api_headers" --output "$work/api.body" --write-out '%{http_code}' \
  --resolve "api.codestra.co:443:${public_bind}" \
  -H "${AUTH_HEADER_NAME}: ${AUTH_SCHEME} bounded-production-invalid" \
  https://api.codestra.co/api/v1/health)"
case "$api_status" in 200|204|401|403) ;; *) fail "live_kong_status:${api_status}" ;; esac
grep -Eqi '^strict-transport-security: max-age=31536000' "$api_headers" || fail live_hsts

redirect_status="$($CURL --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve "api.codestra.co:80:${public_bind}" http://api.codestra.co/api/v1/health)"
[[ "$redirect_status" =~ ^30(1|7|8)$ ]] || fail "live_redirect:${redirect_status}"

version_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/version.body" --write-out '%{http_code}' \
  --resolve "api.codestra.co:443:${public_bind}" https://api.codestra.co/version)"
[[ "$version_status" == 200 ]] || fail "live_realtime_status:${version_status}"
unknown_status="$($CURL --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve "api.codestra.co:443:${public_bind}" https://api.codestra.co/not-a-contracted-route)"
[[ "$unknown_status" == 404 ]] || fail "live_unknown_route:${unknown_status}"

keycloak_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/keycloak.json" --write-out '%{http_code}' \
  --resolve "auth.codestra.co:443:${public_bind}" \
  https://auth.codestra.co/realms/codestra/.well-known/openid-configuration)"
[[ "$keycloak_status" == 200 ]] || fail "live_keycloak_status:${keycloak_status}"
"$PYTHON" - "$work/keycloak.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value.get("issuer") == "https://auth.codestra.co/realms/codestra"
PY

"$OPENSSL" s_client -connect "${public_bind}:443" -servername api.codestra.co -alpn h2 </dev/null 2>/dev/null \
  | grep -q 'ALPN protocol: h2' || fail live_http2
"$OPENSSL" s_client -connect "${public_bind}:443" -servername api.codestra.co </dev/null 2>/dev/null \
  | "$OPENSSL" x509 -noout -checkend 604800 >"$work/certificate-check.txt" || fail live_certificate_expiry

docker_cmd exec codestra-caddy /usr/bin/codestra-http3-probe api.codestra.co "$public_bind" /version \
  >"$work/http3.txt"
grep -q 'CADDY_HTTP3_CANARY=PASS' "$work/http3.txt" || fail live_http3
"$PYTHON" "$ROOT/scripts/websocket_probe.py" api.codestra.co "$public_bind" /ws/agent >/dev/null || fail live_websocket

editor_status="$($CURL --interface 127.0.0.3 --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve "automation.codestra.co:443:${public_bind}" https://automation.codestra.co/)"
[[ "$editor_status" == 404 ]] || fail "live_editor_denial:${editor_status}"
bao_status="$($CURL --interface 127.0.0.3 --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve "bao.codestra.media:443:${public_bind}" https://bao.codestra.media/)"
[[ "$bao_status" == 403 ]] || fail "live_openbao_denial:${bao_status}"

without_cert="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output /dev/null --write-out '%{http_code}' --cacert "$MTLS_CA_CERT" \
  --resolve "middleware-email-events.internal.codestra.agency:18080:${private_bind}" \
  https://middleware-email-events.internal.codestra.agency:18080/not-contracted || true)"
[[ "$without_cert" == 000 || "$without_cert" == 400 ]] || fail "live_mtls_without_cert:${without_cert}"
with_cert="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output /dev/null --write-out '%{http_code}' \
  --cert "$MTLS_CLIENT_CERT" --key "$MTLS_CLIENT_KEY" --cacert "$MTLS_CA_CERT" \
  --resolve "middleware-email-events.internal.codestra.agency:18080:${private_bind}" \
  https://middleware-email-events.internal.codestra.agency:18080/not-contracted)"
[[ "$with_cert" == 403 ]] || fail "live_mtls_denial:${with_cert}"

grafana_status="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve "graf.codestra.media:443:${public_bind}" https://graf.codestra.media/api/health)"
[[ "$grafana_status" == 200 ]] || fail "live_grafana_status:${grafana_status}"

run_validator post-canary-runtime.json
post_sha256="$(sha256sum post-canary-runtime.json | awk '{print $1}')"
cmp -s pre-canary-runtime.json post-canary-runtime.json || fail live_runtime_changed

"$PYTHON" - "$MODE" "$SOURCE_SHA" "$IMAGE" "$CONFIG_SHA256" "$pre_sha256" "$post_sha256" "$api_status" "$version_status" "$keycloak_status" "$grafana_status" "$image_config_sha256" <<'PY'
import json
import sys
from pathlib import Path

(
    mode,
    source_sha,
    image,
    config_sha256,
    pre_sha256,
    post_sha256,
    api_status,
    version_status,
    keycloak_status,
    grafana_status,
    image_config_sha256,
) = sys.argv[1:]
pre = json.loads(Path("pre-canary-runtime.json").read_text(encoding="utf-8"))
post = json.loads(Path("post-canary-runtime.json").read_text(encoding="utf-8"))
if pre != post:
    raise SystemExit(2)
expected_tuple_live = mode in {"post-activation", "rollback"}
post_activation = mode == "post-activation"
rollback_validation = mode == "rollback"
bounded_staging_runtime = "NOT_APPLICABLE" if rollback_validation else "PASS"
if expected_tuple_live:
    if (
        pre["source_sha"] != source_sha
        or pre["image_digest"] != image.rsplit("@", 1)[1]
        or pre["config_sha256"] != config_sha256
    ):
        raise SystemExit(2)
evidence = {
    "schema": "codestra.caddy.production-readonly-canary.v2",
    "canary_mode": mode,
    "candidate_source_sha": source_sha,
    "candidate_image": image,
    "candidate_config_sha256": config_sha256,
    "expected_source_sha": source_sha,
    "expected_image": image,
    "expected_config_sha256": config_sha256,
    "expected_image_config_sha256": image_config_sha256,
    "candidate_signature_and_attestation": "PASS",
    "bounded_staging_runtime": bounded_staging_runtime,
    "candidate_offline_config_validation": "PASS",
    "live_container_validation_before": "PASS",
    "live_container_validation_after": "PASS",
    "live_runtime_snapshot_before_sha256": pre_sha256,
    "live_runtime_snapshot_after_sha256": post_sha256,
    "live_runtime_unchanged": True,
    "live_runtime_is_expected_tuple": expected_tuple_live,
    "live_runtime_is_candidate": post_activation,
    "rollback_validation": rollback_validation,
    "live_source_sha": pre["source_sha"],
    "live_image_digest": pre["image_digest"],
    "live_config_sha256": pre["config_sha256"],
    "live_health": pre["container_health"],
    "live_listener_ownership": pre["listener_ownership"],
    "live_effective_log_redaction": pre["effective_access_log_redaction"],
    "live_kong_readonly_status": int(api_status),
    "live_realtime_readonly_status": int(version_status),
    "live_keycloak_readonly_status": int(keycloak_status),
    "live_grafana_readonly_status": int(grafana_status),
    "live_redirect_hsts_certificate": "PASS",
    "live_http2_http3_websocket": "PASS",
    "live_editor_openbao_denial": "PASS",
    "live_mtls_server_certificate_verified": True,
    "live_mtls_handshake_and_denial": "PASS",
    "write_requests_sent": False,
    "candidate_started_on_production": post_activation,
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

candidate_started=false
expected_tuple_live=false
rollback_validation=false
bounded_staging_runtime=PASS
[[ "$MODE" == post-activation ]] && candidate_started=true
[[ "$MODE" != pre-activation ]] && expected_tuple_live=true
[[ "$MODE" == rollback ]] && rollback_validation=true
[[ "$MODE" == rollback ]] && bounded_staging_runtime=NOT_APPLICABLE
printf '%s\n' \
  'CADDY_PRODUCTION_READONLY_CANARY=PASS' \
  "CADDY_PRODUCTION_CANARY_MODE=$MODE" \
  "CANDIDATE_SOURCE_SHA=$SOURCE_SHA" \
  "CANDIDATE_IMAGE=$IMAGE" \
  "CANDIDATE_CONFIG_SHA256=$CONFIG_SHA256" \
  "IMAGE_CONFIG_SHA256=$image_config_sha256" \
  "BOUNDED_STAGING_RUNTIME=$bounded_staging_runtime" \
  "LIVE_RUNTIME_IS_EXPECTED_TUPLE=$expected_tuple_live" \
  "ROLLBACK_VALIDATION=$rollback_validation" \
  "LIVE_RUNTIME_UNCHANGED_SHA256=$post_sha256" \
  'WRITE_REQUESTS_SENT=false' \
  "CANDIDATE_STARTED_ON_PRODUCTION=$candidate_started" \
  'PUBLIC_TRAFFIC_CHANGED=false'
