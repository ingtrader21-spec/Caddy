#!/usr/bin/env python3
"""Fail-closed repository contract for one Caddy source/runtime model."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def blocks(source: str, directive: str) -> list[str]:
    results: list[str] = []
    pattern = re.compile(rf"(?m)^\s*{re.escape(directive)}(?:\s+[^{{\n]+)?\s*{{")
    for match in pattern.finditer(source):
        depth = 0
        for index in range(match.end() - 1, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    results.append(source[match.start() : index + 1])
                    break
        else:
            raise SystemExit(f"unterminated {directive} block")
    return results


def main() -> int:
    require(CONFIG.is_dir(), "canonical config directory is missing")
    require((CONFIG / "Caddyfile").is_file(), "canonical config/Caddyfile is missing")
    for duplicate in (ROOT / "Caddyfile", ROOT / "sites", ROOT / "snippets"):
        require(not duplicate.exists(), f"duplicate deployable source exists: {duplicate.name}")

    deployable = sorted(CONFIG.rglob("*.caddy")) + [CONFIG / "Caddyfile"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in deployable)
    require(combined.count("api.codestra.co {") == 1, "api.codestra.co must have one authority")
    require("CADDY_LEGACY_API_UPSTREAM" not in combined, "unrestricted legacy API upstream remains")
    require("127.0.0.1:18101" not in (CONFIG / "sites/api.codestra.co.caddy").read_text(encoding="utf-8"), "canonical API bypasses Kong")
    require(not (CONFIG / "sites/current-production.caddy").exists(), "duplicated current-production source remains")

    api = (CONFIG / "sites/api.codestra.co.caddy").read_text(encoding="utf-8")
    for token in (
        "CADDY_KONG_UPSTREAM",
        "X-Codestra-Upstream-Class \"kong\"",
        "X-Codestra-Upstream-Class \"realtime-legacy-v1\"",
        "respond \"Not Found\" 404",
    ):
        require(token in api, f"canonical API contract is missing {token}")

    fallback = json.loads((CONFIG / "legacy-fallbacks.v1.json").read_text(encoding="utf-8"))
    require(fallback.get("default_action") == "deny", "legacy fallback default must deny")
    require(fallback.get("approval_state") == "source-approved-pending-runtime-certification", "fallback approval state is unsafe")
    approved_paths = {
        path
        for entry in fallback.get("approved_fallbacks", [])
        for path in entry.get("paths", [])
    }
    source_paths = {
        "/ws/agent",
        "/api/v1/realtime/sessions",
        "/healthz",
        "/readyz",
        "/version",
    }
    require(approved_paths == source_paths, "fallback manifest and Caddy source paths differ")

    security = (CONFIG / "snippets/security_headers.caddy").read_text(encoding="utf-8")
    required_security = {
        "Strict-Transport-Security",
        "request>headers>Authorization delete",
        "request>headers>Proxy-Authorization delete",
        "request>headers>Cookie delete",
        "request>headers>Apikey delete",
        "request>headers>X-Api-Key delete",
        "request>headers>X-Vault-Token delete",
        "resp_headers>Set-Cookie delete",
        "resp_headers>Authorization delete",
        "resp_headers>X-Auth-Request-Access-Token delete",
        "delete code",
        "delete state",
        "delete access_token",
        "delete refresh_token",
        "delete client_secret",
    }
    require(required_security.issubset(set(line.strip() for line in security.splitlines())), "security/redaction snippet is incomplete")

    access_log_count = 0
    for path in sorted(CONFIG.rglob("*.caddy")):
        source = path.read_text(encoding="utf-8")
        for block in blocks(source, "log"):
            access_log_count += 1
            require("import secure_log_filter" in block, f"access log lacks secure filter: {path}")
    require(access_log_count > 0, "no access log contracts found")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    require("COPY --chown=65532:65532 config/ /etc/caddy/" in dockerfile, "image does not copy canonical config")
    require("co.codestra.caddy.config-sha256" in dockerfile, "image lacks config digest label")
    require("co.codestra.caddy.source-root=\"config/Caddyfile\"" in dockerfile, "image lacks source-root label")

    compose = (ROOT / "deploy/compose.runtime.yaml").read_text(encoding="utf-8")
    for token in (
        "container_name: codestra-caddy-edge",
        "@sha256:${CADDY_IMAGE_SHA256",
        "read_only: true",
        "user: \"65532:65532\"",
        "- ALL",
        "- NET_BIND_SERVICE",
        "no-new-privileges:true",
        "network_mode: host",
        "healthcheck:",
    ):
        require(token in compose, f"runtime contract is missing {token}")

    runtime_validator = (ROOT / "scripts/caddy_container_readonly_validator.py").read_text(encoding="utf-8")
    for token in (
        'CONTAINER = "codestra-caddy-edge"',
        "docker\", \"inspect",
        "RepoDigests",
        "org.opencontainers.image.revision",
        "co.codestra.caddy.config-sha256",
        "ReadonlyRootfs",
        "NET_BIND_SERVICE",
        "list-modules",
        "require_listeners",
        "require_effective_redaction",
    ):
        require(token in runtime_validator, f"runtime validator is missing {token}")
    require(not (ROOT / "scripts/caddy_readonly_validator.py").exists(), "obsolete host validator remains")

    print("CADDY_SINGLE_SOURCE_AUTHORITY=PASS")
    print(f"CADDY_ACCESS_LOG_CONTRACTS={access_log_count}")
    print(f"CADDY_EXPLICIT_FALLBACK_PATHS={len(approved_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
