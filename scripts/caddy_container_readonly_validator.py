#!/usr/bin/env python3
"""Fixed-target, read-only validator for the production Caddy container.

The command accepts no arguments and emits only sanitized JSON evidence. It does
not reload Caddy, change Docker state, print environment values or expose the
adapted configuration.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DOCKER = "/usr/bin/docker"
NSENTER = "/usr/bin/nsenter"
SS = "/usr/bin/ss"
CURL = "/usr/bin/curl"
CONTAINER = "codestra-caddy-edge"
RELEASE_ENV = Path("/var/lib/codestra/caddy/release.env")
EXPECTED_REPOSITORY = "https://github.com/appolon1908-hue/Caddy"
EXPECTED_IMAGE_PREFIX = "ghcr.io/appolon1908-hue/codestra-caddy@"
EXPECTED_USER = "65532:65532"
REQUIRED_ENV = {
    "CADDY_KONG_UPSTREAM",
    "CADDY_REALTIME_UPSTREAM",
    "CADDY_KEYCLOAK_UPSTREAM",
    "CADDY_BREERO_KONG_UPSTREAM",
    "CADDY_EDITOR_ADMIN_CIDRS",
    "CADDY_GRAFANA_UPSTREAM",
    "CADDY_SUPERSET_UPSTREAM",
    "CADDY_OPENBAO_HOST",
    "CADDY_OPENBAO_UPSTREAM",
    "CADDY_OPENBAO_ALLOWED_CIDRS",
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
}
REQUIRED_REDACTIONS = {
    "request>headers>Authorization",
    "request>headers>Proxy-Authorization",
    "request>headers>Cookie",
    "request>headers>Apikey",
    "request>headers>X-Api-Key",
    "request>headers>X-Vault-Token",
    "resp_headers>Set-Cookie",
    "resp_headers>Authorization",
    "resp_headers>X-Auth-Request-Access-Token",
}
REQUIRED_QUERY_REDACTIONS = {
    "apikey",
    "api_key",
    "code",
    "state",
    "token",
    "access_token",
    "id_token",
    "refresh_token",
    "client_secret",
    "signature",
}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ValidationError(RuntimeError):
    pass


def run(command: list[str], *, timeout: int = 45) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise ValidationError(f"fixed command failed: {Path(command[0]).name}")
    return result.stdout


def read_release_identity() -> dict[str, str]:
    if not RELEASE_ENV.is_file() or RELEASE_ENV.is_symlink():
        raise ValidationError("protected release identity file is unavailable")
    if RELEASE_ENV.stat().st_mode & 0o077:
        raise ValidationError("protected release identity permissions are too broad")
    values: dict[str, str] = {}
    for raw_line in RELEASE_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in {
            "CADDY_SOURCE_SHA",
            "CADDY_IMAGE_DIGEST",
            "CADDY_CONFIG_SHA256",
            "CADDY_IMAGE",
        }:
            raise ValidationError("release identity contains an unexpected field")
        values[name] = value
    required = {
        "CADDY_SOURCE_SHA",
        "CADDY_IMAGE_DIGEST",
        "CADDY_CONFIG_SHA256",
        "CADDY_IMAGE",
    }
    if set(values) != required:
        raise ValidationError("release identity is incomplete")
    if not SHA.fullmatch(values["CADDY_SOURCE_SHA"]):
        raise ValidationError("invalid source SHA")
    if not DIGEST.fullmatch(values["CADDY_IMAGE_DIGEST"]):
        raise ValidationError("invalid image digest")
    if not re.fullmatch(r"[0-9a-f]{64}", values["CADDY_CONFIG_SHA256"]):
        raise ValidationError("invalid configuration digest")
    if values["CADDY_IMAGE"] != EXPECTED_IMAGE_PREFIX + values["CADDY_IMAGE_DIGEST"]:
        raise ValidationError("image identity does not match its digest")
    return values


def parse_inspect() -> tuple[dict[str, Any], dict[str, Any]]:
    container_payload = json.loads(run([DOCKER, "inspect", CONTAINER]))
    if not isinstance(container_payload, list) or len(container_payload) != 1:
        raise ValidationError("container identity is ambiguous")
    container = container_payload[0]
    configured_image = str((container.get("Config") or {}).get("Image") or "")
    image_payload = json.loads(run([DOCKER, "image", "inspect", configured_image]))
    if not isinstance(image_payload, list) or len(image_payload) != 1:
        raise ValidationError("image identity is ambiguous")
    return container, image_payload[0]


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValidationError("container configuration tree is empty")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def copied_config_digest() -> str:
    with tempfile.TemporaryDirectory(prefix="codestra-caddy-readonly-") as directory:
        destination = Path(directory) / "caddy"
        destination.mkdir(mode=0o700)
        run([DOCKER, "cp", f"{CONTAINER}:/etc/caddy/.", str(destination)])
        return digest_tree(destination)


def require_container_contract(
    container: dict[str, Any], image: dict[str, Any], release: dict[str, str]
) -> tuple[int, set[str]]:
    config = container.get("Config") or {}
    host = container.get("HostConfig") or {}
    state = container.get("State") or {}
    labels = (image.get("Config") or {}).get("Labels") or {}

    if config.get("Image") != release["CADDY_IMAGE"]:
        raise ValidationError("running container is not digest pinned")
    if state.get("Running") is not True:
        raise ValidationError("Caddy container is not running")
    health = state.get("Health") or {}
    if health.get("Status") != "healthy":
        raise ValidationError("Caddy container is not healthy")
    if config.get("User") != EXPECTED_USER:
        raise ValidationError("unexpected runtime user")
    if host.get("ReadonlyRootfs") is not True:
        raise ValidationError("root filesystem is writable")
    if host.get("NetworkMode") != "host":
        raise ValidationError("unexpected network mode")
    if set(host.get("CapDrop") or []) != {"ALL"}:
        raise ValidationError("capability drop policy is incomplete")
    if set(host.get("CapAdd") or []) != {"NET_BIND_SERVICE"}:
        raise ValidationError("unexpected added capabilities")
    if "no-new-privileges:true" not in set(host.get("SecurityOpt") or []):
        raise ValidationError("no-new-privileges is absent")

    repo_digests = set(image.get("RepoDigests") or [])
    if release["CADDY_IMAGE"] not in repo_digests:
        raise ValidationError("local image digest does not match release identity")
    if labels.get("org.opencontainers.image.source") != EXPECTED_REPOSITORY:
        raise ValidationError("OCI source label mismatch")
    if labels.get("org.opencontainers.image.revision") != release["CADDY_SOURCE_SHA"]:
        raise ValidationError("OCI revision label mismatch")
    if labels.get("co.codestra.caddy.config-sha256") != release["CADDY_CONFIG_SHA256"]:
        raise ValidationError("OCI configuration label mismatch")
    if labels.get("co.codestra.caddy.source-root") != "config/Caddyfile":
        raise ValidationError("OCI source-root label mismatch")

    environment = config.get("Env") or []
    names: set[str] = set()
    for entry in environment:
        name, separator, value = str(entry).partition("=")
        if separator:
            names.add(name)
            if name in REQUIRED_ENV and not value:
                raise ValidationError("required runtime environment value is empty")
    if not REQUIRED_ENV.issubset(names):
        raise ValidationError("required runtime environment contract is incomplete")

    pid = state.get("Pid")
    if not isinstance(pid, int) or pid <= 1:
        raise ValidationError("invalid container process identity")
    return pid, names


def require_listeners(pid: int) -> list[str]:
    tcp = run([NSENTER, "-t", str(pid), "-n", SS, "-H", "-lnt"])
    udp = run([NSENTER, "-t", str(pid), "-n", SS, "-H", "-lnu"])
    required = {
        "tcp/80": bool(re.search(r"(?:^|\s)(?:\[[^]]+\]|[^\s]+):80(?:\s|$)", tcp)),
        "tcp/443": bool(re.search(r"(?:^|\s)(?:\[[^]]+\]|[^\s]+):443(?:\s|$)", tcp)),
        "udp/443": bool(re.search(r"(?:^|\s)(?:\[[^]]+\]|[^\s]+):443(?:\s|$)", udp)),
    }
    missing = [name for name, present in required.items() if not present]
    if missing:
        raise ValidationError("required listener is absent")
    return sorted(required)


def require_effective_redaction(adapted: dict[str, Any]) -> int:
    logs = ((adapted.get("logging") or {}).get("logs") or {})
    access_logs = [value for name, value in logs.items() if name != "default"]
    if not access_logs:
        raise ValidationError("adapted access logs are absent")
    for log in access_logs:
        fields = ((log.get("encoder") or {}).get("fields") or {})
        for field in REQUIRED_REDACTIONS:
            if (fields.get(field) or {}).get("filter") != "delete":
                raise ValidationError("effective credential redaction is incomplete")
        uri = fields.get("request>uri") or {}
        deleted = {
            action.get("parameter")
            for action in uri.get("actions") or []
            if action.get("type") == "delete"
        }
        if uri.get("filter") != "query" or not REQUIRED_QUERY_REDACTIONS.issubset(deleted):
            raise ValidationError("effective query redaction is incomplete")
    return len(access_logs)


def main() -> int:
    if len(sys.argv) != 1:
        raise ValidationError("arguments are not accepted")
    for command in (DOCKER, NSENTER, SS, CURL):
        if not Path(command).is_file():
            raise ValidationError("required fixed command is unavailable")

    release = read_release_identity()
    container, image = parse_inspect()
    pid, environment_names = require_container_contract(container, image, release)
    config_digest = copied_config_digest()
    if config_digest != release["CADDY_CONFIG_SHA256"]:
        raise ValidationError("running configuration checksum mismatch")

    run(
        [
            DOCKER,
            "exec",
            CONTAINER,
            "/usr/bin/caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        ]
    )
    adapted = json.loads(
        run(
            [
                DOCKER,
                "exec",
                CONTAINER,
                "/usr/bin/caddy",
                "adapt",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
        )
    )
    access_logger_count = require_effective_redaction(adapted)
    modules = run([DOCKER, "exec", CONTAINER, "/usr/bin/caddy", "list-modules", "--packages"])
    module_lines = sorted(line.strip() for line in modules.splitlines() if line.strip())
    listeners = require_listeners(pid)
    run([CURL, "--fail", "--silent", "--show-error", "--max-time", "5", "http://127.0.0.1:2020/healthz"])

    evidence = {
        "schema": "codestra.caddy-container-readonly-validation.v1",
        "container": CONTAINER,
        "source_sha": release["CADDY_SOURCE_SHA"],
        "image_digest": release["CADDY_IMAGE_DIGEST"],
        "config_sha256": config_digest,
        "container_running": True,
        "container_healthy": True,
        "runtime_user": EXPECTED_USER,
        "read_only_rootfs": True,
        "no_new_privileges": True,
        "capabilities": ["NET_BIND_SERVICE"],
        "listeners": listeners,
        "required_environment_names": sorted(REQUIRED_ENV),
        "observed_environment_name_count": len(environment_names),
        "module_count": len(module_lines),
        "module_manifest_sha256": hashlib.sha256("\n".join(module_lines).encode()).hexdigest(),
        "access_logger_count": access_logger_count,
        "credential_redaction": "PASS",
        "configuration_validation": "PASS",
        "private_health": "PASS",
    }
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"CADDY_CONTAINER_READONLY_VALIDATION=FAIL:{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
