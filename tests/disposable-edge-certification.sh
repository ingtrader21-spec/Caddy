#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

image="${1:?immutable Caddy image is required}"
root="$(mktemp -d)"
container="codestra-caddy-disposable-${RANDOM}"
pids=()
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  for pid in "${pids[@]}"; do kill "$pid" >/dev/null 2>&1 || true; done
  rm -rf -- "$root"
}
trap cleanup EXIT
mkdir -p "$root/config/snippets" "$root/config/pki" "$root/logs" "$root/go-http3"
cp config/snippets/security_headers.caddy "$root/config/snippets/security_headers.caddy"

openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=Codestra disposable CA' \
  -keyout "$root/config/pki/ca.key" -out "$root/config/pki/ca.crt" >/dev/null 2>&1
for name in mtls client; do
  openssl req -newkey rsa:2048 -nodes -subj "/CN=${name}.edge.test" \
    -keyout "$root/config/pki/${name}.key" -out "$root/config/pki/${name}.csr" >/dev/null 2>&1
  extension='subjectAltName=DNS:mtls.edge.test,IP:127.0.0.1'
  [[ "$name" == client ]] && extension='extendedKeyUsage=clientAuth'
  openssl x509 -req -days 1 -in "$root/config/pki/${name}.csr" \
    -CA "$root/config/pki/ca.crt" -CAkey "$root/config/pki/ca.key" -CAcreateserial \
    -extfile <(printf '%s\n' "$extension") \
    -out "$root/config/pki/${name}.crt" >/dev/null 2>&1
done

