#!/usr/bin/env bash
set -euo pipefail

IMAGE_REF="${1:?usage: runtime-bind-test.sh IMAGE_REF}"
name="caddy-runtime-bind-${GITHUB_RUN_ID:-local}-$$"
work="$(mktemp -d)"
cleanup() {
  docker logs "$name" 2>&1 || true
  docker rm -f "$name" >/dev/null 2>&1 || true
  find "$work" -type f -delete 2>/dev/null || true
  rmdir "$work" 2>/dev/null || true
}
trap cleanup EXIT

cat >"$work/Caddyfile" <<'EOF'
{
  admin off
}
:80 {
  respond "caddy-runtime-bind-ok"
}
:443 {
  tls internal
  respond "caddy-runtime-bind-ok"
}
EOF

docker run --detach --name "$name" \
  --network host \
  --user 65532:65532 \
  --read-only \
  --cap-drop ALL \
  --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges:true \
  --env XDG_DATA_HOME=/data \
  --env XDG_CONFIG_HOME=/config \
  --tmpfs /run/caddy:uid=65532,gid=65532,mode=0700 \
  --tmpfs /var/log/caddy:uid=65532,gid=65532,mode=0700 \
  --tmpfs /data:uid=65532,gid=65532,mode=0700 \
  --tmpfs /config:uid=65532,gid=65532,mode=0700 \
  --tmpfs /tmp:uid=65532,gid=65532,mode=0700 \
  --mount "type=bind,src=$work/Caddyfile,dst=/etc/caddy/Caddyfile,readonly" \
  "$IMAGE_REF" run --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

pid="$(docker inspect --format '{{.State.Pid}}' "$name")"
status="/proc/$pid/status"
has_socket() {
  local port_hex="$1"
  shift
  awk -v port="$port_hex" \
    'NR > 1 {split($2, address, ":"); if (toupper(address[2]) == port) found=1} END {exit !found}' \
    "$@"
}
for _ in $(seq 1 30); do
  if test "$(docker inspect --format '{{.State.Running}}' "$name")" = true \
    && has_socket 0050 "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6" \
    && has_socket 01BB "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6" \
    && has_socket 01BB "/proc/$pid/net/udp" "/proc/$pid/net/udp6"; then
    break
  fi
  sleep 1
done
has_socket 0050 "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6"
has_socket 01BB "/proc/$pid/net/udp" "/proc/$pid/net/udp6"
test "$(awk '/^Uid:/ {print $2}' "$status")" = 65532
test "$(awk '/^Gid:/ {print $2}' "$status")" = 65532
test "$(awk '/^NoNewPrivs:/ {print $2}' "$status")" = 1
test "$(awk '/^CapEff:/ {print $2}' "$status")" = 0000000000000400

echo "CADDY_TCP_80=PASS"
echo "CADDY_TCP_443=PASS"
echo "CADDY_UDP_443=PASS"
echo "CADDY_RUNTIME_UID=65532"
echo "CADDY_EFFECTIVE_CAPABILITIES=NET_BIND_SERVICE_ONLY"
