#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
REVIEWED_SHA="${CADDY_REVIEWED_SHA:-}"
IMAGE_SHA256="${CADDY_IMAGE_SHA256:-}"
CADDY_DATA_DIR="${CADDY_DATA_DIR:-/var/lib/codestra/caddy/data}"
CADDY_CONFIG_DIR="${CADDY_CONFIG_DIR:-/var/lib/codestra/caddy/config}"

if [[ ! "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "BLOCKED: CADDY_REVIEWED_SHA must be the approved production commit." >&2
  exit 1
fi
if [[ ! "$IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "BLOCKED: CADDY_IMAGE_SHA256 must be an approved 64-character digest." >&2
  exit 1
fi
if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "BLOCKED: repository worktree is dirty." >&2
  exit 1
fi
if [[ "$(git -C "$ROOT" branch --show-current)" != "production" ]]; then
  echo "BLOCKED: immutable runtime is allowed only from production." >&2
  exit 1
fi

head_sha="$(git -C "$ROOT" rev-parse HEAD)"
git -C "$ROOT" fetch --quiet origin production
remote_sha="$(git -C "$ROOT" rev-parse refs/remotes/origin/production)"
if [[ "$head_sha" != "$REVIEWED_SHA" || "$remote_sha" != "$REVIEWED_SHA" ]]; then
  echo "BLOCKED: reviewed, checked-out, and remote production SHAs must match." >&2
  exit 1
fi

for state_dir in "$CADDY_DATA_DIR" "$CADDY_CONFIG_DIR"; do
  if [[ -L "$state_dir" || ! -d "$state_dir" ]]; then
    echo "BLOCKED: runtime state path must be a real directory: $state_dir" >&2
    exit 1
  fi
  owner="$(stat -c '%u:%g' -- "$state_dir")"
  if [[ "$owner" != "65532:65532" ]]; then
    echo "BLOCKED: runtime state path must be owned by 65532:65532: $state_dir" >&2
    exit 1
  fi
  mode="$(stat -c '%a' -- "$state_dir")"
  mode_value=$((8#$mode))
  if (( (mode_value & 0200) == 0 || (mode_value & 0022) != 0 )); then
    echo "BLOCKED: runtime state path must be owner-writable and not group/world-writable: $state_dir" >&2
    exit 1
  fi
done

for trust_dir in \
  /etc/caddy/private/klyrow-events \
  /etc/codestra/pki/middleware-private-ingress; do
  if [[ -L "$trust_dir" || ! -d "$trust_dir" ]]; then
    echo "BLOCKED: required host-managed trust path is unavailable: $trust_dir" >&2
    exit 1
  fi
done

export CADDY_DATA_DIR CADDY_CONFIG_DIR CADDY_IMAGE_SHA256
docker compose -f "$COMPOSE" config --quiet
docker compose -f "$COMPOSE" pull caddy
docker compose -f "$COMPOSE" run --rm --no-deps caddy \
  validate --config /etc/caddy/Caddyfile --adapter caddyfile
exec docker compose -f "$COMPOSE" up -d --pull never --no-build