cat >"$root/mock_http.py" <<'PY'
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, sys
kind=sys.argv[1]
port=int(sys.argv[2])
class Handler(BaseHTTPRequestHandler):
    def answer(self):
        if kind == 'keycloak':
            self.send_response(302)
            self.send_header('Location','https://auth.codestra.co/realms/codestra/protocol/openid-connect/auth')
        else:
            payload=json.dumps({'backend':kind,'path':self.path}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Set-Cookie','session=RESPONSE_COOKIE_SECRET; Secure; HttpOnly')
            self.send_header('X-Auth-Request-Access-Token','RESPONSE_TOKEN_SECRET')
        self.end_headers()
        if kind != 'keycloak': self.wfile.write(payload)
    do_GET=answer
    do_HEAD=answer
    do_POST=answer
    def log_message(self,*args): pass
ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
PY
python3 "$root/mock_http.py" kong 19000 & pids+=("$!")
python3 "$root/mock_http.py" keycloak 19002 & pids+=("$!")

cat >"$root/mock_ws.py" <<'PY'
import socket
server=socket.socket(); server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
server.bind(('127.0.0.1',19001)); server.listen()
while True:
    conn,_=server.accept(); data=conn.recv(65535)
    if b'Upgrade: websocket' in data or b'upgrade: websocket' in data.lower():
        conn.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: disposable\r\n\r\n')
    else: conn.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n')
    conn.close()
PY
python3 "$root/mock_ws.py" & pids+=("$!")

cat >"$root/config/Caddyfile" <<'EOF'
{
	admin off
	skip_install_trust
}
import snippets/*.caddy

http://api.edge.test:18080 {
	redir https://api.edge.test:18443{uri} 308
}

https://api.edge.test:18443 {
	tls internal
	import security_headers
	request_body {
		max_size 1KB
	}
	route {
		@ws path /ws
		reverse_proxy @ws 127.0.0.1:19001
		reverse_proxy 127.0.0.1:19000
	}
	log {
		output file /var/log/caddy/api.log
		import secure_log_filter
	}
}

https://auth.edge.test:18444 {
	tls internal
	import security_headers
	reverse_proxy 127.0.0.1:19002
	log {
		output file /var/log/caddy/auth.log
		import secure_log_filter
	}
}

https://editor.edge.test:18445 {
	tls internal
	import security_headers
	@offnet not remote_ip 192.0.2.0/24
	route {
		handle @offnet {
			respond "Not Found" 404
		}
		handle {
			reverse_proxy 127.0.0.1:19000
		}
	}
	log {
		output file /var/log/caddy/editor.log
		import secure_log_filter
	}
}

https://mtls.edge.test:18446 {
	tls /etc/caddy/pki/mtls.crt /etc/caddy/pki/mtls.key {
		client_auth {
			mode require_and_verify
			trust_pool file /etc/caddy/pki/ca.crt
		}
	}
	import security_headers
	reverse_proxy 127.0.0.1:19000
	log {
		output file /var/log/caddy/mtls.log
		import secure_log_filter
	}
}
EOF

docker run -d --name "$container" --network host --read-only \
  --user 65532:65532 --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  --tmpfs /data:uid=65532,gid=65532,mode=0700 \
  --tmpfs /config:uid=65532,gid=65532,mode=0700 \
  -v "$root/config:/etc/caddy:ro" \
  -v "$root/logs:/var/log/caddy" \
  "$image" >/dev/null

for attempt in $(seq 1 60); do
  if curl --silent --show-error --max-time 2 --resolve api.edge.test:18080:127.0.0.1 \
    http://api.edge.test:18080/healthz >/dev/null; then break; fi
  [[ "$attempt" -lt 60 ]] || { docker logs "$container"; exit 1; }
  sleep 1
done

docker cp "$container:/data/caddy/pki/authorities/local/root.crt" "$root/internal-ca.crt"

status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --resolve api.edge.test:18080:127.0.0.1 http://api.edge.test:18080/healthz)"
test "$status" = 308
printf 'CADDY_HTTP_REDIRECT=PASS\n'

headers="$(curl --silent --show-error --http2 --cacert "$root/internal-ca.crt" \
  --resolve api.edge.test:18443:127.0.0.1 -D - https://api.edge.test:18443/healthz -o "$root/body.json")"
grep -q '"backend": "kong"' "$root/body.json"
grep -Eqi '^strict-transport-security: max-age=31536000; includeSubDomains' <<<"$headers"
printf 'CADDY_HTTPS_CERTIFICATE=PASS\nCADDY_HTTP2=PASS\nCADDY_HSTS=PASS\nCADDY_KONG_HANDOFF=PASS\n'

status="$(dd if=/dev/zero bs=2048 count=1 2>/dev/null | curl --silent --output /dev/null \
  --write-out '%{http_code}' --cacert "$root/internal-ca.crt" \
  --resolve api.edge.test:18443:127.0.0.1 -X POST --data-binary @- \
  https://api.edge.test:18443/oversized)"
test "$status" = 413
printf 'CADDY_REQUEST_LIMIT=PASS\n'

cat >"$root/ws_client.py" <<'PY'
import base64, os, socket, ssl, sys
ctx=ssl.create_default_context(cafile=sys.argv[1])
with socket.create_connection(('127.0.0.1',18443),timeout=5) as raw:
  with ctx.wrap_socket(raw,server_hostname='api.edge.test') as sock:
    key=base64.b64encode(os.urandom(16)).decode()
    req=(f'GET /ws HTTP/1.1\r\nHost: api.edge.test:18443\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n')
    sock.sendall(req.encode()); response=sock.recv(4096)
    assert b' 101 ' in response, response
PY
python3 "$root/ws_client.py" "$root/internal-ca.crt"
printf 'CADDY_WEBSOCKET=PASS\n'

cat >"$root/go-http3/go.mod" <<'EOF'
module codestra-caddy-http3-certification

go 1.26

require github.com/quic-go/quic-go v0.59.1
EOF
cat >"$root/go-http3/main.go" <<'EOF'
package main
import (
  "crypto/tls"
  "crypto/x509"
  "io"
  "net/http"
  "os"
  "time"
  "github.com/quic-go/quic-go/http3"
)
func main() {
  pem, err := os.ReadFile(os.Args[1]); if err != nil { panic(err) }
  roots := x509.NewCertPool(); if !roots.AppendCertsFromPEM(pem) { panic("CA") }
  transport := &http3.Transport{TLSClientConfig:&tls.Config{RootCAs:roots,ServerName:"api.edge.test",MinVersion:tls.VersionTLS13}}
  defer transport.Close()
  client := &http.Client{Transport:transport,Timeout:10*time.Second}
  response, err := client.Get("https://127.0.0.1:18443/healthz"); if err != nil { panic(err) }
  defer response.Body.Close(); body, _ := io.ReadAll(response.Body)
  if response.StatusCode != 200 || len(body) == 0 { panic("HTTP3 response") }
}
EOF
(cd "$root/go-http3" && go mod tidy && go run . "$root/internal-ca.crt")
printf 'CADDY_HTTP3=PASS\n'

location="$(curl --silent --show-error --cacert "$root/internal-ca.crt" \
  --resolve auth.edge.test:18444:127.0.0.1 -D - https://auth.edge.test:18444/login -o /dev/null | \
  awk 'BEGIN{IGNORECASE=1} /^location:/{sub(/\r$/,""); print $2}')"
[[ "$location" == https://auth.codestra.co/realms/codestra/* ]]
printf 'CADDY_KEYCLOAK_REDIRECT=PASS\n'

status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  --cacert "$root/internal-ca.crt" --resolve editor.edge.test:18445:127.0.0.1 \
  https://editor.edge.test:18445/)"
test "$status" = 404
printf 'CADDY_EDITOR_OFFNET_DENIAL=PASS\n'

if curl --silent --show-error --cacert "$root/config/pki/ca.crt" \
  --resolve mtls.edge.test:18446:127.0.0.1 https://mtls.edge.test:18446/ >/dev/null 2>&1; then
  echo 'mTLS route accepted a client without a certificate' >&2; exit 1
fi
curl --fail --silent --show-error --cacert "$root/config/pki/ca.crt" \
  --cert "$root/config/pki/client.crt" --key "$root/config/pki/client.key" \
  --resolve mtls.edge.test:18446:127.0.0.1 https://mtls.edge.test:18446/ >/dev/null
printf 'CADDY_MTLS_DENIAL=PASS\nCADDY_MTLS_ACCEPTANCE=PASS\n'

curl --fail --silent --show-error --cacert "$root/internal-ca.crt" \
  --resolve api.edge.test:18443:127.0.0.1 \
  -H 'Authorization: Bearer REQUEST_TOKEN_SECRET' \
  -H 'Cookie: session=REQUEST_COOKIE_SECRET' \
  -H 'X-Api-Key: REQUEST_API_KEY_SECRET' \
  'https://api.edge.test:18443/healthz?code=OIDC_CODE_SECRET&state=OIDC_STATE_SECRET&apikey=QUERY_API_KEY_SECRET' >/dev/null
sleep 1
docker cp "$container:/var/log/caddy/." "$root/log-copy" >/dev/null
for secret in REQUEST_TOKEN_SECRET REQUEST_COOKIE_SECRET REQUEST_API_KEY_SECRET OIDC_CODE_SECRET OIDC_STATE_SECRET QUERY_API_KEY_SECRET RESPONSE_COOKIE_SECRET RESPONSE_TOKEN_SECRET; do
  if grep -R -F -q "$secret" "$root/log-copy"; then
    echo "access log leaked a protected value" >&2; exit 1
  fi
done
printf 'CADDY_SANITIZED_LOGS=PASS\nCADDY_UPSTREAM_HEALTH=PASS\nCADDY_DISPOSABLE_CERTIFICATION=PASS\n'
