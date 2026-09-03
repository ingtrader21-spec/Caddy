#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE="$ROOT/config/release-baseline.v1.json"
DOCKER_BIN="${DOCKER_BIN:-docker}"
COSIGN_BIN="${COSIGN_BIN:-cosign}"
CERTIFICATE_IDENTITY='https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release.yml@refs/heads/production'
CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'

baseline_source="$(python3 - "$BASELINE" <<'PY'
import json, re, sys
item=json.load(open(sys.argv[1],encoding='utf-8'))
assert item.get('schema')=='codestra.caddy-release-baseline.v1'
assert item.get('mutable') is False
assert re.fullmatch(r'[0-9a-f]{40}',item.get('source_sha',''))
assert re.fullmatch(r'ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}',item.get('image',''))
print(item['source_sha'])
PY
)"
baseline_image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image"])' "$BASELINE")"
baseline_digest="${baseline_image##*@sha256:}"

"$COSIGN_BIN" verify \
  --certificate-identity "$CERTIFICATE_IDENTITY" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$baseline_image" >/dev/null
"$DOCKER_BIN" pull "$baseline_image" >/dev/null

image_source="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$baseline_image")"
image_revision="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$baseline_image")"
image_user="$("$DOCKER_BIN" image inspect --format '{{.Config.User}}' "$baseline_image")"
[[ "$image_source" == 'https://github.com/appolon1908-hue/Caddy' ]] || { echo CADDY_ROLLBACK_BASELINE=FAIL:image_source >&2; exit 2; }
[[ "$image_revision" == "$baseline_source" ]] || { echo CADDY_ROLLBACK_BASELINE=FAIL:image_revision >&2; exit 2; }
[[ "$image_user" == '65532:65532' ]] || { echo CADDY_ROLLBACK_BASELINE=FAIL:image_user >&2; exit 2; }

work="$(mktemp -d)"
container="caddy-rollback-evidence-${GITHUB_RUN_ID:-local}-$$"
cleanup(){ "$DOCKER_BIN" rm -f "$container" >/dev/null 2>&1 || true; rm -rf -- "$work"; }
trap cleanup EXIT
mkdir -p "$work/config"
"$DOCKER_BIN" create --name "$container" "$baseline_image" >/dev/null
"$DOCKER_BIN" cp "$container:/etc/caddy/." "$work/config"
config_sha256="$(python3 "$ROOT/scripts/hash_config_tree.py" "$work/config")"
[[ "$config_sha256" =~ ^[0-9a-f]{64}$ ]] || { echo CADDY_ROLLBACK_BASELINE=FAIL:config_hash >&2; exit 2; }

mkdir -p "$work/pki/middleware" "$work/pki/klyrow"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=rollback-validation.invalid' \
  -keyout "$work/pki/validation.key" -out "$work/pki/validation.crt" >/dev/null 2>&1
install -m 0600 "$work/pki/validation.key" "$work/pki/middleware/server.key"
install -m 0600 "$work/pki/validation.key" "$work/pki/middleware/staging-server.key"
install -m 0644 "$work/pki/validation.crt" "$work/pki/middleware/server.crt"
install -m 0644 "$work/pki/validation.crt" "$work/pki/middleware/staging-server.crt"
install -m 0644 "$work/pki/validation.crt" "$work/pki/middleware/client-ca.crt"
install -m 0600 "$work/pki/validation.key" "$work/pki/klyrow/tls.key"
install -m 0644 "$work/pki/validation.crt" "$work/pki/klyrow/tls-fullchain.crt"
install -m 0644 "$work/pki/validation.crt" "$work/pki/klyrow/klyrow-client.crt"

"$DOCKER_BIN" run --rm --network none \
  --mount "type=bind,src=$work/pki/middleware,dst=/etc/codestra/pki/middleware-private-ingress,readonly" \
  --mount "type=bind,src=$work/pki/klyrow,dst=/etc/caddy/private/klyrow-events,readonly" \
  "$baseline_image" validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

export CADDY_IMAGE_SHA256="$baseline_digest"
export CADDY_REVIEWED_SHA="$baseline_source"
export CADDY_CONFIG_SHA256="$config_sha256"
export CADDY_RELEASE_ID="rollback-evidence-$baseline_source"
# Non-secret placeholders are supplied only so Compose renders the same immutable
# runtime selection that the fixed rollback command will use.
while IFS='=' read -r name value; do
  [[ "$name" =~ ^CADDY_[A-Z0-9_]+$ ]] || continue
  [[ "$name" == CADDY_IMAGE_SHA256 || "$name" == CADDY_REVIEWED_SHA || "$name" == CADDY_CONFIG_SHA256 || "$name" == CADDY_RELEASE_ID ]] && continue
  export "$name=$value"
done < "$ROOT/config/runtime-values.example"
"$DOCKER_BIN" compose -f "$ROOT/deploy/compose.runtime.yaml" config --quiet
"$ROOT/tests/runtime-bind-test.sh" "$baseline_image" >/dev/null

printf '%s\n' \
  'CADDY_ROLLBACK_BASELINE=PASS' \
  "ROLLBACK_SOURCE_SHA=$baseline_source" \
  "ROLLBACK_IMAGE=$baseline_image" \
  "ROLLBACK_CONFIG_SHA256=$config_sha256" \
  'ROLLBACK_SIGNATURE=PASS' \
  'ROLLBACK_CONFIG_VALIDATION=PASS' \
  'ROLLBACK_NONROOT_BIND=PASS'
