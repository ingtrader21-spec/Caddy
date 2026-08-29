#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE="${CADDY_LIVE_CONFIG:-/etc/caddy/Caddyfile}"
DEST="$ROOT/config/production/Caddyfile"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if [[ -e "$DEST" ]]; then
  echo "BLOCKED: $DEST already exists. Refusing to overwrite tracked configuration." >&2
  exit 1
fi

if [[ ! -r "$LIVE" ]]; then
  sudo cat "$LIVE" > "$TMP"
else
  cat "$LIVE" > "$TMP"
fi

if grep -InE '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|api[_-]?token[[:space:]]*[:=]|password[[:space:]]*[:=]|bearer[[:space:]]+[A-Za-z0-9._-]+)' "$TMP"; then
  echo "BLOCKED: possible inline secret detected. Move secrets to server environment/secret storage before committing." >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
cp "$TMP" "$DEST"
caddy fmt --overwrite "$DEST"
caddy validate --config "$DEST" --adapter caddyfile

cat <<EOF
Imported and validated: $DEST

NEXT STEPS:
1. Manually review the file for credentials, private IP exposure, stale routes, and unintended public admin/metrics endpoints.
2. Run: git diff --check
3. Run: scripts/validate.sh
4. Commit on a feature/fix branch based on development.
5. Promote only by PR: development -> test -> staging -> production -> main.
EOF
