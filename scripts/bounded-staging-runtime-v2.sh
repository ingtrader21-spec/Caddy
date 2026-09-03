#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly DOCKER=/usr/bin/docker
readonly CURL=/usr/bin/curl
readonly OPENSSL=/usr/bin/openssl
readonly AUTH_HEADER_NAME=Authorization
readonly AUTH_SCHEME=Bearer
readonly PYTHON=/usr/bin/python3
readonly SS=/usr/bin/ss
readonly IMAGE="${CADDY_STAGING_IMAGE:-}"
readonly SOURCE_SHA="${CADDY_STAGING_SOURCE_SHA:-}"
readonly CONFIG_SHA256="${CADDY_STAGING_CONFIG_SHA256:-}"
readonly ENV_FILE="${CADDY_STAGING_ENV_FILE:-}"
readonly DATA_SOURCE="${CADDY_STAGING_DATA_SOURCE:-}"
readonly MTLS_CLIENT_CERT="${CADDY_STAGING_MTLS_CLIENT_CERT:-}"
readonly MTLS_CLIENT_KEY="${CADDY_STAGING_MTLS_CLIENT_KEY:-}"
readonly MTLS_CA_CERT="${CADDY_STAGING_MTLS_CA_CERT:-}"
readonly CANDIDATE=codestra-caddy-bounded-staging
readonly NETWORK="codestra-caddy-staging-${GITHUB_RUN_ID:-manual}"

fail() {
  printf 'CADDY_BOUNDED_STAGING=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$IMAGE" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail invalid_image
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_config_sha256
for binary in "$DOCKER" "$CURL" "$OPENSSL" "$PYTHON" "$SS"; do
  [[ -x "$binary" && ! -L "$binary" ]] || fail "trusted_binary:${binary##*/}"
done
for path in "$ENV_FILE" "$MTLS_CLIENT_CERT" "$MTLS_CLIENT_KEY" "$MTLS_CA_CERT"; do
  [[ -f "$path" && ! -L "$path" ]] || fail "invalid_file:${path##*/}"
done
[[ -d "$DATA_SOURCE" && ! -L "$DATA_SOURCE" ]] || fail invalid_data_source

root_prefix=()
if "$DOCKER" info >/dev/null 2>&1; then
  :
elif command -v sudo >/dev/null 2>&1 && sudo -n "$DOCKER" info >/dev/null 2>&1; then
  root_prefix=(sudo -n)
else
  fail docker_access
fi
as_root() { "${root_prefix[@]}" "$@"; }
docker_cmd() { "${root_prefix[@]}" "$DOCKER" "$@"; }

[[ "$(stat -c %u "$ENV_FILE")" == 0 ]] || fail env_not_root_owned
case "$(stat -c %a "$ENV_FILE")" in 400|600) ;; *) fail env_mode ;; esac

required=(
  CADDY_PUBLIC_BIND CADDY_PRIVATE_METRICS_BIND CADDY_PRIVATE_INGRESS_BIND
  CADDY_KLYROW_SOURCE_CIDRS CADDY_VICIDIAL_SOURCE_CIDRS
  CADDY_STAGING_EVENT_SOURCE_CIDRS CADDY_KONG_UPSTREAM
  CADDY_REALTIME_UPSTREAM CADDY_KEYCLOAK_UPSTREAM
  CADDY_CRM_RESELLER_UPSTREAM CADDY_CRM_UPSTREAM CADDY_N8N_UPSTREAM
  CADDY_N8N_STAGING_UPSTREAM CADDY_STAGING_API_UPSTREAM
  CADDY_STAGING_PORTAL_UPSTREAM CADDY_STAGING_KEYCLOAK_UPSTREAM
  CADDY_STAGING_ODOO_UPSTREAM CADDY_MIDDLEWARE_CALLBACK_UPSTREAM
  CADDY_AGENT_GATEWAY_UPSTREAM CADDY_AGENT_UI_UPSTREAM
  CADDY_MONITORING_UPSTREAM CADDY_KLYROW_EVENTS_UPSTREAM
  CADDY_EDITOR_ADMIN_CIDRS CADDY_N8N_EDITOR_MAX_REQUEST_BODY
  CADDY_GRAFANA_UPSTREAM CADDY_SUPERSET_UPSTREAM CADDY_OPENBAO_UPSTREAM
  CADDY_OPENBAO_ALLOWED_CIDRS
)
declare -A permitted=() values=() seen=()
for name in "${required[@]}"; do permitted["$name"]=1; done
while IFS= read -r raw || [[ -n "$raw" ]]; do
  line="${raw%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" == *=* ]] || fail malformed_env
  name="${line%%=*}"
  value="${line#*=}"
  [[ -n "${permitted[$name]:-}" && -n "$value" ]] || fail "unapproved_env:${name}"
  [[ -z "${seen[$name]:-}" ]] || fail "duplicate_env:${name}"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || fail "invalid_env_value:${name}"
  values["$name"]="$value"
  seen["$name"]=1
