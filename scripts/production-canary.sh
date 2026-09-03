#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly VALIDATOR="$ROOT/scripts/caddy_readonly_validator.py"
readonly EVIDENCE_DIR=/var/lib/codestra/caddy/evidence
readonly DOCKER_BIN=/usr/bin/docker
[[ $# -eq 0 ]] || { echo CADDY_PRODUCTION_CANARY=FAIL:arguments_not_allowed >&2; exit 2; }
[[ -x "$VALIDATOR" && ! -L "$VALIDATOR" ]] || { echo CADDY_PRODUCTION_CANARY=FAIL:validator_unavailable >&2; exit 2; }
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || { echo CADDY_PRODUCTION_CANARY=FAIL:dirty_worktree >&2; exit 2; }
[[ "$(git -C "$ROOT" branch --show-current)" == production ]] || { echo CADDY_PRODUCTION_CANARY=FAIL:wrong_branch >&2; exit 2; }

root_prefix=()
if [[ "$(id -u)" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1 || { echo CADDY_PRODUCTION_CANARY=FAIL:root_evidence_access >&2; exit 2; }
  root_prefix=(sudo -n)
fi
as_root(){ "${root_prefix[@]}" "$@"; }

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
temporary="$(mktemp)"
trap 'rm -f -- "$temporary"' EXIT
python3 "$VALIDATOR" >"$temporary"
python3 - "$temporary" <<'PY'
import json
import sys

data=json.load(open(sys.argv[1],encoding='utf-8'))
assert data.get('schema')=='codestra.caddy-container-validation.v2'
assert data.get('config_validation')=='PASS'
assert data.get('config_identity')=='PASS'
assert data.get('container_running') is True
assert data.get('container_health')=='healthy'
assert data.get('caddy_process_count')==1
assert data.get('listener_ownership')=='CADDY_PROCESS_ONLY'
listeners=set(data.get('listeners') or [])
requirements=(
    ('tcp/', ':80@caddy-pid'),
    ('tcp/', ':443@caddy-pid'),
    ('udp/', ':443@caddy-pid'),
    ('tcp/', ':2020@caddy-pid'),
    ('tcp/', ':18080@caddy-pid'),
)
for prefix,suffix in requirements:
    assert any(item.startswith(prefix) and item.endswith(suffix) for item in listeners), (prefix,suffix,listeners)
PY
as_root install -d -m 0700 "$EVIDENCE_DIR"
final="$EVIDENCE_DIR/caddy-production-canary-$stamp.json"
as_root install -m 0600 "$temporary" "$final"
rm -f -- "$temporary"; trap - EXIT
# Read back the immutable tuple from the actual running container without
# exposing raw configuration or environment values.
actual_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
actual_source="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
actual_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
printf 'CADDY_PRODUCTION_CANARY=PASS\nEVIDENCE=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nLISTENER_OWNERSHIP=CADDY_PROCESS_ONLY\n' "$final" "$actual_source" "$actual_image" "$actual_config"
