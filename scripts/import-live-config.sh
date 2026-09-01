#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE="${CADDY_LIVE_CONFIG:-/etc/caddy/Caddyfile}"
LIVE_ROOT="$(dirname "$LIVE")"
DEST="$ROOT/config/Caddyfile"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

files=("$LIVE")
for directory in snippets sites conf.d; do
  if [[ -d "$LIVE_ROOT/$directory" ]]; then
    while IFS= read -r -d '' file; do
      files+=("$file")
    done < <(find "$LIVE_ROOT/$directory" -maxdepth 1 -type f -name '*.caddy' -print0 | sort -z)
  fi
done

for source in "${files[@]}"; do
  relative="${source#"$LIVE_ROOT"/}"
  [[ "$source" == "$LIVE" ]] && relative="Caddyfile"
  staged="$TMP_DIR/$relative"
  mkdir -p "$(dirname "$staged")"
  if [[ ! -r "$source" ]]; then
    sudo cp -- "$source" "$staged"
  else
    cp -- "$source" "$staged"
  fi
  if grep -InE '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|api[_-]?token[[:space:]]*[:=]|password[[:space:]]*[:=]|bearer[[:space:]]+[A-Za-z0-9._-]+)' "$staged"; then
    echo "BLOCKED: possible inline secret detected in $relative." >&2
    exit 1
  fi
  caddy fmt --overwrite "$staged"
  target="$ROOT/config/$relative"
  if [[ -e "$target" ]] && ! cmp -s "$staged" "$target"; then
    echo "BLOCKED: tracked $relative differs from the formatted live file." >&2
    exit 1
  fi
done

for source in "${files[@]}"; do
  relative="${source#"$LIVE_ROOT"/}"
  [[ "$source" == "$LIVE" ]] && relative="Caddyfile"
  install -D -m 0644 "$TMP_DIR/$relative" "$ROOT/config/$relative"
done
caddy validate --config "$DEST" --adapter caddyfile

cat <<EOF
Imported and validated: ${#files[@]} Caddy configuration files under $ROOT/config

NEXT STEPS:
1. Manually review the file for credentials, private IP exposure, stale routes, and unintended public admin/metrics endpoints.
2. Run: git diff --check
3. Run: scripts/validate.sh
4. Commit on a feature/fix branch based on development.
5. Promote only by PR: development -> test -> staging -> production -> main.
EOF
