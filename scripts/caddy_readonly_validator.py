#!/usr/bin/env python3
"""Fixed-target, read-only production Caddy validator.

This program accepts no arguments and never emits raw Caddy configuration.
Installation and sudo/forced-command wiring are deliberately outside this
source change and require the protected deployment authority.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

CADDY = "/usr/bin/caddy"
SYSTEMCTL = "/usr/bin/systemctl"
CONFIG = Path("/etc/caddy/Caddyfile")
CONFIG_ROOT = Path("/etc/caddy")
SAFE_DIAL = re.compile(r"^(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?$")
REQUIRED_REDACTIONS = (
    "request>headers>Authorization delete",
    "request>headers>Apikey delete",
    "request>headers>X-Api-Key delete",
    "delete apikey",
)


class ValidationError(RuntimeError):
    pass


def run_fixed(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise ValidationError(f"fixed command failed: {command[1]}")
    return result.stdout


def canonical_source() -> tuple[str, str]:
    paths = [CONFIG]
    for pattern in ("sites/*.caddy", "snippets/*.caddy"):
        paths.extend(sorted(CONFIG_ROOT.glob(pattern)))
    if any(not path.is_file() for path in paths):
        raise ValidationError("canonical Caddy source is incomplete")
    payload = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    return payload, hashlib.sha256(payload.encode()).hexdigest()


def require_redaction(source: str) -> None:
    missing = [token for token in REQUIRED_REDACTIONS if token not in source]
    if missing:
        raise ValidationError("credential redaction policy is incomplete")


def sanitized_summary(adapted: dict[str, Any]) -> dict[str, Any]:
    hosts: set[str] = set()
    paths: set[str] = set()
    upstreams: set[str] = set()
    header_names: set[str] = set()
    duration_fields: set[str] = set()
    mtls_present = False

    def visit(value: Any, key: str = "") -> None:
        nonlocal mtls_present
        if isinstance(value, dict):
            for child_key, child in value.items():
                lowered = child_key.lower()
                if lowered in {"client_authentication", "client_certificate", "client_ca_pool"}:
                    mtls_present = True
                if lowered in {"headers", "set", "add", "delete"} and isinstance(child, dict):
                    header_names.update(str(name) for name in child)
                if any(part in lowered for part in ("timeout", "keepalive", "duration")):
                    duration_fields.add(child_key)
                visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str):
            if key == "host" and re.fullmatch(r"[A-Za-z0-9.*_-]+", value):
                hosts.add(value)
            elif key == "path" and value.startswith("/") and "?" not in value:
                paths.add(value)
            elif key == "dial":
                if not SAFE_DIAL.fullmatch(value):
                    raise ValidationError("unsafe upstream representation")
                upstreams.add(value)

    visit(adapted)
    return {
        "hosts": sorted(hosts),
        "paths": sorted(paths),
        "upstreams": sorted(upstreams),
        "header_names": sorted(header_names),
        "duration_fields": sorted(duration_fields),
        "mtls_policy_present": mtls_present,
        "websocket_transport_supported": bool(upstreams),
    }


def main() -> int:
    if len(sys.argv) != 1:
        raise ValidationError("arguments are not accepted")
    source, checksum = canonical_source()
    require_redaction(source)
    run_fixed([CADDY, "validate", "--config", str(CONFIG)])
    if run_fixed([SYSTEMCTL, "is-active", "caddy.service"]).strip() != "active":
        raise ValidationError("caddy.service is not active")
    adapted = json.loads(run_fixed([CADDY, "adapt", "--config", str(CONFIG), "--pretty"]))
    evidence = {
        "schema": "codestra.caddy-readonly-validation.v1",
        "config_sha256": checksum,
        "config_validation": "PASS",
        "service_active": True,
        "credential_redaction": "PASS",
        "summary": sanitized_summary(adapted),
    }
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"CADDY_READONLY_VALIDATION=FAIL:{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)

