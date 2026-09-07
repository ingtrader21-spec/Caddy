#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CADDY_VALIDATOR_IMAGE='docker.io/library/caddy@sha256:ae4458638da8e1a91aafffb231c5f8778e964bca650c8a8cb23a7e8ac557aa3c'
cd "$ROOT"
python3 scripts/validate_calling_contract_pin.py
python3 scripts/validate_calling_contract_pin.py --self-test
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(git ls-files -z '*.sh')
printf 'SHELL_SYNTAX=PASS\n'
python3 -m compileall -q scripts tests
python3 scripts/test_caddy_kong_contract.py
python3 scripts/validate_cross_repository_route_contract.py
python3 scripts/validate_platform_edge_certification.py
python3 scripts/validate_repository.py
python3 scripts/validate_complete_redaction.py
python3 scripts/validate_community_n8n.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 - <<'PY'
import json
from pathlib import Path
for path in Path('config').rglob('*.json'): json.loads(path.read_text())
print('JSON_CONTRACTS=PASS')
PY
validation_pki="$(mktemp -d)"; adapted="$(mktemp)"
trap 'rm -rf -- "$validation_pki" "$adapted"' EXIT
mkdir -p "$validation_pki/middleware" "$validation_pki/klyrow"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=caddy-ci.invalid' -keyout "$validation_pki/validation.key" -out "$validation_pki/validation.crt" >/dev/null 2>&1
install -m 0644 "$validation_pki/validation.crt" "$validation_pki/middleware/server.crt"
install -m 0644 "$validation_pki/validation.crt" "$validation_pki/middleware/staging-server.crt"
install -m 0644 "$validation_pki/validation.crt" "$validation_pki/middleware/client-ca.crt"
install -m 0600 "$validation_pki/validation.key" "$validation_pki/middleware/server.key"
install -m 0600 "$validation_pki/validation.key" "$validation_pki/middleware/staging-server.key"
install -m 0644 "$validation_pki/validation.crt" "$validation_pki/klyrow/tls-fullchain.crt"
install -m 0644 "$validation_pki/validation.crt" "$validation_pki/klyrow/klyrow-client.crt"
install -m 0600 "$validation_pki/validation.key" "$validation_pki/klyrow/tls.key"
common_env=(
-e CADDY_PUBLIC_BIND=192.0.2.10 -e CADDY_PRIVATE_METRICS_BIND=10.40.0.1 -e CADDY_PRIVATE_INGRESS_BIND=10.40.0.1 -e CADDY_KLYROW_SOURCE_CIDRS=10.40.0.4/32 -e CADDY_VICIDIAL_SOURCE_CIDRS=10.40.0.2/32 -e CADDY_STAGING_EVENT_SOURCE_CIDRS=198.51.100.10/32 -e CADDY_KONG_UPSTREAM=127.0.0.1:8000 -e CADDY_REALTIME_UPSTREAM=127.0.0.1:18102 -e CADDY_KEYCLOAK_UPSTREAM=127.0.0.1:18103 -e CADDY_CRM_RESELLER_UPSTREAM=127.0.0.1:18104 -e CADDY_CRM_UPSTREAM=127.0.0.1:18105 -e CADDY_N8N_UPSTREAM=127.0.0.1:18106 -e CADDY_N8N_STAGING_UPSTREAM=127.0.0.1:18107 -e CADDY_STAGING_API_UPSTREAM=127.0.0.1:18108 -e CADDY_STAGING_PORTAL_UPSTREAM=127.0.0.1:18109 -e CADDY_STAGING_KEYCLOAK_UPSTREAM=127.0.0.1:18110 -e CADDY_STAGING_ODOO_UPSTREAM=127.0.0.1:18111 -e CADDY_MIDDLEWARE_CALLBACK_UPSTREAM=127.0.0.1:18112 -e CADDY_AGENT_GATEWAY_UPSTREAM=127.0.0.1:18113 -e CADDY_AGENT_UI_UPSTREAM=127.0.0.1:18114 -e CADDY_MONITORING_UPSTREAM=127.0.0.1:18115 -e CADDY_KLYROW_EVENTS_UPSTREAM=127.0.0.1:18180 -e CADDY_EDITOR_ADMIN_CIDRS=192.0.2.0/24 -e CADDY_N8N_EDITOR_MAX_REQUEST_BODY=16777216 -e CADDY_GRAFANA_UPSTREAM=127.0.0.1:18003 -e CADDY_SUPERSET_UPSTREAM=127.0.0.1:18088 -e CADDY_OPENBAO_UPSTREAM=127.0.0.1:18200 -e 'CADDY_OPENBAO_ALLOWED_CIDRS=192.0.2.0/24 198.51.100.0/24')
common_mounts=(-v "$ROOT:/srv:ro" -v "$validation_pki/middleware:/etc/codestra/pki/middleware-private-ingress:ro" -v "$validation_pki/klyrow:/etc/caddy/private/klyrow-events:ro")
while IFS= read -r -d '' file; do
  docker run --rm --network none --workdir /srv "${common_env[@]}" "${common_mounts[@]}" "$CADDY_VALIDATOR_IMAGE" caddy fmt "/srv/$file" >/dev/null
