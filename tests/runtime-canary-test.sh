#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
IMAGE_REF="${1:?usage: runtime-canary-test.sh IMAGE_REF}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
name="codestra-caddy-canary-${GITHUB_RUN_ID:-local}-$$"; work="$(mktemp -d)"; mock_pid=""
cleanup(){
  docker logs "$name" >"$work/caddy-container.log" 2>&1 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
  [[ -z "$mock_pid" ]] || kill "$mock_pid" >/dev/null 2>&1 || true
  if ! rm -rf -- "$work" 2>/dev/null; then
    if command -v sudo >/dev/null 2>&1; then
      sudo -n rm -rf -- "$work" >/dev/null 2>&1 || true
    fi
  fi
  return 0
}
trap cleanup EXIT
on_error(){
  local rc=$?
  trap - ERR
  printf 'CADDY_CANARY_FAILURE=line=%s rc=%s\n' "${BASH_LINENO[0]:-$LINENO}" "$rc" >&2
  docker inspect --format 'CADDY_CANARY_CONTAINER_STATE=running={{.State.Running}} exit={{.State.ExitCode}} error={{json .State.Error}}' "$name" >&2 2>/dev/null || true
  exit "$rc"
}
trap on_error ERR
cp -a "$ROOT/config" "$work/config"
python3 - "$work/config/Caddyfile" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); text=path.read_text(); needle='\tskip_install_trust\n'
if needle not in text: raise SystemExit('canary renderer could not find global block')
path.write_text(text.replace(needle,needle+'\tlocal_certs\n',1))
PY
mkdir -p "$work/pki/middleware" "$work/pki/klyrow" "$work/logs" "$work/data" "$work/runtime-config"
chmod 0777 "$work/logs" "$work/data" "$work/runtime-config"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=Codestra Canary CA' -keyout "$work/pki/ca.key" -out "$work/pki/ca.crt" >/dev/null 2>&1
make_cert(){ local name="$1" dns="$2"; openssl req -newkey rsa:2048 -nodes -subj "/CN=$dns" -addext "subjectAltName=DNS:$dns" -keyout "$work/pki/$name.key" -out "$work/pki/$name.csr" >/dev/null 2>&1; openssl x509 -req -days 1 -in "$work/pki/$name.csr" -CA "$work/pki/ca.crt" -CAkey "$work/pki/ca.key" -CAcreateserial -copy_extensions copy -out "$work/pki/$name.crt" >/dev/null 2>&1; }
make_cert middleware middleware.internal.codestra.agency
make_cert middleware-staging middleware-staging.internal.codestra.agency
make_cert klyrow middleware-email-events.internal.codestra.agency
make_cert client codestra-canary-client
install -m 0644 "$work/pki/middleware.crt" "$work/pki/middleware/server.crt"; install -m 0600 "$work/pki/middleware.key" "$work/pki/middleware/server.key"
install -m 0644 "$work/pki/middleware-staging.crt" "$work/pki/middleware/staging-server.crt"; install -m 0600 "$work/pki/middleware-staging.key" "$work/pki/middleware/staging-server.key"; install -m 0644 "$work/pki/ca.crt" "$work/pki/middleware/client-ca.crt"
install -m 0644 "$work/pki/klyrow.crt" "$work/pki/klyrow/tls-fullchain.crt"; install -m 0600 "$work/pki/klyrow.key" "$work/pki/klyrow/tls.key"; install -m 0644 "$work/pki/ca.crt" "$work/pki/klyrow/klyrow-client.crt"
find "$work/pki" -type f -name '*.key' -exec chmod 0644 {} +
export MOCK_UPSTREAM_LOG="$work/mock-upstreams.jsonl"; python3 "$ROOT/scripts/mock_upstreams.py" >"$work/mock.log" 2>&1 & mock_pid=$!
for _ in $(seq 1 50); do grep -q MOCK_UPSTREAMS=READY "$work/mock.log" 2>/dev/null && break; sleep 0.1; done
grep -q MOCK_UPSTREAMS=READY "$work/mock.log"
common_env=(
-e CADDY_PUBLIC_BIND=127.0.0.2 -e CADDY_PRIVATE_METRICS_BIND=127.0.0.5 -e CADDY_PRIVATE_INGRESS_BIND=127.0.0.4 -e CADDY_KLYROW_SOURCE_CIDRS=127.0.0.1/32 -e CADDY_VICIDIAL_SOURCE_CIDRS=127.0.0.1/32 -e CADDY_STAGING_EVENT_SOURCE_CIDRS=127.0.0.1/32 -e CADDY_KONG_UPSTREAM=127.0.0.1:8000 -e CADDY_REALTIME_UPSTREAM=127.0.0.1:18102 -e CADDY_KEYCLOAK_UPSTREAM=127.0.0.1:18103 -e CADDY_CRM_RESELLER_UPSTREAM=127.0.0.1:18104 -e CADDY_CRM_UPSTREAM=127.0.0.1:18105 -e CADDY_N8N_UPSTREAM=127.0.0.1:18106 -e CADDY_N8N_STAGING_UPSTREAM=127.0.0.1:18107 -e CADDY_STAGING_API_UPSTREAM=127.0.0.1:18108 -e CADDY_STAGING_PORTAL_UPSTREAM=127.0.0.1:18109 -e CADDY_STAGING_KEYCLOAK_UPSTREAM=127.0.0.1:18110 -e CADDY_STAGING_ODOO_UPSTREAM=127.0.0.1:18111 -e CADDY_MIDDLEWARE_CALLBACK_UPSTREAM=127.0.0.1:18112 -e CADDY_AGENT_GATEWAY_UPSTREAM=127.0.0.1:18113 -e CADDY_AGENT_UI_UPSTREAM=127.0.0.1:18114 -e CADDY_MONITORING_UPSTREAM=127.0.0.1:18115 -e CADDY_KLYROW_EVENTS_UPSTREAM=127.0.0.1:18180 -e CADDY_EDITOR_ADMIN_CIDRS=127.0.0.1/32 -e CADDY_N8N_EDITOR_MAX_REQUEST_BODY=16777216 -e CADDY_GRAFANA_UPSTREAM=127.0.0.1:18003 -e CADDY_SUPERSET_UPSTREAM=127.0.0.1:18088 -e CADDY_OPENBAO_UPSTREAM=127.0.0.1:18200 -e CADDY_OPENBAO_ALLOWED_CIDRS=127.0.0.1/32)
docker run -d --name "$name" --network host --user 65532:65532 --read-only --cap-drop ALL --cap-add NET_BIND_SERVICE --security-opt no-new-privileges:true --env XDG_DATA_HOME=/data --env XDG_CONFIG_HOME=/config "${common_env[@]}" --tmpfs /run/caddy:uid=65532,gid=65532,mode=0700 --tmpfs /tmp:uid=65532,gid=65532,mode=0700 --mount "type=bind,src=$work/config,dst=/etc/caddy,readonly" --mount "type=bind,src=$work/logs,dst=/var/log/caddy" --mount "type=bind,src=$work/data,dst=/data" --mount "type=bind,src=$work/runtime-config,dst=/config" --mount "type=bind,src=$work/pki/middleware,dst=/etc/codestra/pki/middleware-private-ingress,readonly" --mount "type=bind,src=$work/pki/klyrow,dst=/etc/caddy/private/klyrow-events,readonly" "$IMAGE_REF" >/dev/null
for _ in $(seq 1 90); do curl --fail --silent --max-time 2 http://127.0.0.5:2020/healthz >/dev/null 2>&1 && break; test "$(docker inspect --format '{{.State.Running}}' "$name")" = true; sleep 1; done
curl --fail --silent --max-time 5 http://127.0.0.5:2020/healthz | grep -q ok
pid="$(docker inspect --format '{{.State.Pid}}' "$name")"
has_socket(){ local port_hex="$1"; shift; awk -v port="$port_hex" 'NR>1 {split($2,address,":"); if (toupper(address[2])==port) found=1} END {exit !found}' "$@"; }
has_socket 0050 "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/udp" "/proc/$pid/net/udp6"
status="$(curl -sS -o /dev/null -w '%{http_code}' --resolve api.codestra.co:80:127.0.0.2 http://api.codestra.co/api/v1/health)"; [[ "$status" =~ ^30[178]$ ]]
headers="$(curl -ksSI --resolve api.codestra.co:443:127.0.0.2 https://api.codestra.co/api/v1/health)"; grep -qi '^strict-transport-security: max-age=31536000' <<<"$headers"; grep -qi '^HTTP/.* 200' <<<"$headers"
openssl s_client -connect 127.0.0.2:443 -servername api.codestra.co -alpn h2 </dev/null 2>/dev/null | grep -q 'ALPN protocol: h2'
python3 "$ROOT/scripts/websocket_probe.py" api.codestra.co 127.0.0.2 /ws/agent
unknown="$(curl -ksS -o /dev/null -w '%{http_code}' --resolve api.codestra.co:443:127.0.0.2 https://api.codestra.co/not-contracted)"; test "$unknown" = 404
legacy="$(curl -ksS --resolve api.codestra.agency:443:127.0.0.2 https://api.codestra.agency/api/v1/health)"; grep -q '"port": 8000' <<<"$legacy"
redirect_headers="$(curl -ksSI --resolve automation.codestra.co:443:127.0.0.2 https://automation.codestra.co/)"; grep -q '^HTTP/.* 302' <<<"$redirect_headers"; grep -qi '^location: https://auth\.codestra\.co/realms/codestra/' <<<"$redirect_headers"
denied_editor="$(curl --interface 127.0.0.3 -ksS -o /dev/null -w '%{http_code}' --resolve automation.codestra.co:443:127.0.0.2 https://automation.codestra.co/)"; test "$denied_editor" = 404
denied_bao="$(curl --interface 127.0.0.3 -ksS -o /dev/null -w '%{http_code}' --resolve bao.codestra.media:443:127.0.0.2 https://bao.codestra.media/)"; test "$denied_bao" = 403
without_cert="$(curl -ksS -o /dev/null -w '%{http_code}' --resolve middleware-email-events.internal.codestra.agency:18080:127.0.0.4 https://middleware-email-events.internal.codestra.agency:18080/internal/provider-events/klyrow || true)"; [[ "$without_cert" == 000 || "$without_cert" == 400 ]]
with_cert="$(curl -ksS --cert "$work/pki/client.crt" --key "$work/pki/client.key" --resolve middleware-email-events.internal.codestra.agency:18080:127.0.0.4 https://middleware-email-events.internal.codestra.agency:18080/internal/provider-events/klyrow)"; grep -q '"port": 18180' <<<"$with_cert"
limit_status="$(head -c 10485761 /dev/zero | curl -ksS -o /dev/null -w '%{http_code}' --resolve api.codestra.co:443:127.0.0.2 --data-binary @- https://api.codestra.co/api/v1/health)"; test "$limit_status" = 413
auth_value='Bearer caddy-canary-auth-secret'; cookie_value='session=caddy-canary-cookie-secret'; api_key_value='caddy-canary-api-key-secret'
curl -ksS --resolve api.codestra.co:443:127.0.0.2 -H "Authorization: $auth_value" -H "Cookie: $cookie_value" -H "X-Api-Key: $api_key_value" 'https://api.codestra.co/api/v1/health?apikey=caddy-canary-query-secret&code=caddy-canary-code-secret&state=caddy-canary-state-secret' >/dev/null
docker stop --time 10 "$name" >/dev/null
for secret in caddy-canary-auth-secret caddy-canary-cookie-secret caddy-canary-api-key-secret caddy-canary-query-secret caddy-canary-code-secret caddy-canary-state-secret; do ! grep -R -F "$secret" "$work/logs" || { echo "CADDY_CANARY_REDACTION=FAIL:$secret" >&2; exit 1; }; done
grep -q '"port": 8000' "$work/mock-upstreams.jsonl"; grep -q '"port": 18102' "$work/mock-upstreams.jsonl"; grep -q '"port": 18180' "$work/mock-upstreams.jsonl"
printf '%s\n' CADDY_TCP_80_CANARY=PASS CADDY_TCP_443_CANARY=PASS CADDY_UDP_443_BIND=PASS CADDY_HTTP2_CANARY=PASS CADDY_LOCAL_TLS_CANARY=PASS CADDY_REDIRECT_CANARY=PASS CADDY_HSTS_CANARY=PASS CADDY_REQUEST_LIMIT_CANARY=PASS CADDY_WEBSOCKET_CANARY=PASS CADDY_KONG_HANDOFF_CANARY=PASS CADDY_KEYCLOAK_REDIRECT_CANARY=PASS CADDY_MTLS_CANARY=PASS CADDY_EDITOR_DENIAL_CANARY=PASS CADDY_UPSTREAM_HEALTH_CANARY=PASS CADDY_LOG_REDACTION_CANARY=PASS CANARY_CERTIFICATION=PASS
