#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/deploy/compose.runtime.yaml"
BASELINE="$ROOT/config/release-baseline.v1.json"
DOCKER_BIN='/usr/bin/docker'
COSIGN_BIN='/usr/local/bin/cosign'
PYTHON_BIN='/usr/bin/python3'
CERTIFICATE_IDENTITY='https://github.com/appolon1908-hue/Caddy/.github/workflows/immutable-release.yml@refs/heads/production'
CERTIFICATE_ISSUER='https://token.actions.githubusercontent.com'

fail() {
  printf 'CADDY_ROLLBACK=FAIL:%s\n' "$1" >&2
  exit 2
}

trusted_executable() {
  local requested="$1" resolved
  resolved="$(readlink -f -- "$requested")"
  [[ -x "$requested" && -n "$resolved" && -x "$resolved" && ! -L "$resolved" ]] || \
    fail "trusted_binary:$requested"
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
for binary in "$DOCKER_BIN" "$COSIGN_BIN" "$PYTHON_BIN"; do
  trusted_executable "$binary"
done

readarray -t baseline < <("$PYTHON_BIN" - "$BASELINE" <<'PY'
import json,re,sys
item=json.load(open(sys.argv[1],encoding='utf-8'))
assert item['schema']=='codestra.caddy-release-baseline.v1'
assert re.fullmatch(r'[0-9a-f]{40}',item['source_sha'])
assert re.fullmatch(r'ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}',item['image'])
assert item['mutable'] is False
print(item['source_sha'])
print(item['image'])
PY
)
[[ ${#baseline[@]} -eq 2 ]] || fail baseline_contract
baseline_source="${baseline[0]}"
baseline_image="${baseline[1]}"
baseline_digest="${baseline_image##*@sha256:}"

"$COSIGN_BIN" verify \
  --certificate-identity "$CERTIFICATE_IDENTITY" \
  --certificate-oidc-issuer "$CERTIFICATE_ISSUER" \
  "$baseline_image" >/dev/null
"$DOCKER_BIN" pull "$baseline_image" >/dev/null
image_source="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$baseline_image")"
image_revision="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$baseline_image")"
[[ "$image_source" == 'https://github.com/appolon1908-hue/Caddy' ]] || fail image_source
[[ "$image_revision" == "$baseline_source" ]] || fail image_revision

work="$(mktemp -d)"
probe="codestra-caddy-rollback-probe-$$"
cleanup() {
  "$DOCKER_BIN" rm -f "$probe" >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT
mkdir -p "$work/config"
"$DOCKER_BIN" create --name "$probe" "$baseline_image" >/dev/null
"$DOCKER_BIN" cp "$probe:/etc/caddy/." "$work/config"
computed_config_sha="$($PYTHON_BIN "$ROOT/scripts/hash_config_tree.py" "$work/config")"
image_config_sha="$("$DOCKER_BIN" image inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' "$baseline_image")"
if [[ -n "$image_config_sha" && "$image_config_sha" != "$computed_config_sha" ]]; then
  fail image_config_identity
fi

export CADDY_IMAGE_SHA256="$baseline_digest"
export CADDY_REVIEWED_SHA="$baseline_source"
export CADDY_CONFIG_SHA256="$computed_config_sha"
export CADDY_RELEASE_ID="rollback-$baseline_source"
"$DOCKER_BIN" compose -f "$COMPOSE" config --quiet
"$DOCKER_BIN" compose -f "$COMPOSE" up -d --pull never --no-build caddy

for _ in $(seq 1 60); do
  state="$("$DOCKER_BIN" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' codestra-caddy 2>/dev/null || true)"
  [[ "$state" == healthy ]] && break
  sleep 2
done
[[ "$("$DOCKER_BIN" inspect --format '{{.State.Health.Status}}' codestra-caddy 2>/dev/null || true)" == healthy ]] || fail unhealthy

final_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
final_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
[[ "$final_image" == "$baseline_image" ]] || fail image_readback
[[ "$final_config" == "$computed_config_sha" ]] || fail config_readback

printf 'CADDY_ROLLBACK=PASS\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\n' \
  "$baseline_source" "$baseline_image" "$computed_config_sha"
