#!/usr/bin/env python3
from __future__ import annotations

import base64
import secrets
import socket
import ssl
import subprocess
import sys
from pathlib import Path

from certify_caddy_kong_middleware_runtime import CertificationError, certify

ROOT = Path(__file__).resolve().parents[1]

if len(sys.argv) not in (4, 5):
    raise SystemExit("usage: websocket_probe.py HOST IP PATH [PORT]")
host, ip, path = sys.argv[1:4]
if len(sys.argv) == 5:
    try:
        port = int(sys.argv[4])
    except ValueError as exc:
        raise SystemExit("WEBSOCKET_CANARY=FAIL:invalid_port") from exc
else:
    port = 443
    if ip == "127.0.0.1":
        with socket.socket() as probe_socket:
            probe_socket.settimeout(0.5)
            if probe_socket.connect_ex((ip, 18443)) == 0:
                port = 18443
if not 1 <= port <= 65535:
    raise SystemExit("WEBSOCKET_CANARY=FAIL:invalid_port")

websocket_key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
with socket.create_connection((ip, port), timeout=10) as raw:
    with context.wrap_socket(raw, server_hostname=host) as connection:
        connection.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                f"Sec-WebSocket-Key: {websocket_key}\r\n\r\n"
            ).encode()
        )
        response = connection.recv(4096).decode("latin-1")
if not response.startswith("HTTP/1.1 101"):
    raise SystemExit(
        f"WEBSOCKET_CANARY=FAIL:{response.splitlines()[0] if response else 'empty'}"
    )
print("WEBSOCKET_CANARY=PASS")

probe = ROOT / "build" / "codestra-http3-probe"
if port == 443 and probe.is_file():
    result = subprocess.run(
        [str(probe), host, ip, "/api/v1/health"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        diagnostic = (result.stderr or "http3_probe_failed").strip().splitlines()[-1]
        raise SystemExit(diagnostic)
    print(result.stdout.strip())

try:
    certify(ip=ip, port=port)
except CertificationError as exc:
    raise SystemExit(f"CADDY_RUNTIME_CANARY=FAIL:{exc}") from exc