done <"$ENV_FILE"
for name in "${required[@]}"; do [[ -n "${values[$name]:-}" ]] || fail "missing_env:${name}"; done

# Preserve actual staging upstreams. Loopback upstreams are translated to the
# Docker host gateway because the candidate has a private network namespace.
for name in "${required[@]}"; do
  [[ "$name" == *_UPSTREAM ]] || continue
  case "${values[$name]}" in
    127.0.0.1:*) values["$name"]="host.docker.internal:${values[$name]#127.0.0.1:}" ;;
    localhost:*) values["$name"]="host.docker.internal:${values[$name]#localhost:}" ;;
  esac
done

for endpoint in 127.0.0.1:18080 127.0.0.1:18443 127.0.0.1:12020 127.0.0.1:28080; do
  "$SS" -H -lntup | grep -Fq "$endpoint" && fail "bounded_listener_in_use:${endpoint}"
done
"$SS" -H -lnup | grep -Fq '127.0.0.1:18443' && fail bounded_udp_listener_in_use
if docker_cmd container inspect "$CANDIDATE" >/dev/null 2>&1; then fail preexisting_candidate; fi
if docker_cmd network inspect "$NETWORK" >/dev/null 2>&1; then fail preexisting_network; fi

subnet=''
gateway=''
candidate_ip=''
for third in $(seq 240 254); do
  attempted="172.30.${third}.0/24"
  if docker_cmd network create --driver bridge --subnet "$attempted" "$NETWORK" >/dev/null 2>&1; then
    subnet="$attempted"
    gateway="172.30.${third}.1"
    candidate_ip="172.30.${third}.2"
    break
  fi
done
[[ -n "$subnet" ]] || fail network_allocation

work="$(mktemp -d /var/tmp/codestra-caddy-staging.XXXXXX)"
cleanup() {
  docker_cmd rm -f "$CANDIDATE" >/dev/null 2>&1 || true
  docker_cmd network rm "$NETWORK" >/dev/null 2>&1 || true
  as_root rm -rf -- "$work" >/dev/null 2>&1 || true
}
trap cleanup EXIT
as_root install -d -m 0700 "$work/data" "$work/runtime-config" "$work/logs" "$work/config-copy"
as_root cp -a "$DATA_SOURCE/." "$work/data/"
as_root chown -R 65532:65532 "$work/data" "$work/runtime-config" "$work/logs"
as_root chmod 0700 "$work/data" "$work/runtime-config" "$work/logs"

values[CADDY_PUBLIC_BIND]="$candidate_ip"
values[CADDY_PRIVATE_METRICS_BIND]="$candidate_ip"
values[CADDY_PRIVATE_INGRESS_BIND]="$candidate_ip"
values[CADDY_KLYROW_SOURCE_CIDRS]="$gateway/32"
values[CADDY_VICIDIAL_SOURCE_CIDRS]="$gateway/32"
values[CADDY_STAGING_EVENT_SOURCE_CIDRS]="$gateway/32"
# Prove editor/OpenBao denial from the host gateway rather than accidentally
# granting the certification runner administrative access.
values[CADDY_EDITOR_ADMIN_CIDRS]='192.0.2.1/32'
values[CADDY_OPENBAO_ALLOWED_CIDRS]='192.0.2.1/32'

