#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
REVIEWED_SHA="${CADDY_REVIEWED_SHA:-}"
IMAGE_SHA256="${CADDY_IMAGE_SHA256:-}"
IMAGE_REPOSITORY="ghcr.io/appolon1908-hue/codestra-caddy"
COSIGN_BIN="/usr/local/bin/cosign"
DOCKER_BIN="/usr/bin/docker"
PYTHON_BIN="/usr/bin/python3"
ATTESTATION_VERIFIER="$ROOT/scripts/verify-image-attestation.py"
CERTIFICATE_IDENTITY="https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release.yml@refs/heads/production"
CERTIFICATE_ISSUER="https://token.actions.githubusercontent.com"
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
IMAGE_REF="${IMAGE_REPOSITORY}@sha256:${IMAGE_SHA256}"
for trusted_binary in "$COSIGN_BIN" "$DOCKER_BIN" "$PYTHON_BIN"; do
  if [[ -L "$trusted_binary" || ! -x "$trusted_binary" ]]; then
    echo "BLOCKED: required trusted executable is unavailable: $trusted_binary" >&2
    exit 1
  fi
  binary_owner="$(stat -c '%u:%g' -- "$trusted_binary")"
  binary_mode="$(stat -c '%a' -- "$trusted_binary")"
  binary_mode_value=$((8#$binary_mode))
  if [[ "$binary_owner" != "0:0" ]] || (( (binary_mode_value & 0022) != 0 )); then
    echo "BLOCKED: trusted executable must be root-owned and not group/world-writable: $trusted_binary" >&2
    exit 1
  fi
done
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
"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet

# Verify the immutable remote digest against the protected GitHub Actions
# identity before pulling it. The pulled config (and therefore its revision
# label) is transitively covered by this digest signature.
"$COSIGN_BIN" verify \
  --certificate-identity "$CERTIFICATE_IDENTITY" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$IMAGE_REF" >/dev/null
attestation_output="$(mktemp)"
trap 'rm -f -- "$attestation_output"' EXIT
"$COSIGN_BIN" verify-attestation \
  --type https://codestra.co/attestations/caddy-source/v1 \
  --certificate-identity "$CERTIFICATE_IDENTITY" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  --output json \
  "$IMAGE_REF" >"$attestation_output"
"$PYTHON_BIN" "$ATTESTATION_VERIFIER" \
  "$attestation_output" "$IMAGE_SHA256" \
  "https://github.com/appolon1908-hue/Caddy" "$REVIEWED_SHA"
"$DOCKER_BIN" pull "$IMAGE_REF" >/dev/null

image_revision="$("$DOCKER_BIN" image inspect \
  --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
  "$IMAGE_REF")"
image_source="$("$DOCKER_BIN" image inspect \
  --format '{{ index .Config.Labels "org.opencontainers.image.source" }}' \
  "$IMAGE_REF")"
if [[ "$image_revision" != "$REVIEWED_SHA" ]]; then
  echo "BLOCKED: signed image revision does not match the reviewed production SHA." >&2
  exit 1
fi
if [[ "$image_source" != "https://github.com/appolon1908-hue/Caddy" ]]; then
  echo "BLOCKED: signed image source label is not the canonical Caddy repository." >&2
  exit 1
fi

"$DOCKER_BIN" compose -f "$COMPOSE" run --rm --no-deps caddy \
  validate --config /etc/caddy/Caddyfile --adapter caddyfile
exec "$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build
