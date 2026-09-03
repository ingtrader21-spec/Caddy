#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

candidate_image="${1:?candidate image is required}"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/release/previous-production.env"

[[ "$CADDY_PREVIOUS_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$CADDY_PREVIOUS_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
test "$CADDY_PREVIOUS_IMAGE" = "ghcr.io/appolon1908-hue/codestra-caddy@${CADDY_PREVIOUS_IMAGE_DIGEST}"

root="$(mktemp -d)"
port="$((21000 + RANDOM % 2000))"
current="codestra-caddy-current-${RANDOM}"
previous="codestra-caddy-previous-${RANDOM}"
pids=()
cleanup() {
  docker rm -f "$current" "$previous" >/dev/null 2>&1 || true
  rm -rf -- "$root"
}
trap cleanup EXIT
mkdir -p "$root/config" "$root/old-config"

cat >"$root/config/Caddyfile" <<EOF
{
	admin off
}
http://127.0.0.1:${port} {
	respond /healthz "healthy" 200
	respond /version "rollback-rehearsal" 200
}
EOF

start_and_probe() {
  local name="$1"
  local image="$2"
  local started_ns ready_ns
  started_ns="$(date +%s%N)"
  docker run -d --name "$name" --network host --read-only \
    --user 65532:65532 --cap-drop ALL --security-opt no-new-privileges:true \
    -e XDG_DATA_HOME=/data -e XDG_CONFIG_HOME=/config \
    --tmpfs /data:uid=65532,gid=65532,mode=0700 \
    --tmpfs /config:uid=65532,gid=65532,mode=0700 \
    -v "$root/config/Caddyfile:/etc/caddy/Caddyfile:ro" \
    "$image" >/dev/null
  for attempt in $(seq 1 60); do
    if curl --fail --silent --show-error --max-time 2 \
      "http://127.0.0.1:${port}/healthz" >/dev/null; then
      ready_ns="$(date +%s%N)"
      python3 - "$started_ns" "$ready_ns" <<'PY'
import sys
print((int(sys.argv[2]) - int(sys.argv[1])) // 1_000_000)
PY
      return 0
    fi
    [[ "$attempt" -lt 60 ]] || { docker logs "$name" >&2 || true; return 1; }
    sleep 1
  done
}

# Pull by digest so rollback cannot resolve through a mutable tag.
docker pull "$CADDY_PREVIOUS_IMAGE" >/dev/null
previous_repo_digests="$(docker image inspect "$CADDY_PREVIOUS_IMAGE" --format '{{json .RepoDigests}}')"
python3 - "$CADDY_PREVIOUS_IMAGE" "$previous_repo_digests" <<'PY'
import json, sys
expected=sys.argv[1]
values=json.loads(sys.argv[2])
raise SystemExit(0 if expected in values else 1)
PY
previous_revision="$(docker image inspect "$CADDY_PREVIOUS_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
test "$previous_revision" = "$CADDY_PREVIOUS_SOURCE_SHA"

# Record the previous embedded configuration checksum without relying on a
# checksum label that did not exist before the reconciliation release.
extract_id="$(docker create "$CADDY_PREVIOUS_IMAGE")"
docker cp "$extract_id:/etc/caddy/." "$root/old-config"
docker rm "$extract_id" >/dev/null
previous_config_sha256="$(python3 - "$root/old-config" <<'PY'
import hashlib, pathlib, sys
root=pathlib.Path(sys.argv[1])
digest=hashlib.sha256()
files=sorted(path for path in root.rglob('*') if path.is_file())
if not files: raise SystemExit(1)
for path in files:
    relative=path.relative_to(root).as_posix().encode()
    payload=path.read_bytes()
    digest.update(len(relative).to_bytes(8,'big')); digest.update(relative)
    digest.update(len(payload).to_bytes(8,'big')); digest.update(payload)
print(digest.hexdigest())
PY
)"
[[ "$previous_config_sha256" =~ ^[0-9a-f]{64}$ ]]

candidate_rto_ms="$(start_and_probe "$current" "$candidate_image")"
docker rm -f "$current" >/dev/null
rollback_rto_ms="$(start_and_probe "$previous" "$CADDY_PREVIOUS_IMAGE")"
previous_health="$(curl --fail --silent --show-error --max-time 2 "http://127.0.0.1:${port}/healthz")"
test "$previous_health" = healthy
docker rm -f "$previous" >/dev/null
recovery_rto_ms="$(start_and_probe "$current" "$candidate_image")"
candidate_health="$(curl --fail --silent --show-error --max-time 2 "http://127.0.0.1:${port}/healthz")"
test "$candidate_health" = healthy

cat > rollback-rehearsal.json <<EOF
{
  "schema": "codestra.caddy.rollback-rehearsal.v1",
  "candidate_image": "${candidate_image}",
  "previous_source_sha": "${CADDY_PREVIOUS_SOURCE_SHA}",
  "previous_image": "${CADDY_PREVIOUS_IMAGE}",
  "previous_image_digest": "${CADDY_PREVIOUS_IMAGE_DIGEST}",
  "previous_config_sha256": "${previous_config_sha256}",
  "candidate_start_rto_ms": ${candidate_rto_ms},
  "rollback_rto_ms": ${rollback_rto_ms},
  "candidate_recovery_rto_ms": ${recovery_rto_ms},
  "rpo": "0",
  "data_integrity": "PASS_STATELESS_EDGE_NO_DATA_MUTATION",
  "previous_health": "PASS",
  "candidate_health_after_recovery": "PASS",
  "ssh_changed": false,
  "firewall_changed": false,
  "dns_changed": false,
  "unrelated_workloads_changed": false,
  "result": "PASS"
}
EOF
printf 'CADDY_ROLLBACK_REHEARSAL=PASS\n'
cat rollback-rehearsal.json
