#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

fail() {
  printf 'CADDY_PRODUCTION_CANARY=FAIL reason=%s\n' "$1" >&2
  exit 1
}

required=(
  CADDY_CANARY_IMAGE
  CADDY_CANARY_SOURCE_SHA
  CADDY_CANARY_CONFIG_SHA256
  CADDY_CANARY_ENV_FILE
  CADDY_CANARY_DATA_SOURCE
  CADDY_CANARY_MTLS_CLIENT_CERT
  CADDY_CANARY_MTLS_CLIENT_KEY
  CADDY_CANARY_MTLS_CA_CERT
)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || fail "missing_${name}"
done
[[ "$CADDY_CANARY_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail invalid_source_sha
[[ "$CADDY_CANARY_CONFIG_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail invalid_config_sha256
[[ "$CADDY_CANARY_IMAGE" =~ ^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$ ]] || fail invalid_image_identity

for command in awk base64 cp curl date docker grep jq openssl python3 sha256sum ss stat; do
  command -v "$command" >/dev/null 2>&1 || fail "missing_command_${command}"
done

root_prefix=()
if [[ "$(id -u)" -eq 0 ]]; then
  :
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  root_prefix=(sudo -n)
else
  fail passwordless_sudo_required
fi
as_root() { "${root_prefix[@]}" "$@"; }

docker_prefix=()
if docker info >/dev/null 2>&1; then
  :
elif "${root_prefix[@]}" docker info >/dev/null 2>&1; then
  docker_prefix=("${root_prefix[@]}")
else
  fail docker_access_unavailable
fi
docker_cmd() { "${docker_prefix[@]}" docker "$@"; }

[[ -f "$CADDY_CANARY_ENV_FILE" && ! -L "$CADDY_CANARY_ENV_FILE" ]] || fail invalid_canary_env_file
[[ "$(stat -c %u "$CADDY_CANARY_ENV_FILE")" = 0 ]] || fail canary_env_not_root_owned
permissions="$(stat -c %a "$CADDY_CANARY_ENV_FILE")"
[[ "$permissions" = 600 || "$permissions" = 400 ]] || fail canary_env_permissions
[[ -d "$CADDY_CANARY_DATA_SOURCE" && ! -L "$CADDY_CANARY_DATA_SOURCE" ]] || fail invalid_canary_data_source
for path in "$CADDY_CANARY_MTLS_CLIENT_CERT" "$CADDY_CANARY_MTLS_CLIENT_KEY" "$CADDY_CANARY_MTLS_CA_CERT"; do
  [[ -f "$path" && ! -L "$path" ]] || fail invalid_mtls_probe_file
done
for path in \
  /etc/caddy/private/klyrow-events \
  /etc/codestra/pki/middleware-private-ingress; do
  [[ -d "$path" && ! -L "$path" ]] || fail missing_fixed_pki_mount
 done

allowed=(
  CADDY_ACME_EMAIL CADDY_BIND_ADDRESSES CADDY_HTTP_PORT CADDY_HTTPS_PORT
  CADDY_METRICS_PORT CADDY_KONG_UPSTREAM CADDY_REALTIME_UPSTREAM
  CADDY_KEYCLOAK_UPSTREAM CADDY_BREERO_KONG_UPSTREAM
  CADDY_EDITOR_ADMIN_CIDRS CADDY_GRAFANA_UPSTREAM CADDY_SUPERSET_UPSTREAM
  CADDY_OPENBAO_HOST CADDY_OPENBAO_UPSTREAM CADDY_OPENBAO_ALLOWED_CIDRS
)
declare -A permitted=() values=()
for name in "${allowed[@]}"; do permitted["$name"]=1; done
while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  line="${raw_line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  name="${line%%=*}"
  value="${line#*=}"
  [[ "$line" == *"="* && -n "${permitted[$name]:-}" && -n "$value" ]] || fail invalid_canary_env_entry
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || fail invalid_canary_env_value
  values["$name"]="$value"
done <"$CADDY_CANARY_ENV_FILE"
for name in "${allowed[@]}"; do [[ -n "${values[$name]:-}" ]] || fail "missing_canary_${name}"; done
[[ "${values[CADDY_BIND_ADDRESSES]}" = 127.0.0.1 ]] || fail canary_bind_not_loopback
[[ "${values[CADDY_HTTP_PORT]}" = 18080 ]] || fail canary_http_port_mismatch
[[ "${values[CADDY_HTTPS_PORT]}" = 18443 ]] || fail canary_https_port_mismatch
[[ "${values[CADDY_METRICS_PORT]}" = 2021 ]] || fail canary_metrics_port_mismatch

candidate="codestra-caddy-production-canary"
if docker_cmd container inspect "$candidate" >/dev/null 2>&1; then
  fail preexisting_canary_container
fi
live_id="$(docker_cmd ps -q --filter 'name=^/codestra-caddy-edge$')"
[[ -n "$live_id" ]] || fail live_caddy_container_missing

work_root="$(mktemp -d /var/tmp/codestra-caddy-canary.XXXXXX)"
cleanup() {
  docker_cmd rm -f "$candidate" >/dev/null 2>&1 || true
  as_root rm -rf -- "$work_root"
}
trap cleanup EXIT
as_root install -d -m 0700 "$work_root/data" "$work_root/logs" "$work_root/config-copy"
as_root cp -a "$CADDY_CANARY_DATA_SOURCE/." "$work_root/data/"
as_root chown -R 65532:65532 "$work_root/data" "$work_root/logs"
as_root chmod 0700 "$work_root/data" "$work_root/logs"

# The live fixed-target validator must pass before and after the isolated canary.
as_root python3 scripts/caddy_container_readonly_validator.py > pre-canary-runtime.json

# Verify the candidate before it is allowed to start.
docker_cmd pull "$CADDY_CANARY_IMAGE" >/dev/null
candidate_revision="$(docker_cmd image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
candidate_config="$(docker_cmd image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "co.codestra.caddy.config-sha256"}}')"
candidate_source="$(docker_cmd image inspect "$CADDY_CANARY_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')"
candidate_user="$(docker_cmd image inspect "$CADDY_CANARY_IMAGE" --format '{{.Config.User}}')"
[[ "$candidate_revision" = "$CADDY_CANARY_SOURCE_SHA" ]] || fail candidate_revision_mismatch
[[ "$candidate_config" = "$CADDY_CANARY_CONFIG_SHA256" ]] || fail candidate_config_label_mismatch
[[ "$candidate_source" = https://github.com/appolon1908-hue/Caddy ]] || fail candidate_source_label_mismatch
[[ "$candidate_user" = 65532:65532 ]] || fail candidate_runtime_user_mismatch

env_args=(-e XDG_DATA_HOME=/data -e XDG_CONFIG_HOME=/config)
for name in "${allowed[@]}"; do env_args+=(-e "$name=${values[$name]}"); done

docker_cmd run -d --name "$candidate" --network host --read-only \
  --user 65532:65532 --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  "${env_args[@]}" \
  --tmpfs /run/caddy:uid=65532,gid=65532,mode=0700 \
  --tmpfs /config:uid=65532,gid=65532,mode=0700 \
  -v "$work_root/data:/data" \
  -v "$work_root/logs:/var/log/caddy" \
  -v /etc/caddy/private/klyrow-events:/etc/caddy/private/klyrow-events:ro \
  -v /etc/codestra/pki/middleware-private-ingress:/etc/codestra/pki/middleware-private-ingress:ro \
  "$CADDY_CANARY_IMAGE" >/dev/null

for attempt in $(seq 1 90); do
  state="$(docker_cmd inspect --format '{{.State.Status}}' "$candidate" 2>/dev/null || true)"
  if [[ "$state" = running ]] && curl --noproxy '*' --fail --silent --show-error --max-time 3 \
    http://127.0.0.1:2021/healthz >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 90 ]]; then
    docker_cmd logs --tail 200 "$candidate" >&2 || true
    fail canary_startup_failed
  fi
  sleep 1
done

docker_cmd exec "$candidate" /usr/bin/caddy validate \
  --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

# Verify exact embedded configuration while excluding fixed runtime PKI mounts.
docker_cmd cp "$candidate:/etc/caddy/." "$work_root/config-copy"
as_root rm -rf "$work_root/config-copy/private"
runtime_config_sha256="$(python3 - "$work_root/config-copy" <<'PY'
import hashlib, pathlib, sys
root=pathlib.Path(sys.argv[1]); digest=hashlib.sha256()
files=sorted(path for path in root.rglob('*') if path.is_file())
if not files: raise SystemExit(1)
for path in files:
    relative=path.relative_to(root).as_posix().encode(); payload=path.read_bytes()
    digest.update(len(relative).to_bytes(8,'big')); digest.update(relative)
    digest.update(len(payload).to_bytes(8,'big')); digest.update(payload)
print(digest.hexdigest())
PY
)"
[[ "$runtime_config_sha256" = "$CADDY_CANARY_CONFIG_SHA256" ]] || fail runtime_config_checksum_mismatch

inspect_json="$(docker_cmd inspect "$candidate")"
python3 - "$CADDY_CANARY_IMAGE" "$inspect_json" <<'PY'
import json, sys
expected=sys.argv[1]; item=json.loads(sys.argv[2])[0]
config=item['Config']; host=item['HostConfig']; state=item['State']
assert config['Image'] == expected
assert config['User'] == '65532:65532'
assert host['ReadonlyRootfs'] is True
assert set(host.get('CapDrop') or []) == {'ALL'}
assert set(host.get('CapAdd') or []) == {'NET_BIND_SERVICE'}
assert 'no-new-privileges:true' in set(host.get('SecurityOpt') or [])
assert host['NetworkMode'] == 'host'
assert state['Running'] is True
PY

modules="$(docker_cmd exec "$candidate" /usr/bin/caddy list-modules --packages)"
module_count="$(grep -c . <<<"$modules")"
module_sha256="$(printf '%s\n' "$modules" | sha256sum | awk '{print $1}')"
[[ "$module_count" -gt 0 ]] || fail empty_module_manifest

ss -H -lnt | grep -Eq '127\.0\.0\.1:18080([[:space:]]|$)' || fail missing_tcp_18080
ss -H -lnt | grep -Eq '127\.0\.0\.1:18443([[:space:]]|$)' || fail missing_tcp_18443
ss -H -lnu | grep -Eq '127\.0\.0\.1:18443([[:space:]]|$)' || fail missing_udp_18443
ss -H -lnt | grep -Eq '127\.0\.0\.1:2021([[:space:]]|$)' || fail missing_tcp_2021

http_status="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18080:127.0.0.1 http://api.codestra.co:18080/v1/admin/system/health)"
[[ "$http_status" = 308 ]] || fail http_redirect_failed

headers="$work_root/api.headers"
kong_status="$(curl --noproxy '*' --silent --show-error --http2 \
  --dump-header "$headers" --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 \
  -H 'Authorization: Bearer invalid-canary-token' \
  https://api.codestra.co:18443/v1/admin/system/health)"
[[ "$kong_status" = 401 || "$kong_status" = 403 ]] || fail invalid_identity_not_rejected
grep -Eqi '^x-codestra-upstream-class: kong' "$headers" || fail kong_route_header_missing
grep -Eqi '^strict-transport-security: max-age=31536000; includeSubDomains' "$headers" || fail hsts_missing
curl --noproxy '*' --fail --silent --show-error --http2 \
  --resolve auth.codestra.co:18443:127.0.0.1 \
  https://auth.codestra.co:18443/realms/codestra/.well-known/openid-configuration \
  > "$work_root/keycloak.json"
python3 - "$work_root/keycloak.json" <<'PY'
import json, sys
value=json.load(open(sys.argv[1],encoding='utf-8'))
assert value.get('issuer') == 'https://auth.codestra.co/realms/codestra'
PY

(cd tests/http3-probe && go mod tidy && go run . api.codestra.co 18443 /v1/admin/system/health "$kong_status") \
  > "$work_root/http3.txt"

unknown_status="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 https://api.codestra.co:18443/not-a-real-codestra-route)"
[[ "$unknown_status" = 404 ]] || fail unknown_path_not_denied

large_status="$(head -c 11000000 /dev/zero | curl --noproxy '*' --silent --output /dev/null \
  --write-out '%{http_code}' --resolve api.codestra.co:18443:127.0.0.1 \
  -X POST -H 'Content-Type: application/octet-stream' --data-binary @- \
  https://api.codestra.co:18443/v1/admin/system/health)"
[[ "$large_status" = 413 ]] || fail request_limit_not_enforced

fallback_headers="$work_root/fallback.headers"
fallback_status="$(curl --noproxy '*' --silent --show-error --dump-header "$fallback_headers" \
  --output /dev/null --write-out '%{http_code}' \
  --resolve api.codestra.co:18443:127.0.0.1 https://api.codestra.co:18443/version)"
[[ "$fallback_status" = 200 ]] || fail read_only_fallback_unhealthy
grep -Eqi '^x-codestra-upstream-class: realtime-legacy-v1' "$fallback_headers" || fail fallback_class_header_missing

superset_headers="$work_root/superset.headers"
superset_status="$(curl --noproxy '*' --silent --show-error --dump-header "$superset_headers" \
  --output /dev/null --write-out '%{http_code}' \
  --resolve supe.codestra.media:18443:127.0.0.1 \
  https://supe.codestra.media:18443/login/keycloak)"
[[ "$superset_status" = 302 || "$superset_status" = 303 ]] || fail superset_oidc_redirect_status
grep -Eqi '^location: https://auth\.codestra\.co/' "$superset_headers" || fail keycloak_redirect_missing

grafana_status="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve grafana.codestra.media:18443:127.0.0.1 \
  https://grafana.codestra.media:18443/api/health)"
[[ "$grafana_status" = 200 ]] || fail grafana_upstream_unhealthy
superset_health="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve supe.codestra.media:18443:127.0.0.1 \
  https://supe.codestra.media:18443/health)"
[[ "$superset_health" = 200 ]] || fail superset_upstream_unhealthy

editor_status="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --resolve automation.codestra.co:18443:127.0.0.1 \
  https://automation.codestra.co:18443/)"
[[ "$editor_status" = 404 ]] || fail editor_offnet_denial_failed

mtls_url=https://middleware.internal.codestra.agency:18443/api/v1/events/vicidial
if curl --noproxy '*' --silent --show-error --cacert "$CADDY_CANARY_MTLS_CA_CERT" \
  --resolve middleware.internal.codestra.agency:18443:127.0.0.1 "$mtls_url" >/dev/null 2>&1; then
  fail mtls_missing_client_certificate_accepted
fi
mtls_status="$(curl --noproxy '*' --silent --show-error --cacert "$CADDY_CANARY_MTLS_CA_CERT" \
  --cert "$CADDY_CANARY_MTLS_CLIENT_CERT" --key "$CADDY_CANARY_MTLS_CLIENT_KEY" \
  --resolve middleware.internal.codestra.agency:18443:127.0.0.1 \
  --output /dev/null --write-out '%{http_code}' "$mtls_url")"
[[ "$mtls_status" = 403 ]] || fail mtls_authenticated_source_denial_failed

curl --noproxy '*' --silent --show-error --output /dev/null \
  --resolve api.codestra.co:18443:127.0.0.1 \
  -H 'Authorization: Bearer CANARY_REQUEST_TOKEN_SECRET' \
  -H 'Cookie: session=CANARY_REQUEST_COOKIE_SECRET' \
  -H 'X-Api-Key: CANARY_REQUEST_API_KEY_SECRET' \
  'https://api.codestra.co:18443/v1/admin/system/health?code=CANARY_OIDC_CODE_SECRET&state=CANARY_OIDC_STATE_SECRET&apikey=CANARY_QUERY_API_KEY_SECRET'
sleep 2
for secret in \
  CANARY_REQUEST_TOKEN_SECRET CANARY_REQUEST_COOKIE_SECRET \
  CANARY_REQUEST_API_KEY_SECRET CANARY_OIDC_CODE_SECRET \
  CANARY_OIDC_STATE_SECRET CANARY_QUERY_API_KEY_SECRET; do
  if as_root grep -R -F -q "$secret" "$work_root/logs"; then
    fail access_log_secret_leak
  fi
done

# Stop the isolated candidate and prove the live exact runtime did not move.
docker_cmd rm -f "$candidate" >/dev/null
as_root python3 scripts/caddy_container_readonly_validator.py > post-canary-runtime.json
python3 - pre-canary-runtime.json post-canary-runtime.json <<'PY'
import json, sys
before=json.load(open(sys.argv[1],encoding='utf-8'))
after=json.load(open(sys.argv[2],encoding='utf-8'))
keys=('source_sha','image_digest','config_sha256','module_manifest_sha256','listeners')
for key in keys:
    assert before[key] == after[key], key
PY

cat > production-canary-evidence.json <<EOF
{
  "schema": "codestra.caddy.production-readonly-canary.v1",
  "candidate_source_sha": "${CADDY_CANARY_SOURCE_SHA}",
  "candidate_image": "${CADDY_CANARY_IMAGE}",
  "candidate_config_sha256": "${CADDY_CANARY_CONFIG_SHA256}",
  "runtime_config_sha256": "${runtime_config_sha256}",
  "module_count": ${module_count},
  "module_manifest_sha256": "${module_sha256}",
  "tcp_18080": "PASS",
  "tcp_18443": "PASS",
  "udp_18443": "PASS",
  "private_metrics_2021": "PASS",
  "http_redirect": "PASS",
  "public_certificate": "PASS",
  "http2": "PASS",
  "http3": "PASS",
  "hsts": "PASS",
  "request_limit": "PASS",
  "kong_handoff": "PASS",
  "invalid_identity_denied": "PASS",
  "keycloak_issuer": "PASS",
  "keycloak_redirect": "PASS",
  "realtime_readonly_fallback": "PASS",
  "fallback_requests": 1,
  "editor_offnet_denial": "PASS",
  "mtls_without_certificate": "DENIED",
  "mtls_valid_certificate_wrong_source": "DENIED_403",
  "grafana_health": "PASS",
  "superset_health": "PASS",
  "sanitized_logs": "PASS",
  "public_traffic_percent": 0,
  "upstream_mutating_requests": 0,
  "blocked_request_limit_posts": 1,
  "live_runtime_unchanged": true,
  "ssh_changed": false,
  "firewall_changed": false,
  "dns_changed": false,
  "unrelated_workloads_changed": false,
  "result": "PASS"
}
EOF
printf 'CADDY_PRODUCTION_READONLY_CANARY=PASS\n'
cat production-canary-evidence.json