# Verify exact signed image and canonical source before deployment.
docker_cmd pull "$IMAGE" >/dev/null
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == https://github.com/appolon1908-hue/Caddy ]] || fail image_source
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$SOURCE_SHA" ]] || fail image_revision
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}')" == "$CONFIG_SHA256" ]] || fail image_config
[[ "$(docker_cmd image inspect "$IMAGE" --format '{{.Config.User}}')" == 65532:65532 ]] || fail image_user
[[ "$("$PYTHON" "$ROOT/scripts/hash_config_tree.py" "$ROOT/config")" == "$CONFIG_SHA256" ]] || fail source_config
for trust_dir in /etc/caddy/private/klyrow-events /etc/codestra/pki/middleware-private-ingress; do
  [[ -d "$trust_dir" && ! -L "$trust_dir" ]] || fail "fixed_trust_dir:${trust_dir##*/}"
done

env_args=(-e XDG_DATA_HOME=/data -e XDG_CONFIG_HOME=/config)
for name in "${required[@]}"; do env_args+=(-e "$name=${values[$name]}"); done

docker_cmd run -d --name "$CANDIDATE" --network "$NETWORK" --ip "$candidate_ip" \
  --add-host "host.docker.internal:$gateway" \
  --read-only --user 65532:65532 --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  -p 127.0.0.1:18080:80/tcp \
  -p 127.0.0.1:18443:443/tcp \
  -p 127.0.0.1:18443:443/udp \
  -p 127.0.0.1:12020:2020/tcp \
  -p 127.0.0.1:28080:18080/tcp \
  "${env_args[@]}" \
  --tmpfs /run/caddy:uid=65532,gid=65532,mode=0700 \
  --tmpfs /tmp:uid=65532,gid=65532,mode=0700 \
  --mount "type=bind,src=$work/data,dst=/data" \
  --mount "type=bind,src=$work/runtime-config,dst=/config" \
  --mount "type=bind,src=$work/logs,dst=/var/log/caddy" \
  --mount type=bind,src=/etc/caddy/private/klyrow-events,dst=/etc/caddy/private/klyrow-events,readonly \
  --mount type=bind,src=/etc/codestra/pki/middleware-private-ingress,dst=/etc/codestra/pki/middleware-private-ingress,readonly \
  "$IMAGE" >/dev/null

for attempt in $(seq 1 90); do
  state="$(docker_cmd inspect "$CANDIDATE" --format '{{.State.Status}}' 2>/dev/null || true)"
  if [[ "$state" == running ]] && "$CURL" --noproxy '*' --fail --silent --max-time 3 \
    http://127.0.0.1:12020/healthz >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 90 ]]; then
    docker_cmd logs --tail 160 "$CANDIDATE" >&2 || true
    fail startup
  fi
  sleep 1
done

docker_cmd exec "$CANDIDATE" /usr/bin/caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
inspect="$(docker_cmd inspect "$CANDIDATE")"
"$PYTHON" - "$IMAGE" "$NETWORK" "$inspect" <<'PY'
import json
import sys
expected, network = sys.argv[1:3]
item = json.loads(sys.argv[3])[0]
config, host, state = item["Config"], item["HostConfig"], item["State"]
assert config["Image"] == expected
assert config["User"] == "65532:65532"
assert host["ReadonlyRootfs"] is True
assert set(host.get("CapDrop") or []) == {"ALL"}
assert set(host.get("CapAdd") or []) == {"NET_BIND_SERVICE"}
assert "no-new-privileges:true" in set(host.get("SecurityOpt") or [])
assert host["NetworkMode"] == network
assert state["Running"] is True
for binding in host.get("PortBindings", {}).values():
    for item in binding:
        assert item.get("HostIp") == "127.0.0.1"
