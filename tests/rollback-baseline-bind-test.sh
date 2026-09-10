#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE="$ROOT/config/release-baseline.v1.json"
DOCKER_BIN="${DOCKER_BIN:-docker}"
SS_BIN="${SS_BIN:-ss}"
FLOCK_BIN="${FLOCK_BIN:-flock}"

fail() {
  printf 'CADDY_ROLLBACK_BASELINE_BIND=FAIL:%s\n' "$1" >&2
  if [[ -n "${container:-}" ]]; then
    "$DOCKER_BIN" inspect --format \
      'running={{.State.Running}} status={{.State.Status}} exit={{.State.ExitCode}} error={{json .State.Error}} network={{.HostConfig.NetworkMode}}' \
      "$container" >&2 2>/dev/null || true
    "$DOCKER_BIN" logs "$container" >&2 2>/dev/null || true
  fi
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ -f "$BASELINE" && ! -L "$BASELINE" ]] || fail baseline_file
command -v "$DOCKER_BIN" >/dev/null 2>&1 || fail docker_unavailable
command -v "$SS_BIN" >/dev/null 2>&1 || fail ss_unavailable
command -v "$FLOCK_BIN" >/dev/null 2>&1 || fail flock_unavailable

mapfile -t identity < <(python3 - "$BASELINE" <<'PY'
import json
import re
import sys

item = json.load(open(sys.argv[1], encoding="utf-8"))
assert item.get("schema") == "codestra.caddy-release-baseline.v1"
assert item.get("mutable") is False
source = item.get("source_sha", "")
image = item.get("image", "")
assert re.fullmatch(r"[0-9a-f]{40}", source)
assert re.fullmatch(
    r"ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}", image
)
print(source)
print(image)
PY
)
[[ ${#identity[@]} -eq 2 ]] || fail baseline_identity
readonly baseline_source="${identity[0]}"
readonly baseline_image="${identity[1]}"

"$DOCKER_BIN" pull "$baseline_image" >/dev/null
"$DOCKER_BIN" image inspect "$baseline_image" --format '{{range .RepoDigests}}{{println .}}{{end}}' \
  | grep -Fxq "$baseline_image" || fail repository_digest
[[ "$("$DOCKER_BIN" image inspect "$baseline_image" --format '{{index .Config.Labels "org.opencontainers.image.source"}}')" == \
  https://github.com/appolon1908-hue/Caddy ]] || fail image_source
[[ "$("$DOCKER_BIN" image inspect "$baseline_image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == \
  "$baseline_source" ]] || fail image_revision
[[ "$("$DOCKER_BIN" image inspect "$baseline_image" --format '{{.Config.User}}')" == 65532:65532 ]] || fail image_user

# This compatibility proof deliberately preserves the host-network bind model
# used by the signed baseline's own successful release job. It is serialized
# and may start only when host TCP 80/443 and UDP 443 are all unused.
exec 9>"${TMPDIR:-/tmp}/codestra-caddy-rollback-bind.lock"
"$FLOCK_BIN" -w 60 9 || fail bind_lock_timeout

tcp_ports_in_use() {
  "$SS_BIN" -H -lnt | awk '$4 ~ /:80$/ || $4 ~ /:443$/ {found=1} END {exit found ? 0 : 1}'
}
udp_443_in_use() {
  "$SS_BIN" -H -lnu | awk '$4 ~ /:443$/ {found=1} END {exit found ? 0 : 1}'
}

tcp_ports_in_use && fail host_tcp_listener_in_use
udp_443_in_use && fail host_udp_listener_in_use

work="$(mktemp -d)"
container="caddy-rollback-baseline-bind-${GITHUB_RUN_ID:-local}-$$"
started=false
cleanup() {
  if [[ "$started" == true ]]; then
    "$DOCKER_BIN" rm -f "$container" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$work" >/dev/null 2>&1 || true
}
trap cleanup EXIT
chmod 0755 "$work"
cat >"$work/Caddyfile" <<'EOF'
{
  admin off
  skip_install_trust
}
:80 {
  respond "caddy-rollback-baseline-bind-ok"
}
:443 {
  tls internal
  respond "caddy-rollback-baseline-bind-ok"
}
EOF
chmod 0444 "$work/Caddyfile"

"$DOCKER_BIN" run --detach --name "$container" \
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
  --entrypoint /usr/bin/caddy \
  "$baseline_image" run --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
started=true

[[ "$("$DOCKER_BIN" inspect --format '{{.HostConfig.NetworkMode}}' "$container")" == host ]] || fail network_contract

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
  running="$("$DOCKER_BIN" inspect --format '{{.State.Running}}' "$container" 2>/dev/null)" || return 1
  [[ "$running" == true ]] || return 1
  pid="$("$DOCKER_BIN" inspect --format '{{.State.Pid}}' "$container" 2>/dev/null)" || return 1
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

  [[ "$("$DOCKER_BIN" inspect --format '{{.State.Running}}' "$container" 2>/dev/null)" == true ]] || return 1
  printf '%s %s %s %s %s\n' "$pid" "$uid" "$gid" "$no_new_privs" "$cap_eff"
}

snapshot=''
for _ in $(seq 1 100); do
  if snapshot="$(process_snapshot)"; then
    break
  fi
  running="$("$DOCKER_BIN" inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)"
  [[ "$running" == true ]] || fail container_exited_before_socket_readback
  sleep 0.1
done
[[ -n "$snapshot" ]] || fail socket_readback_timeout

read -r _pid uid gid no_new_privs cap_eff <<<"$snapshot"
[[ "$uid" == 65532 ]] || fail "runtime_uid:${uid}"
[[ "$gid" == 65532 ]] || fail "runtime_gid:${gid}"
[[ "$no_new_privs" == 1 ]] || fail "no_new_privs:${no_new_privs}"
[[ "$cap_eff" == 0000000000000400 ]] || fail "effective_capabilities:${cap_eff}"

"$DOCKER_BIN" rm -f "$container" >/dev/null
started=false
released=false
for _ in $(seq 1 50); do
  if ! tcp_ports_in_use && ! udp_443_in_use; then
    released=true
    break
  fi
  sleep 0.1
done
[[ "$released" == true ]] || fail host_listeners_not_released

printf '%s\n' \
  'CADDY_ROLLBACK_BASELINE_BIND=PASS' \
  "ROLLBACK_BIND_SOURCE_SHA=$baseline_source" \
  "ROLLBACK_BIND_IMAGE=$baseline_image" \
  'ROLLBACK_BIND_NETWORK=SERIALIZED_HOST' \
  'ROLLBACK_BIND_RUNTIME_UID=65532' \
  'ROLLBACK_BIND_EFFECTIVE_CAPABILITIES=NET_BIND_SERVICE_ONLY' \
  'ROLLBACK_BIND_LISTENERS_RELEASED=true'
