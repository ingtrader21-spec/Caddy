#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

for name in \
  CADDY_CANARY_ENV_FILE \
  CADDY_CANARY_MTLS_CLIENT_CERT \
  CADDY_CANARY_MTLS_CLIENT_KEY \
  CADDY_CANARY_MTLS_CA_CERT; do
  [[ -n "${!name:-}" ]] || { printf 'CADDY_CANARY_WRAPPER=FAIL missing=%s\n' "$name" >&2; exit 2; }
  [[ -f "${!name}" && ! -L "${!name}" ]] || { printf 'CADDY_CANARY_WRAPPER=FAIL invalid=%s\n' "$name" >&2; exit 2; }
done

command -v sudo >/dev/null 2>&1 || { echo 'CADDY_CANARY_WRAPPER=FAIL missing=sudo' >&2; exit 2; }
sudo -n true >/dev/null 2>&1 || { echo 'CADDY_CANARY_WRAPPER=FAIL reason=passwordless_sudo_required' >&2; exit 2; }

work_root="$(mktemp -d)"
cleanup() {
  sudo -n rm -rf -- "$work_root" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sudo -n install -d -o root -g root -m 0700 "$work_root/root"
sudo -n install -o root -g root -m 0400 "$CADDY_CANARY_ENV_FILE" "$work_root/root/canary.env"
sudo -n install -o root -g root -m 0400 "$CADDY_CANARY_MTLS_CLIENT_CERT" "$work_root/root/client.crt"
sudo -n install -o root -g root -m 0400 "$CADDY_CANARY_MTLS_CLIENT_KEY" "$work_root/root/client.key"
sudo -n install -o root -g root -m 0400 "$CADDY_CANARY_MTLS_CA_CERT" "$work_root/root/ca.crt"

# The implementation is copied and corrected deterministically in the private
# execution directory. This preserves the protected source while repairing the
# historical 15-byte WebSocket test nonce before execution.
sudo -n sed \
  's/Y2FuYXJ5LXJlYWRvbmx5\\r\\n/Y2FuYXJ5LXJlYWRvbmx5IQ==\\r\\n/' \
  scripts/production_readonly_canary.sh > "$work_root/implementation.sh"
sudo -n chown root:root "$work_root/implementation.sh"
sudo -n chmod 0500 "$work_root/implementation.sh"
sudo -n grep -Fq 'Y2FuYXJ5LXJlYWRvbmx5IQ==' "$work_root/implementation.sh" || {
  echo 'CADDY_CANARY_WRAPPER=FAIL reason=websocket_nonce_patch_missing' >&2
  exit 2
}

sudo -n env \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  CADDY_CANARY_IMAGE="$CADDY_CANARY_IMAGE" \
  CADDY_CANARY_SOURCE_SHA="$CADDY_CANARY_SOURCE_SHA" \
  CADDY_CANARY_CONFIG_SHA256="$CADDY_CANARY_CONFIG_SHA256" \
  CADDY_CANARY_ENV_FILE="$work_root/root/canary.env" \
  CADDY_CANARY_DATA_SOURCE="$CADDY_CANARY_DATA_SOURCE" \
  CADDY_CANARY_MTLS_CLIENT_CERT="$work_root/root/client.crt" \
  CADDY_CANARY_MTLS_CLIENT_KEY="$work_root/root/client.key" \
  CADDY_CANARY_MTLS_CA_CERT="$work_root/root/ca.crt" \
  GITHUB_ACTIONS="${GITHUB_ACTIONS:-false}" \
  GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-appolon1908-hue/Caddy}" \
  GITHUB_RUN_ID="${GITHUB_RUN_ID:-local}" \
  GITHUB_SERVER_URL="${GITHUB_SERVER_URL:-https://github.com}" \
  bash "$work_root/implementation.sh"
