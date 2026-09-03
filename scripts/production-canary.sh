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
assert data.get('effective_access_log_redaction')=='PASS'
assert int(data.get('effective_access_log_count') or 0)>=5
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

# Read back the immutable tuple and the public bind from the actual running
# container without printing environment values.
actual_image="$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' codestra-caddy)"
actual_source="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.source.sha"}}' codestra-caddy)"
actual_config="$("$DOCKER_BIN" inspect --format '{{index .Config.Labels "io.codestra.caddy.config.sha256"}}' codestra-caddy)"
public_bind="$("$DOCKER_BIN" inspect --format '{{range .Config.Env}}{{println .}}{{end}}' codestra-caddy | sed -n 's/^CADDY_PUBLIC_BIND=//p' | head -n1)"
[[ "$public_bind" =~ ^[0-9A-Fa-f:.]+$ ]] || { echo CADDY_PRODUCTION_CANARY=FAIL:public_bind >&2; exit 2; }
http3_output="$("$DOCKER_BIN" exec codestra-caddy /usr/bin/codestra-http3-probe api.codestra.co "$public_bind" /api/v1/health)"
grep -q '^CADDY_HTTP3_CANARY=PASS ' <<<"$http3_output" || { echo CADDY_PRODUCTION_CANARY=FAIL:http3 >&2; exit 2; }

python3 - "$temporary" <<'PY'
import json
import sys
from pathlib import Path
path=Path(sys.argv[1])
data=json.loads(path.read_text(encoding='utf-8'))
data['http3_canary']='PASS'
data['http3_host']='api.codestra.co'
path.write_text(json.dumps(data,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
PY

as_root install -d -m 0700 "$EVIDENCE_DIR"
final="$EVIDENCE_DIR/caddy-production-canary-$stamp.json"
as_root install -m 0600 "$temporary" "$final"
rm -f -- "$temporary"; trap - EXIT
printf '%s\n' "$http3_output"
printf 'CADDY_PRODUCTION_CANARY=PASS\nEVIDENCE=%s\nSOURCE_SHA=%s\nIMAGE=%s\nCONFIG_SHA256=%s\nLISTENER_OWNERSHIP=CADDY_PROCESS_ONLY\nEFFECTIVE_LOG_REDACTION=PASS\nHTTP3=PASS\n' "$final" "$actual_source" "$actual_image" "$actual_config"
