#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CADDY_BIN="${CADDY_BIN:-caddy}"

if ! command -v "$CADDY_BIN" >/dev/null 2>&1; then
  echo "ERROR: caddy binary not found. Set CADDY_BIN or install Caddy." >&2
  exit 1
fi

mapfile -d '' files < <(find config -type f -name Caddyfile -print0 2>/dev/null || true)

if (( ${#files[@]} == 0 )); then
  echo "BOOTSTRAP: no environment Caddyfile has been imported yet."
  echo "Validation infrastructure and the mandatory observability patch are ready; production deployment remains blocked."
  python3 -m py_compile scripts/ensure-observability-metrics.py
  exit 0
fi

failed=0
for file in "${files[@]}"; do
  echo "==> Observability contract: $file"
  if ! python3 scripts/ensure-observability-metrics.py --check "$file"; then
    failed=1
  fi

  echo "==> Formatting check: $file"
  formatted="$($CADDY_BIN fmt "$file")"
  current="$(cat "$file")"
  if [[ "$formatted" != "$current" ]]; then
    echo "ERROR: $file is not formatted. Run: caddy fmt --overwrite $file" >&2
    failed=1
  fi

  echo "==> Caddy validation: $file"
  if ! "$CADDY_BIN" validate --config "$file" --adapter caddyfile; then
    failed=1
  fi
done

if grep -RInE --exclude='*.md' --exclude='*.example' \
  '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|api[_-]?token[[:space:]]*[:=][[:space:]]*[^{$]|password[[:space:]]*[:=][[:space:]]*[^{$]|bearer[[:space:]]+[A-Za-z0-9._-]+)' \
  config 2>/dev/null; then
  echo "ERROR: possible committed secret detected under config/." >&2
  failed=1
fi

if (( failed != 0 )); then
  echo "Caddy validation failed." >&2
  exit 1
fi

echo "Caddy validation passed."
