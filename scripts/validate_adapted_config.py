#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_DELETE_FIELDS = {
    "request>headers>Authorization",
    "request>headers>Proxy-Authorization",
    "request>headers>Cookie",
    "request>headers>Apikey",
    "request>headers>X-Api-Key",
    "request>headers>X-Auth-Request-Access-Token",
    "request>headers>X-Access-Token",
    "request>headers>X-Id-Token",
    "request>headers>X-Refresh-Token",
    "request>headers>X-Vault-Token",
    "request>headers>X-Bao-Token",
    "resp_headers>Authorization",
    "resp_headers>Proxy-Authorization",
    "resp_headers>Set-Cookie",
    "resp_headers>X-Access-Token",
    "resp_headers>X-Auth-Request-Access-Token",
    "resp_headers>X-Id-Token",
    "resp_headers>X-Refresh-Token",
}
REQUIRED_QUERY_DELETIONS = {
    "access_token",
    "api-key",
    "api_key",
    "apikey",
    "client_secret",
    "code",
    "id_token",
    "oauth_token",
    "refresh_token",
    "session_state",
    "state",
    "token",
}


def visit(value: Any, counters: dict[str, int]) -> None:
    if isinstance(value, dict):
        if value.get("handler") == "reverse_proxy":
            counters["reverse_proxy_handlers"] += 1
        if value.get("handler") == "metrics":
            counters["metrics_handlers"] += 1
        for child in value.values():
            visit(child, counters)
    elif isinstance(value, list):
        for child in value:
            visit(child, counters)


def validate_access_logs(adapted: dict[str, Any]) -> int:
    logs = ((adapted.get("logging") or {}).get("logs") or {})
    access_logs = {name: value for name, value in logs.items() if name != "default"}
    if len(access_logs) < 5:
        raise SystemExit("CADDY_ADAPTED_CONFIG=FAIL:missing_access_logs")

    for name, log in access_logs.items():
        fields = ((log.get("encoder") or {}).get("fields") or {})
        missing_fields = sorted(
            field
            for field in REQUIRED_DELETE_FIELDS
            if (fields.get(field) or {}).get("filter") != "delete"
        )
        if missing_fields:
            raise SystemExit(
                f"CADDY_ADAPTED_CONFIG=FAIL:redaction_fields:{name}:"
                + ",".join(missing_fields)
            )

        uri = fields.get("request>uri") or {}
        if uri.get("filter") != "query":
            raise SystemExit(f"CADDY_ADAPTED_CONFIG=FAIL:query_filter:{name}")
        deleted = {
            action.get("parameter")
            for action in (uri.get("actions") or [])
            if action.get("type") == "delete"
        }
        missing_queries = sorted(REQUIRED_QUERY_DELETIONS - deleted)
        if missing_queries:
            raise SystemExit(
                f"CADDY_ADAPTED_CONFIG=FAIL:query_redaction:{name}:"
                + ",".join(missing_queries)
            )
    return len(access_logs)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_adapted_config.py ADAPTED_JSON", file=sys.stderr)
        return 2
    adapted = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    servers = (((adapted.get("apps") or {}).get("http") or {}).get("servers") or {})
    if not servers:
        raise SystemExit("CADDY_ADAPTED_CONFIG=FAIL:no_http_servers")

    counters = {"reverse_proxy_handlers": 0, "metrics_handlers": 0}
    visit(adapted, counters)
    if counters["reverse_proxy_handlers"] < 10:
        raise SystemExit("CADDY_ADAPTED_CONFIG=FAIL:missing_reverse_proxy_handlers")
    if counters["metrics_handlers"] < 1:
        raise SystemExit("CADDY_ADAPTED_CONFIG=FAIL:missing_metrics_handler")
    access_log_count = validate_access_logs(adapted)

    print(
        "CADDY_ADAPTED_CONFIG=PASS "
        f"servers={len(servers)} "
        f"reverse_proxies={counters['reverse_proxy_handlers']} "
        f"logs={access_log_count} "
        "credential_redaction=PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
