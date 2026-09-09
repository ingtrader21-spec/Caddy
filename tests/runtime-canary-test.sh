#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

IMAGE_REF="${1:?usage: runtime-canary-test.sh IMAGE_REF}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="codestra-caddy-canary-${GITHUB_RUN_ID:-local}-$$"
WORK="$(mktemp -d)"
MOCK_PID=""
STAGE="setup"

cleanup() {
  docker logs "$NAME" >"$WORK/caddy-container.log" 2>&1 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  [[ -z "$MOCK_PID" ]] || kill "$MOCK_PID" >/dev/null 2>&1 || true
  if ! rm -rf -- "$WORK" 2>/dev/null; then
    command -v sudo >/dev/null 2>&1 && sudo -n rm -rf -- "$WORK" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

on_error() {
  local rc=$?
  trap - ERR
  printf 'CADDY_CANARY_FAILURE=stage=%s line=%s rc=%s\n' "$STAGE" "${BASH_LINENO[0]:-$LINENO}" "$rc" >&2
  docker inspect --format 'CADDY_CANARY_CONTAINER_STATE=running={{.State.Running}} exit={{.State.ExitCode}} error={{json .State.Error}}' "$NAME" >&2 2>/dev/null || true
  if [[ "$(docker inspect --format '{{.State.Running}}' "$NAME" 2>/dev/null || true)" == false ]]; then
    docker logs --tail 120 "$NAME" 2>&1 |
      sed -E \
        -e 's/(Authorization|Proxy-Authorization|Cookie|Apikey|X-Api-Key|X-Auth-Request-Access-Token|X-Access-Token|X-Id-Token|X-Refresh-Token|X-Vault-Token|X-Bao-Token)([^[:space:]]*)/\1=REDACTED/Ig' \
        -e 's/(access_token|api-key|api_key|apikey|client_secret|code|id_token|oauth_token|refresh_token|session_state|state|token)=([^&[:space:]"}]+)/\1=REDACTED/Ig' >&2 || true
  fi
  exit "$rc"
}
trap on_error ERR

STAGE="render-config"
cp -a "$ROOT/config" "$WORK/config"
python3 - "$WORK/config/Caddyfile" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "\tskip_install_trust\n"
if needle not in text:
    raise SystemExit("canary renderer could not find global block")
path.write_text(text.replace(needle, needle + "\tlocal_certs\n", 1), encoding="utf-8")
PY

mkdir -p "$WORK/pki/middleware" "$WORK/pki/klyrow" "$WORK/logs" "$WORK/data" "$WORK/runtime-config"
chmod 0755 "$WORK" "$WORK/pki" "$WORK/pki/middleware" "$WORK/pki/klyrow"
chmod 0777 "$WORK/logs" "$WORK/data" "$WORK/runtime-config"

STAGE="create-ephemeral-pki"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=Codestra Canary CA' \
  -keyout "$WORK/pki/ca.key" -out "$WORK/pki/ca.crt" >/dev/null 2>&1
make_cert() {
  local name="$1" dns="$2"
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$dns" \
    -addext "subjectAltName=DNS:$dns" \
    -keyout "$WORK/pki/$name.key" -out "$WORK/pki/$name.csr" >/dev/null 2>&1
  openssl x509 -req -days 1 -in "$WORK/pki/$name.csr" \
    -CA "$WORK/pki/ca.crt" -CAkey "$WORK/pki/ca.key" -CAcreateserial \
    -copy_extensions copy -out "$WORK/pki/$name.crt" >/dev/null 2>&1
}
make_cert middleware middleware.internal.codestra.agency
make_cert middleware-staging middleware-staging.internal.codestra.agency
make_cert klyrow middleware-email-events.internal.codestra.agency
make_cert client codestra-canary-client
install -m 0644 "$WORK/pki/middleware.crt" "$WORK/pki/middleware/server.crt"
install -m 0644 "$WORK/pki/middleware.key" "$WORK/pki/middleware/server.key"
install -m 0644 "$WORK/pki/middleware-staging.crt" "$WORK/pki/middleware/staging-server.crt"
install -m 0644 "$WORK/pki/middleware-staging.key" "$WORK/pki/middleware/staging-server.key"
install -m 0644 "$WORK/pki/ca.crt" "$WORK/pki/middleware/client-ca.crt"
install -m 0644 "$WORK/pki/klyrow.crt" "$WORK/pki/klyrow/tls-fullchain.crt"
install -m 0644 "$WORK/pki/klyrow.key" "$WORK/pki/klyrow/tls.key"
install -m 0644 "$WORK/pki/ca.crt" "$WORK/pki/klyrow/klyrow-client.crt"
chmod 0644 "$WORK/pki/client.crt" "$WORK/pki/client.key"

STAGE="render-runtime-environment"
python3 - "$ROOT/config/runtime-values.example" "$WORK/canary.env" <<'PY'
from pathlib import Path
import sys
source, target = map(Path, sys.argv[1:])
values = {}
for raw in source.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    name, value = line.split("=", 1)
    values[name] = value
values.update({
    "CADDY_PUBLIC_BIND": "127.0.0.2",
    "CADDY_PRIVATE_METRICS_BIND": "127.0.0.5",
    "CADDY_PRIVATE_INGRESS_BIND": "127.0.0.4",
    "CADDY_KLYROW_SOURCE_CIDRS": "127.0.0.1/32",
    "CADDY_VICIDIAL_SOURCE_CIDRS": "127.0.0.1/32",
    "CADDY_STAGING_EVENT_SOURCE_CIDRS": "127.0.0.1/32",
    "CADDY_EDITOR_ADMIN_CIDRS": "127.0.0.1/32",
    "CADDY_OPENBAO_ALLOWED_CIDRS": "127.0.0.1/32",
})
target.write_text("".join(f"{name}={value}\n" for name, value in sorted(values.items())), encoding="utf-8")
PY

STAGE="start-mock-upstreams"
export MOCK_UPSTREAM_LOG="$WORK/mock-upstreams.jsonl"
python3 "$ROOT/scripts/mock_upstreams.py" >"$WORK/mock.log" 2>&1 &
MOCK_PID=$!
for _ in $(seq 1 50); do
  grep -q MOCK_UPSTREAMS=READY "$WORK/mock.log" 2>/dev/null && break
  sleep 0.1
done
grep -q MOCK_UPSTREAMS=READY "$WORK/mock.log"

STAGE="start-caddy-container"
docker run -d --name "$NAME" --network host \
  --user 65532:65532 --read-only --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  --env XDG_DATA_HOME=/data --env XDG_CONFIG_HOME=/config \
  --env-file "$WORK/canary.env" \
  --tmpfs /run/caddy:uid=65532,gid=65532,mode=0700 \
  --tmpfs /tmp:uid=65532,gid=65532,mode=0700 \
  --mount "type=bind,src=$WORK/config,dst=/etc/caddy,readonly" \
  --mount "type=bind,src=$WORK/logs,dst=/var/log/caddy" \
  --mount "type=bind,src=$WORK/data,dst=/data" \
  --mount "type=bind,src=$WORK/runtime-config,dst=/config" \
  --mount "type=bind,src=$WORK/pki/middleware,dst=/etc/codestra/pki/middleware-private-ingress,readonly" \
  --mount "type=bind,src=$WORK/pki/klyrow,dst=/etc/caddy/private/klyrow-events,readonly" \
  "$IMAGE_REF" >/dev/null

STAGE="wait-for-health"
for _ in $(seq 1 90); do
  curl --fail --silent --max-time 2 http://127.0.0.5:2020/healthz >/dev/null 2>&1 && break
  test "$(docker inspect --format '{{.State.Running}}' "$NAME")" = true
  sleep 1
done
curl --fail --silent --max-time 5 http://127.0.0.5:2020/healthz | grep -q ok

STAGE="listener-checks"
pid="$(docker inspect --format '{{.State.Pid}}' "$NAME")"
has_socket() {
  local port_hex="$1"
  shift
  awk -v port="$port_hex" 'NR>1 {split($2,address,":"); if (toupper(address[2])==port) found=1} END {exit !found}' "$@"
}
has_socket 0050 "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/udp" "/proc/$pid/net/udp6"

STAGE="http-redirect"
status="$(curl -sS -o /dev/null -w '%{http_code}' --resolve api.codestra.co:80:127.0.0.2 http://api.codestra.co/api/v1/health)"
[[ "$status" =~ ^30[178]$ ]]

STAGE="https-hsts-http2"
headers="$(curl -ksSI --resolve api.codestra.co:443:127.0.0.2 https://api.codestra.co/api/v1/health)"
grep -qi '^strict-transport-security: max-age=31536000' <<<"$headers"
grep -qi '^HTTP/.* 200' <<<"$headers"
openssl s_client -connect 127.0.0.2:443 -servername api.codestra.co -alpn h2 </dev/null 2>/dev/null | grep -q 'ALPN protocol: h2'

STAGE="public-readonly-canary-methods"
for path in /healthz /readyz /version; do
  get_status="$(curl -ksS -o /dev/null -w '%{http_code}' \
    --resolve api.codestra.co:443:127.0.0.2 "https://api.codestra.co${path}")"
  test "$get_status" = 200
  head_status="$(curl -ksSI -o /dev/null -w '%{http_code}' \
    --resolve api.codestra.co:443:127.0.0.2 "https://api.codestra.co${path}")"
  test "$head_status" = 200
  for method in POST PUT PATCH DELETE; do
    status="$(curl -ksS -X "$method" -o /dev/null -w '%{http_code}' \
      --resolve api.codestra.co:443:127.0.0.2 "https://api.codestra.co${path}")"
    test "$status" = 405
  done
done

STAGE="websocket-and-http3"
python3 "$ROOT/scripts/websocket_probe.py" api.codestra.co 127.0.0.2 /ws/agent

STAGE="kong-and-closed-fallback"
unknown="$(curl -ksS -o /dev/null -w '%{http_code}' --resolve api.codestra.co:443:127.0.0.2 https://api.codestra.co/not-contracted)"
test "$unknown" = 404
legacy="$(curl -ksS --resolve api.codestra.agency:443:127.0.0.2 https://api.codestra.agency/api/v1/health)"
grep -q '"port": 8000' <<<"$legacy"

STAGE="staging-kong-isolation"
for host in api.staging.internal.codestra.agency bridge-staging.codestra.agency; do
  staging="$(curl -ksS --resolve "$host:443:127.0.0.2" "https://$host/api/v1/health")"
  grep -q '"port": 18000' <<<"$staging"
  grep -q '"host": "api.codestra.co"' <<<"$staging"
done
private_callback="$(curl -ksS -o /dev/null -w '%{http_code}' \
  --resolve bridge-staging.codestra.agency:443:127.0.0.2 \
  https://bridge-staging.codestra.agency/api/v1/events/vicidial)"
test "$private_callback" = 404

STAGE="keycloak-and-access-denials"
redirect_headers="$(curl -ksSI --resolve automation.codestra.co:443:127.0.0.2 https://automation.codestra.co/)"
grep -q '^HTTP/.* 302' <<<"$redirect_headers"
grep -qi '^location: https://auth\.codestra\.co/realms/codestra/' <<<"$redirect_headers"
denied_editor="$(curl --interface 127.0.0.3 -ksS -o /dev/null -w '%{http_code}' --resolve automation.codestra.co:443:127.0.0.2 https://automation.codestra.co/)"
test "$denied_editor" = 404
denied_bao="$(curl --interface 127.0.0.3 -ksS -o /dev/null -w '%{http_code}' --resolve bao.codestra.media:443:127.0.0.2 https://bao.codestra.media/)"
test "$denied_bao" = 403

STAGE="mtls"
without_cert="$(curl -ksS --request POST --data '{}' -o /dev/null -w '%{http_code}' \
  --resolve middleware-email-events.internal.codestra.agency:18080:127.0.0.4 \
  https://middleware-email-events.internal.codestra.agency:18080/internal/provider-events/klyrow || true)"
[[ "$without_cert" == 000 || "$without_cert" == 400 ]]
with_cert="$(curl -ksS --request POST --data '{}' \
  --cert "$WORK/pki/client.crt" --key "$WORK/pki/client.key" \
  --resolve middleware-email-events.internal.codestra.agency:18080:127.0.0.4 \
  https://middleware-email-events.internal.codestra.agency:18080/internal/provider-events/klyrow)"
grep -q '"port": 18180' <<<"$with_cert"

STAGE="request-limit"
limit_status="$(head -c 10485761 /dev/zero | curl -ksS -o /dev/null -w '%{http_code}' \
  --resolve api.codestra.co:443:127.0.0.2 --data-binary @- \
  https://api.codestra.co/api/v1/health)"
test "$limit_status" = 413

STAGE="log-redaction"
auth_value='Bearer caddy-canary-auth-secret'
cookie_value='session=caddy-canary-cookie-secret'
api_key_value='caddy-canary-api-key-secret'
curl -ksS --resolve api.codestra.co:443:127.0.0.2 \
  -H "Authorization: $auth_value" -H "Cookie: $cookie_value" -H "X-Api-Key: $api_key_value" \
  'https://api.codestra.co/api/v1/health?apikey=caddy-canary-query-secret&code=caddy-canary-code-secret&state=caddy-canary-state-secret' >/dev/null
docker stop --time 10 "$NAME" >/dev/null

# A redaction test is valid only when every generated access log is present and
# readable. Normalize ownership in this disposable runner sandbox; never treat
# grep's permission/error exit code as proof that a secret is absent.
if ! find "$WORK/logs" -type f -print -quit | grep -q .; then
  echo CADDY_CANARY_LOGS=FAIL:no_access_logs >&2
  exit 1
fi
if find "$WORK/logs" -type f ! -readable -print -quit | grep -q .; then
  command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 || {
    echo CADDY_CANARY_LOGS=FAIL:read_access_logs >&2
    exit 1
  }
  sudo -n chown -R "$(id -u):$(id -g)" "$WORK/logs"
fi
while IFS= read -r -d '' log_file; do
  [[ -r "$log_file" ]] || {
    echo CADDY_CANARY_LOGS=FAIL:unreadable_access_log >&2
    exit 1
  }
done < <(find "$WORK/logs" -type f -print0)

for secret in \
  caddy-canary-auth-secret caddy-canary-cookie-secret caddy-canary-api-key-secret \
  caddy-canary-query-secret caddy-canary-code-secret caddy-canary-state-secret; do
  if grep -R -F --quiet -- "$secret" "$WORK/logs"; then
  grep_status=0
else
  grep_status=$?
fi
  case "$grep_status" in
    0)
      echo "CADDY_CANARY_REDACTION=FAIL:$secret" >&2
      exit 1
      ;;
    1)
      ;;
    *)
      echo CADDY_CANARY_LOGS=FAIL:grep_error >&2
      exit 1
      ;;
  esac
