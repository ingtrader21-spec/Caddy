#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE_REF="${1:?usage: runtime-bind-test.sh IMAGE_REF}"
name="caddy-runtime-bind-${GITHUB_RUN_ID:-local}-$$"
work="$(mktemp -d)"

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  find "$work" -type f -delete 2>/dev/null || true
  rmdir "$work" 2>/dev/null || true
}
trap cleanup EXIT

diagnose() {
  docker inspect --format \
    'running={{.State.Running}} status={{.State.Status}} exit={{.State.ExitCode}} error={{json .State.Error}} network={{.HostConfig.NetworkMode}}' \
    "$name" >&2 2>/dev/null || true
  docker logs "$name" >&2 2>/dev/null || true
}

fail() {
  printf 'CADDY_RUNTIME_BIND=FAIL:%s\n' "$1" >&2
  diagnose
  exit 2
}

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

# The proof needs only the container's own network namespace. Host networking
# made consecutive candidate/baseline tests contend for host TCP/UDP 80/443 and
# could leave a dead PID between Docker inspection and /proc socket read-back.
docker run --detach --name "$name" \
  --network none \
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

network_mode="$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$name")"
[[ "$network_mode" == none ]] || fail "network_not_isolated:${network_mode}"

has_socket() {
  local port_hex="$1"
  shift
  local table
  for table in "$@"; do
    [[ -r "$table" ]] || continue
    if awk -v port="$port_hex" \
      'NR > 1 {split($2, address, ":"); if (toupper(address[2]) == port) found=1} END {exit !found}' \
      "$table" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

process_snapshot() {
  local running pid status uid gid no_new_privs cap_eff
  running="$(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null)" || return 1
  [[ "$running" == true ]] || return 1
  pid="$(docker inspect --format '{{.State.Pid}}' "$name" 2>/dev/null)" || return 1
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  status="/proc/$pid/status"
  [[ -r "$status" ]] || return 1

  has_socket 0050 "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6" || return 1
  has_socket 01BB "/proc/$pid/net/tcp" "/proc/$pid/net/tcp6" || return 1
  has_socket 01BB "/proc/$pid/net/udp" "/proc/$pid/net/udp6" || return 1

  uid="$(awk '/^Uid:/ {print $2}' "$status" 2>/dev/null)" || return 1
  gid="$(awk '/^Gid:/ {print $2}' "$status" 2>/dev/null)" || return 1
  no_new_privs="$(awk '/^NoNewPrivs:/ {print $2}' "$status" 2>/dev/null)" || return 1
  cap_eff="$(awk '/^CapEff:/ {print $2}' "$status" 2>/dev/null)" || return 1
  [[ -n "$uid" && -n "$gid" && -n "$no_new_privs" && -n "$cap_eff" ]] || return 1

  # Close the inspection race: the same container must still be running after
  # every socket and process-security field has been collected.
  [[ "$(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null)" == true ]] || return 1
  printf '%s %s %s %s %s\n' "$pid" "$uid" "$gid" "$no_new_privs" "$cap_eff"
}

snapshot=''
for _ in $(seq 1 100); do
  if snapshot="$(process_snapshot)"; then
    break
  fi
  running="$(docker inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true)"
  [[ "$running" == true ]] || fail container_exited_before_socket_readback
  sleep 0.1
done
[[ -n "$snapshot" ]] || fail socket_readback_timeout

read -r pid uid gid no_new_privs cap_eff <<<"$snapshot"
[[ "$uid" == 65532 ]] || fail "runtime_uid:${uid}"
[[ "$gid" == 65532 ]] || fail "runtime_gid:${gid}"
[[ "$no_new_privs" == 1 ]] || fail "no_new_privs:${no_new_privs}"
[[ "$cap_eff" == 0000000000000400 ]] || fail "effective_capabilities:${cap_eff}"

printf '%s\n' \
  'CADDY_TCP_80=PASS' \
  'CADDY_TCP_443=PASS' \
  'CADDY_UDP_443=PASS' \
  'CADDY_RUNTIME_UID=65532' \
  'CADDY_RUNTIME_NETWORK=ISOLATED_NONE' \
  'CADDY_EFFECTIVE_CAPABILITIES=NET_BIND_SERVICE_ONLY'
