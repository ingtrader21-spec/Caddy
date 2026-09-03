#!/usr/bin/env python3
"""Enforce the complete shared Caddy access-log redaction contract."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGGING = ROOT / "config" / "snippets" / "logging.caddy"
SOURCES = [
    *sorted((ROOT / "config" / "sites").glob("*.caddy")),
    *sorted((ROOT / "config" / "conf.d").glob("*.caddy")),
]

REQUIRED_FILTERS = {
    "request>headers>Authorization delete",
    "request>headers>Proxy-Authorization delete",
    "request>headers>Cookie delete",
    "request>headers>Apikey delete",
    "request>headers>X-Api-Key delete",
    "request>headers>X-Auth-Request-Access-Token delete",
    "request>headers>X-Access-Token delete",
    "request>headers>X-Id-Token delete",
    "request>headers>X-Refresh-Token delete",
    "request>headers>X-Vault-Token delete",
    "request>headers>X-Bao-Token delete",
    "delete access_token",
    "delete api-key",
    "delete api_key",
    "delete apikey",
    "delete client_secret",
    "delete code",
    "delete id_token",
    "delete oauth_token",
    "delete refresh_token",
    "delete session_state",
    "delete state",
    "delete token",
    "resp_headers>Authorization delete",
    "resp_headers>Proxy-Authorization delete",
    "resp_headers>Set-Cookie delete",
    "resp_headers>X-Access-Token delete",
    "resp_headers>X-Auth-Request-Access-Token delete",
    "resp_headers>X-Id-Token delete",
    "resp_headers>X-Refresh-Token delete",
}


def main() -> int:
    source = LOGGING.read_text(encoding="utf-8")
    missing = sorted(token for token in REQUIRED_FILTERS if token not in source)
    if missing:
        raise SystemExit("CADDY_COMPLETE_REDACTION=FAIL:missing=" + ",".join(missing))

    unsanitized = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        if "log {" in text and "import sanitized_access_log" not in text:
            unsanitized.append(path.relative_to(ROOT).as_posix())
    if unsanitized:
        raise SystemExit("CADDY_COMPLETE_REDACTION=FAIL:unsanitized=" + ",".join(unsanitized))

    print("CADDY_COMPLETE_CREDENTIAL_REDACTION=PASS")
    print(f"CADDY_SANITIZED_ACCESS_LOG_SOURCES={len(SOURCES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
