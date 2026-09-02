#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT/config"
SOURCE="$SOURCE_DIR/Caddyfile"
TARGET_DIR="${CADDY_TARGET_DIR:-/etc/caddy}"
BACKUP_DIR="${CADDY_BACKUP_DIR:-/var/backups/caddy-git-controller}"
CADDY_BIN="${CADDY_BIN:-caddy}"
REVIEWED_SHA="${CADDY_REVIEWED_SHA:-}"

if [[ ! -f "$SOURCE" ]]; then
  echo "BLOCKED: $SOURCE does not exist. Import and review the live configuration first." >&2
  exit 1
fi

if [[ -e "$SOURCE_DIR/private" || -L "$SOURCE_DIR/private" ]]; then
  echo "BLOCKED: host-managed private material must not exist in the repository tree." >&2
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

if [[ ! "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "BLOCKED: CADDY_REVIEWED_SHA must be the approved 40-character production commit." >&2
  exit 1
fi

head_sha="$(git -C "$ROOT" rev-parse HEAD)"
git -C "$ROOT" fetch --quiet origin production
remote_sha="$(git -C "$ROOT" rev-parse refs/remotes/origin/production)"
if [[ "$head_sha" != "$REVIEWED_SHA" || "$remote_sha" != "$REVIEWED_SHA" ]]; then
  echo "BLOCKED: reviewed, checked-out, and remote production SHAs must match." >&2
  echo "REVIEWED_SHA=$REVIEWED_SHA" >&2
  echo "HEAD_SHA=$head_sha" >&2
  echo "REMOTE_PRODUCTION_SHA=$remote_sha" >&2
  exit 1
fi

"$CADDY_BIN" validate --config "$SOURCE" --adapter caddyfile

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -p "$BACKUP_DIR"
backup="$BACKUP_DIR/config.$stamp"
if sudo test -d "$TARGET_DIR"; then
  sudo cp -a "$TARGET_DIR" "$backup"
fi

target_parent="$(dirname "$TARGET_DIR")"
target_name="$(basename "$TARGET_DIR")"
staged="$(sudo mktemp -d "$target_parent/.${target_name}.staged.XXXXXX")"
previous="$target_parent/.${target_name}.previous.$stamp"
failed="$target_parent/.${target_name}.failed.$stamp"
cleanup() {
  if [[ -n "${staged:-}" ]] && sudo test -d "$staged"; then
    sudo rm -rf -- "$staged"
  fi
  if [[ -n "${failed:-}" ]] && sudo test -d "$failed"; then
    sudo rm -rf -- "$failed"
  fi
}
trap cleanup EXIT
if ! git -C "$ROOT" archive --format=tar "$REVIEWED_SHA" -- config \
  | sudo tar --extract --file=- --directory="$staged" --strip-components=1; then
  echo "BLOCKED: failed to stage the Git-tracked configuration from the reviewed commit." >&2
  exit 1
fi
sudo chown -R root:root "$staged"
sudo find "$staged" -type d -exec chmod 0755 {} +
sudo find "$staged" -type f -exec chmod 0644 {} +
if sudo test -L "$TARGET_DIR/private"; then
  echo "BLOCKED: host-managed private material must not be a symbolic link." >&2
  exit 1
fi
if sudo test -e "$TARGET_DIR/private"; then
  if ! sudo test -d "$TARGET_DIR/private"; then
    echo "BLOCKED: host-managed private material is not a directory." >&2
    exit 1
  fi
  sudo cp -a -- "$TARGET_DIR/private" "$staged/private"
fi

sudo "$CADDY_BIN" validate --config "$staged/Caddyfile" --adapter caddyfile
if sudo test -e "$TARGET_DIR"; then
  sudo mv "$TARGET_DIR" "$previous"
fi
sudo mv "$staged" "$TARGET_DIR"
staged=""

if ! sudo "$CADDY_BIN" validate --config "$TARGET_DIR/Caddyfile" --adapter caddyfile; then
  echo "Installed configuration failed validation; restoring backup." >&2
  if sudo test -d "$previous"; then
    sudo mv "$TARGET_DIR" "$failed"
    sudo mv "$previous" "$TARGET_DIR"
  fi
  exit 1
fi

if ! sudo systemctl reload caddy; then
  echo "Reload failed; restoring previous configuration." >&2
  if sudo test -d "$previous"; then
    sudo mv "$TARGET_DIR" "$failed"
    sudo mv "$previous" "$TARGET_DIR"
    sudo systemctl reload caddy || true
  fi
  exit 1
fi

sudo systemctl is-active --quiet caddy
if sudo test -d "$previous"; then
  sudo rm -rf -- "$previous"
fi

echo "DEPLOYED_COMMIT=$head_sha"
echo "BACKUP=$backup"
