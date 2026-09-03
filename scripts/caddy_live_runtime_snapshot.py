#!/usr/bin/env python3
"""Emit a sanitized, fixed-target snapshot of the unchanged live Caddy edge.

The snapshot supports the migration boundary: an already-reconciled immutable
container or the pre-migration systemd Caddy service. It never prints raw Caddy
configuration, environment values, credentials, certificate material, or logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DOCKER = "/usr/bin/docker"
SYSTEMCTL = "/usr/bin/systemctl"
CADDY = "/usr/bin/caddy"
SS = "/usr/bin/ss"
CONTAINER = "codestra-caddy-edge"
CONFIG_ROOT = Path("/etc/caddy")


class SnapshotError(RuntimeError):
    pass


def run(command: list[str], timeout: int = 45) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise SnapshotError(f"fixed command failed: {Path(command[0]).name}")
    return result.stdout


def digest_paths(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.relative_to(root).parts[0] not in {"private", "data"}
        and path.suffix in {"", ".caddy", ".json"}
    )
    if not files:
        raise SnapshotError("live Caddy source is unavailable")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def listeners() -> list[str]:
    tcp = run([SS, "-H", "-lnt"])
    udp = run([SS, "-H", "-lnu"])
    result = []
    for protocol, port, source in (("tcp", 80, tcp), ("tcp", 443, tcp), ("udp", 443, udp)):
        if re.search(rf"(?:^|\s)(?:\[[^]]+\]|[^\s]+):{port}(?:\s|$)", source):
            result.append(f"{protocol}/{port}")
    if set(result) != {"tcp/80", "tcp/443", "udp/443"}:
        raise SnapshotError("live edge listener set is incomplete")
    return sorted(result)


def canonical_container_snapshot() -> dict[str, Any] | None:
    result = subprocess.run(
        [DOCKER, "inspect", CONTAINER],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or len(payload) != 1:
        raise SnapshotError("canonical container identity is ambiguous")
    item = payload[0]
    config = item.get("Config") or {}
    state = item.get("State") or {}
    image_name = str(config.get("Image") or "")
    images = json.loads(run([DOCKER, "image", "inspect", image_name]))
    if not isinstance(images, list) or len(images) != 1:
        raise SnapshotError("canonical image identity is ambiguous")
    image = images[0]
    labels = (image.get("Config") or {}).get("Labels") or {}
    if state.get("Running") is not True:
        raise SnapshotError("canonical container is not running")
    return {
        "schema": "codestra.caddy-live-runtime-snapshot.v1",
        "mode": "immutable-container",
        "container": CONTAINER,
        "container_id": str(item.get("Id") or ""),
        "process_id": int(state.get("Pid") or 0),
        "image": image_name,
        "repo_digests": sorted(image.get("RepoDigests") or []),
        "source_sha": labels.get("org.opencontainers.image.revision"),
        "config_sha256": labels.get("co.codestra.caddy.config-sha256"),
        "runtime_user": config.get("User"),
        "health": (state.get("Health") or {}).get("Status"),
        "listeners": listeners(),
        "service_active": True,
    }


def legacy_systemd_snapshot() -> dict[str, Any]:
    if not Path(SYSTEMCTL).is_file() or not Path(CADDY).is_file():
        raise SnapshotError("legacy fixed commands are unavailable")
    if run([SYSTEMCTL, "is-active", "caddy.service"]).strip() != "active":
        raise SnapshotError("legacy caddy.service is not active")
    pid_text = run([SYSTEMCTL, "show", "--property", "MainPID", "--value", "caddy.service"]).strip()
    if not pid_text.isdigit() or int(pid_text) <= 1:
        raise SnapshotError("legacy Caddy process identity is invalid")
    pid = int(pid_text)
    run([CADDY, "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"])
    executable = Path(f"/proc/{pid}/exe").resolve(strict=True)
    binary_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    return {
        "schema": "codestra.caddy-live-runtime-snapshot.v1",
        "mode": "legacy-systemd",
        "service": "caddy.service",
        "process_id": pid,
        "binary_sha256": binary_sha256,
        "config_sha256": digest_paths(CONFIG_ROOT),
        "listeners": listeners(),
        "service_active": True,
    }


def main() -> int:
    if len(sys.argv) != 1:
        raise SnapshotError("arguments are not accepted")
    for command in (DOCKER, SS):
        if not Path(command).is_file():
            raise SnapshotError("required fixed command is unavailable")
    snapshot = canonical_container_snapshot() or legacy_systemd_snapshot()
    print(json.dumps(snapshot, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SnapshotError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"CADDY_LIVE_RUNTIME_SNAPSHOT=FAIL:{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)
