#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
SITE = (ROOT / "sites" / "api.codestra.co.caddy").read_text(encoding="utf-8")

required = (
    "appolon1908-hue/Caddy",
    "appolon1908-hue/Kong",
    "appolon1908-hue/Middleware-",
    "appolon1908-hue/codestra-production-platform",
)
for value in required:
    if value not in README:
        raise SystemExit(f"CADDY_AUTHORITY_ERROR=missing_reference:{value}")

if "historical runtime/deployment/reconciliation evidence only" not in README:
    raise SystemExit("CADDY_AUTHORITY_ERROR=platform_not_reference_only")
if "operations/caddy/api.codestra.co.caddy" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=missing_import_provenance")
if "api.codestra.co {" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=missing_api_site")
if "Authorization delete" not in SITE:
    raise SystemExit("CADDY_AUTHORITY_ERROR=authorization_log_redaction_missing")

secret_patterns = (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)client_secret\s*[=:]\s*[^<\s][^\s]*",
    r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~-]+",
)
for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pattern in secret_patterns:
        if re.search(pattern, text):
            raise SystemExit(f"CADDY_AUTHORITY_ERROR=possible_secret:{path.relative_to(ROOT)}")

print("CADDY_REPOSITORY_AUTHORITY=PASS")
print("CADDY_PRINCIPAL=appolon1908-hue/Caddy")
print("PRODUCTION_PLATFORM=REFERENCE_ONLY")
print("LIVE_RELOAD_AUTHORIZED=NO")
