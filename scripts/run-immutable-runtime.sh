#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"; COMPOSE="$ROOT/deploy/compose.runtime.yaml"; REVIEWED_SHA="${CADDY_REVIEWED_SHA:-}"; IMAGE_SHA256="${CADDY_IMAGE_SHA256:-}"; IMAGE_REPOSITORY=ghcr.io/appolon1908-hue/codestra-caddy; COSIGN_BIN=/usr/local/bin/cosign; DOCKER_BIN=/usr/bin/docker; PYTHON_BIN=/usr/bin/python3; ATTESTATION_VERIFIER="$ROOT/scripts/verify-image-attestation.py"; CERTIFICATE_IDENTITY='https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release.yml@refs/heads/production'; CERTIFICATE_ISSUER=https://token.actions.githubusercontent.com; CADDY_DATA_DIR="${CADDY_DATA_DIR:-/var/lib/codestra/caddy/data}"; CADDY_CONFIG_DIR="${CADDY_CONFIG_DIR:-/var/lib/codestra/caddy/runtime-config}"
[[ "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ && "$IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo BLOCKED:invalid_release_identity >&2; exit 1; }; IMAGE_REF="${IMAGE_REPOSITORY}@sha256:${IMAGE_SHA256}"
for binary in "$COSIGN_BIN" "$DOCKER_BIN" "$PYTHON_BIN"; do [[ -x "$binary" && ! -L "$binary" ]] || { echo "BLOCKED:trusted_executable:$binary" >&2; exit 1; }; owner="$(stat -c '%u:%g' -- "$binary")"; mode="$(stat -c '%a' -- "$binary")"; mode_value=$((8#$mode)); [[ "$owner" == 0:0 ]] && (( (mode_value & 0022)==0 )) || { echo "BLOCKED:executable_ownership:$binary" >&2; exit 1; }; done
[[ -z "$(git -C "$ROOT" status --porcelain)" && "$(git -C "$ROOT" branch --show-current)" == production ]] || { echo BLOCKED:worktree_or_branch >&2; exit 1; }
head_sha="$(git -C "$ROOT" rev-parse HEAD)"; git -C "$ROOT" fetch --quiet origin production; remote_sha="$(git -C "$ROOT" rev-parse refs/remotes/origin/production)"; [[ "$head_sha" == "$REVIEWED_SHA" && "$remote_sha" == "$REVIEWED_SHA" ]] || { echo BLOCKED:source_identity >&2; exit 1; }
for state_dir in "$CADDY_DATA_DIR" "$CADDY_CONFIG_DIR"; do [[ -d "$state_dir" && ! -L "$state_dir" && "$(stat -c '%u:%g' -- "$state_dir")" == 65532:65532 ]] || { echo "BLOCKED:state_path:$state_dir" >&2; exit 1; }; mode="$(stat -c '%a' -- "$state_dir")"; mode_value=$((8#$mode)); (( (mode_value&0200)!=0 && (mode_value&0022)==0 )) || { echo "BLOCKED:state_mode:$state_dir" >&2; exit 1; }; done
for trust_dir in /etc/caddy/private/klyrow-events /etc/codestra/pki/middleware-private-ingress; do [[ -d "$trust_dir" && ! -L "$trust_dir" ]] || { echo "BLOCKED:trust_path:$trust_dir" >&2; exit 1; }; done
export CADDY_CONFIG_SHA256="$("$PYTHON_BIN" "$ROOT/scripts/hash_config_tree.py" "$ROOT/config")" CADDY_RELEASE_ID="production-$REVIEWED_SHA" CADDY_DATA_DIR CADDY_CONFIG_DIR CADDY_IMAGE_SHA256 CADDY_REVIEWED_SHA
"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet
"$COSIGN_BIN" verify --certificate-identity "$CERTIFICATE_IDENTITY" --certificate-oidc-issuer "$CERTIFICATE_ISSUER" "$IMAGE_REF" >/dev/null
attestation_output="$(mktemp)"; trap 'rm -f -- "$attestation_output"' EXIT
"$COSIGN_BIN" verify-attestation --type https://codestra.co/attestations/caddy-source/v2 --certificate-identity "$CERTIFICATE_IDENTITY" --certificate-oidc-issuer "$CERTIFICATE_ISSUER" --output json "$IMAGE_REF" >"$attestation_output"
"$PYTHON_BIN" "$ATTESTATION_VERIFIER" "$attestation_output" "$IMAGE_SHA256" https://github.com/appolon1908-hue/Caddy "$REVIEWED_SHA" "$CADDY_CONFIG_SHA256"
"$DOCKER_BIN" pull "$IMAGE_REF" >/dev/null
image_revision="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE_REF")"; image_source="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$IMAGE_REF")"; image_config="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$IMAGE_REF")"
[[ "$image_revision" == "$REVIEWED_SHA" && "$image_source" == https://github.com/appolon1908-hue/Caddy && "$image_config" == "$CADDY_CONFIG_SHA256" ]] || { echo BLOCKED:image_labels >&2; exit 1; }
"$DOCKER_BIN" compose -f "$COMPOSE" run --rm --no-deps caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
"$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy
for _ in $(seq 1 60); do state="$("$DOCKER_BIN" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"; [[ "$state" == healthy ]] && break; sleep 2; done
[[ "$("$DOCKER_BIN" inspect --format '{{.State.Health.Status}}' codestra-caddy)" == healthy ]] || { echo CADDY_ACTIVATION=FAIL:automatic_rollback >&2; "$ROOT/scripts/rollback-runtime.sh" || true; exit 1; }
canary_output="$("$ROOT/scripts/production-canary.sh")" || { echo CADDY_ACTIVATION=FAIL:runtime_readback >&2; "$ROOT/scripts/rollback-runtime.sh" || true; exit 1; }
printf '%s\n' "$canary_output"
printf 'CADDY_ACTIVATION=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\n' "$REVIEWED_SHA" "$IMAGE_REF" "$CADDY_CONFIG_SHA256"