done < <(find config -type f \( -name Caddyfile -o -name '*.caddy' \) -print0 | sort -z)
printf 'CADDY_FORMAT_PARSE=PASS\n'
docker run --rm --network none --workdir /srv "${common_env[@]}" "${common_mounts[@]}" "$CADDY_VALIDATOR_IMAGE" caddy validate --config /srv/config/Caddyfile --adapter caddyfile
docker run --rm --network none --workdir /srv "${common_env[@]}" "${common_mounts[@]}" "$CADDY_VALIDATOR_IMAGE" caddy adapt --config /srv/config/Caddyfile --adapter caddyfile --validate >"$adapted"
python3 scripts/validate_adapted_config.py "$adapted"
export CADDY_IMAGE_SHA256="$(printf '0%.0s' {1..64})" CADDY_REVIEWED_SHA="$(printf '0%.0s' {1..40})" CADDY_CONFIG_SHA256="$(python3 scripts/hash_config_tree.py config)" CADDY_RELEASE_ID=validation
export CADDY_PUBLIC_BIND=192.0.2.10 CADDY_PRIVATE_METRICS_BIND=10.40.0.1 CADDY_PRIVATE_INGRESS_BIND=10.40.0.1 CADDY_KLYROW_SOURCE_CIDRS=10.40.0.4/32 CADDY_VICIDIAL_SOURCE_CIDRS=10.40.0.2/32 CADDY_STAGING_EVENT_SOURCE_CIDRS=198.51.100.10/32 CADDY_KONG_UPSTREAM=127.0.0.1:8000 CADDY_REALTIME_UPSTREAM=127.0.0.1:18102 CADDY_KEYCLOAK_UPSTREAM=127.0.0.1:18103 CADDY_CRM_RESELLER_UPSTREAM=127.0.0.1:18104 CADDY_CRM_UPSTREAM=127.0.0.1:18105 CADDY_N8N_UPSTREAM=127.0.0.1:18106 CADDY_N8N_STAGING_UPSTREAM=127.0.0.1:18107 CADDY_STAGING_API_UPSTREAM=127.0.0.1:18108 CADDY_STAGING_PORTAL_UPSTREAM=127.0.0.1:18109 CADDY_STAGING_KEYCLOAK_UPSTREAM=127.0.0.1:18110 CADDY_STAGING_ODOO_UPSTREAM=127.0.0.1:18111 CADDY_MIDDLEWARE_CALLBACK_UPSTREAM=127.0.0.1:18112 CADDY_AGENT_GATEWAY_UPSTREAM=127.0.0.1:18113 CADDY_AGENT_UI_UPSTREAM=127.0.0.1:18114 CADDY_MONITORING_UPSTREAM=127.0.0.1:18115 CADDY_KLYROW_EVENTS_UPSTREAM=127.0.0.1:18180 CADDY_EDITOR_ADMIN_CIDRS=192.0.2.0/24 CADDY_N8N_EDITOR_MAX_REQUEST_BODY=16777216 CADDY_GRAFANA_UPSTREAM=127.0.0.1:18003 CADDY_SUPERSET_UPSTREAM=127.0.0.1:18088 CADDY_OPENBAO_UPSTREAM=127.0.0.1:18200
export CADDY_OPENBAO_ALLOWED_CIDRS='192.0.2.0/24 198.51.100.0/24'
docker compose -f deploy/compose.runtime.yaml config --quiet
git diff --check
printf 'CADDY_EXACT_DEPLOYABLE_SOURCE=PASS\n'
