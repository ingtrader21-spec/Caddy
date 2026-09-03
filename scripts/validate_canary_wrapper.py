#!/usr/bin/env python3
"""Validate the deterministic protected-canary wrapper transformation."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/run_production_readonly_canary.sh"
IMPLEMENTATION = ROOT / "scripts/production_readonly_canary.sh"


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    source = IMPLEMENTATION.read_text(encoding="utf-8")

    required_wrapper_tokens = (
        "sudo -n true",
        "install -o root -g root -m 0400",
        "CADDY_CANARY_ENV_FILE",
        "CADDY_CANARY_MTLS_CLIENT_KEY",
        "CADDY_CANARY_DATA_SOURCE",
        "production-canary-evidence.json",
        "pre-canary-runtime.json",
        "post-canary-runtime.json",
        "CADDY_CANARY_WRAPPER=PASS",
    )
    for token in required_wrapper_tokens:
        if token not in wrapper:
            fail(f"canary wrapper is missing {token}")

    transformed = source.replace(
        "Sec-WebSocket-Key: Y2FuYXJ5LXJlYWRvbmx5\\r\\n",
        "Sec-WebSocket-Key: Y2FuYXJ5LXJlYWRvbmx5IQ==\\r\\n",
    )
    old = 'large_status="$(head -c 11000000 /dev/zero | curl'
    new = '''large_status="$(set +o pipefail
head -c 11000000 /dev/zero | curl'''
    transformed = transformed.replace(old, new)

    if transformed == source:
        fail("canary wrapper transformation changed nothing")
    if "Y2FuYXJ5LXJlYWRvbmx5IQ==" not in transformed:
        fail("valid WebSocket nonce is absent")
    if new not in transformed:
        fail("isolated pipefail override is absent")
    if transformed.count("Y2FuYXJ5LXJlYWRvbmx5IQ==") != 1:
        fail("WebSocket nonce replacement is ambiguous")
    if transformed.count(new) != 1:
        fail("oversized-body replacement is ambiguous")

    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sh") as handle:
        handle.write(transformed)
        handle.flush()
        subprocess.run(["bash", "-n", handle.name], check=True)

    print("CADDY_CANARY_WRAPPER_SOURCE_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