done

grep -q '"port": 8000' "$WORK/mock-upstreams.jsonl"
grep -q '"port": 18102' "$WORK/mock-upstreams.jsonl"
grep -q '"port": 18180' "$WORK/mock-upstreams.jsonl"

printf '%s\n' \
  CADDY_TCP_80_CANARY=PASS \
  CADDY_TCP_443_CANARY=PASS \
  CADDY_UDP_443_BIND=PASS \
  CADDY_HTTP2_CANARY=PASS \
  CADDY_HTTP3_CANARY=PASS \
  CADDY_LOCAL_TLS_CANARY=PASS \
  CADDY_REDIRECT_CANARY=PASS \
  CADDY_HSTS_CANARY=PASS \
  CADDY_REQUEST_LIMIT_CANARY=PASS \
  CADDY_WEBSOCKET_CANARY=PASS \
  CADDY_KONG_HANDOFF_CANARY=PASS \
  CADDY_KEYCLOAK_REDIRECT_CANARY=PASS \
  CADDY_MTLS_CANARY=PASS \
  CADDY_EDITOR_DENIAL_CANARY=PASS \
  CADDY_UPSTREAM_HEALTH_CANARY=PASS \
  CADDY_LOG_REDACTION_CANARY=PASS \
  CANARY_CERTIFICATION=PASS
