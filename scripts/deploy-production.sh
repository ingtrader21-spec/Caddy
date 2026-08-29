#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/config/Caddyfile"
TARGET="${CADDY_TARGET:-/etc/caddy/Caddyfile}"
BACKUP_DIR="${CADDY_BACKUP_DIR:-/var/backups/caddy-git-controller}"
CADDY_BIN="${CADDY_BIN:-caddy}"

if [[ ! -f "$SOURCE" ]]; then
  echo "BLOCKED: $SOURCE does not exist. Import and review the live configuration first." >&2
  exit 1
fi

if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "BLOCKED: repository worktree is dirty." >&2
  exit 1
fi

branch="$(git -C "$ROOT" branch --show-current)"
if [[ "$branch" != "production" ]]; then
  echo "BLOCKED: deployment is allowed only from the production branch; current=$branch" >&2
  exit 1
fi

"$CADDY_BIN" validate --config "$SOURCE" --adapter caddyfile

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$BACKUP_DIR"
if sudo test -f "$TARGET"; then
  sudo cp -a "$TARGET" "$BACKUP_DIR/Caddyfile.$stamp"
fi

sudo install -o root -g root -m 0644 "$SOURCE" "$TARGET"

if ! sudo "$CADDY_BIN" validate --config "$TARGET" --adapter caddyfile; then
  echo "Installed configuration failed validation; restoring backup." >&2
  if sudo test -f "$BACKUP_DIR/Caddyfile.$stamp"; then
    sudo cp -a "$BACKUP_DIR/Caddyfile.$stamp" "$TARGET"
  fi
  exit 1
fi

if ! sudo systemctl reload caddy; then
  echo "Reload failed; restoring previous configuration." >&2
  if sudo test -f "$BACKUP_DIR/Caddyfile.$stamp"; then
    sudo cp -a "$BACKUP_DIR/Caddyfile.$stamp" "$TARGET"
    sudo systemctl reload caddy || true
  fi
  exit 1
fi

sudo systemctl is-active --quiet caddy

echo "DEPLOYED_COMMIT=$(git -C "$ROOT" rev-parse HEAD)"
echo "BACKUP=$BACKUP_DIR/Caddyfile.$stamp"