PY

http_status="$($CURL --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18080:127.0.0.1 http://api.codestra.co:18080/api/v1/health)"
[[ "$http_status" =~ ^30(1|7|8)$ ]] || fail "redirect:${http_status}"
api_headers="$work/api.headers"
api_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --dump-header "$api_headers" --output "$work/api.body" --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 \
  -H "${AUTH_HEADER_NAME}: ${AUTH_SCHEME} bounded-staging-invalid" \
  https://api.codestra.co:18443/api/v1/health)"
case "$api_status" in 200|204|401|403) ;; *) fail "kong_readonly:${api_status}" ;; esac
grep -Eqi '^strict-transport-security: max-age=31536000' "$api_headers" || fail hsts

version_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/version.body" --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 https://api.codestra.co:18443/version)"
[[ "$version_status" == 200 ]] || fail "realtime_version:${version_status}"
unknown_status="$($CURL --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 https://api.codestra.co:18443/not-a-contracted-route)"
[[ "$unknown_status" == 404 ]] || fail "unknown_route:${unknown_status}"

keycloak_status="$($CURL --noproxy '*' --silent --show-error --max-time 15 \
  --output "$work/keycloak.json" --write-out '%{http_code}' \
  --resolve auth.codestra.co:18443:127.0.0.1 \
  https://auth.codestra.co:18443/realms/codestra/.well-known/openid-configuration)"
[[ "$keycloak_status" == 200 ]] || fail "keycloak:${keycloak_status}"
"$PYTHON" - "$work/keycloak.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
assert value.get("issuer") == "https://auth.codestra.co/realms/codestra"
PY

"$OPENSSL" s_client -connect 127.0.0.1:18443 -servername api.codestra.co -alpn h2 </dev/null 2>/dev/null \
  | grep -q 'ALPN protocol: h2' || fail http2
"$OPENSSL" s_client -connect 127.0.0.1:18443 -servername api.codestra.co </dev/null 2>/dev/null \
  | "$OPENSSL" x509 -noout -checkend 604800 >/dev/null || fail certificate_expiry
docker_cmd exec "$CANDIDATE" /usr/bin/codestra-http3-probe api.codestra.co "$candidate_ip" /version >"$work/http3.txt"
grep -q 'CADDY_HTTP3_CANARY=PASS' "$work/http3.txt" || fail http3
"$PYTHON" "$ROOT/scripts/websocket_probe.py" api.codestra.co 127.0.0.1 /ws/agent >/dev/null || fail websocket

editor_status="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve automation.codestra.co:18443:127.0.0.1 https://automation.codestra.co:18443/)"
[[ "$editor_status" == 404 ]] || fail "editor_denial:${editor_status}"
bao_status="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve bao.codestra.media:18443:127.0.0.1 https://bao.codestra.media:18443/)"
[[ "$bao_status" == 403 ]] || fail "openbao_denial:${bao_status}"

head -c 10485761 /dev/zero >"$work/large.bin"
limit_status="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 -X POST \
  -H 'Content-Type: application/octet-stream' --data-binary "@$work/large.bin" \
  https://api.codestra.co:18443/api/v1/health)"
[[ "$limit_status" == 413 ]] || fail "request_limit:${limit_status}"

without_cert="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --resolve middleware-email-events.internal.codestra.agency:28080:127.0.0.1 \
  https://middleware-email-events.internal.codestra.agency:28080/not-contracted || true)"
[[ "$without_cert" == 000 || "$without_cert" == 400 ]] || fail "mtls_without_cert:${without_cert}"
with_cert="$($CURL --noproxy '*' -ksS --output /dev/null --write-out '%{http_code}' \
  --cert "$MTLS_CLIENT_CERT" --key "$MTLS_CLIENT_KEY" --cacert "$MTLS_CA_CERT" \
  --resolve middleware-email-events.internal.codestra.agency:28080:127.0.0.1 \
  https://middleware-email-events.internal.codestra.agency:28080/not-contracted)"
[[ "$with_cert" == 403 ]] || fail "mtls_denial:${with_cert}"

"$CURL" --noproxy '*' -ksS --resolve api.codestra.co:18443:127.0.0.1 \
  -H "${AUTH_HEADER_NAME}: ${AUTH_SCHEME} bounded-staging-auth-secret" \
  -H 'Cookie: session=bounded-staging-cookie-secret' \
  -H 'X-Api-Key: bounded-staging-api-key-secret' \
  'https://api.codestra.co:18443/api/v1/health?apikey=bounded-staging-query-secret&code=bounded-staging-code-secret&state=bounded-staging-state-secret' \
  >/dev/null

docker_cmd stop --time 15 "$CANDIDATE" >/dev/null
for secret in bounded-staging-auth-secret bounded-staging-cookie-secret bounded-staging-api-key-secret bounded-staging-query-secret bounded-staging-code-secret bounded-staging-state-secret; do
  ! grep -R -F "$secret" "$work/logs" || fail log_redaction
 done

docker_cmd cp "$CANDIDATE:/etc/caddy/." "$work/config-copy"
as_root rm -rf -- "$work/config-copy/private"
runtime_config_sha256="$($PYTHON "$ROOT/scripts/hash_config_tree.py" "$work/config-copy")"
[[ "$runtime_config_sha256" == "$CONFIG_SHA256" ]] || fail runtime_config
modules="$(docker_cmd run --rm --entrypoint /usr/bin/caddy "$IMAGE" list-modules --packages)"
module_sha256="$(printf '%s\n' "$modules" | sha256sum | awk '{print $1}')"
[[ -n "$modules" ]] || fail modules

docker_cmd rm "$CANDIDATE" >/dev/null
docker_cmd network rm "$NETWORK" >/dev/null
for endpoint in 127.0.0.1:18080 127.0.0.1:18443 127.0.0.1:12020 127.0.0.1:28080; do
  ! "$SS" -H -lntup | grep -Fq "$endpoint" || fail "listener_not_released:${endpoint}"
done

"$PYTHON" - "$SOURCE_SHA" "$IMAGE" "$CONFIG_SHA256" "$runtime_config_sha256" "$module_sha256" "$api_status" "$version_status" "$keycloak_status" <<'PY'
import json, sys
from pathlib import Path
source_sha, image, config_sha256, runtime_config_sha256, module_sha256, api_status, version_status, keycloak_status = sys.argv[1:]
evidence = {
    "schema": "codestra.caddy.bounded-staging-runtime.v2",
    "source_sha": source_sha,
    "image": image,
    "config_sha256": config_sha256,
    "runtime_config_sha256": runtime_config_sha256,
    "module_set_sha256": module_sha256,
    "isolated_network": True,
    "host_bindings_loopback_only": True,
    "nonroot_readonly_runtime": "PASS",
    "tcp_80_443_udp_443": "PASS",
    "http2_http3_websocket": "PASS",
    "certificate_expiry": "PASS",
    "redirects_hsts_limits": "PASS",
    "kong_readonly_status": int(api_status),
    "realtime_readonly_status": int(version_status),
    "keycloak_readonly_status": int(keycloak_status),
    "editor_openbao_denial": "PASS",
    "mtls_handshake_and_denial": "PASS",
    "sanitized_logs": "PASS",
    "candidate_removed": True,
    "public_traffic_changed": False,
    "dns_changed": False,
    "firewall_changed": False,
    "ssh_changed": False,
    "result": "PASS",
}
Path("bounded-staging-runtime-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf '%s\n' \
  'CADDY_BOUNDED_STAGING=PASS' \
  "SOURCE_SHA=$SOURCE_SHA" \
  "IMAGE=$IMAGE" \
  "CONFIG_SHA256=$CONFIG_SHA256" \
  'HOST_BINDINGS_LOOPBACK_ONLY=true' \
  'PUBLIC_TRAFFIC_CHANGED=false'
