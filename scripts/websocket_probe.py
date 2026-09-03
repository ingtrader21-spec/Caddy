#!/usr/bin/env python3
from __future__ import annotations

import socket
import ssl
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: websocket_probe.py HOST IP PATH")
host, ip, path = sys.argv[1:]
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
with socket.create_connection((ip, 443), timeout=10) as raw:
    with context.wrap_socket(raw, server_hostname=host) as connection:
        connection.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
            ).encode()
        )
        response = connection.recv(4096).decode("latin-1")
if not response.startswith("HTTP/1.1 101"):
    raise SystemExit(
        f"WEBSOCKET_CANARY=FAIL:{response.splitlines()[0] if response else 'empty'}"
    )
print("WEBSOCKET_CANARY=PASS")

# A UDP bind does not prove HTTP/3. Exercise a real QUIC request against the
# same canonical API host while this canary Caddy process is still running.
probe = Path(__file__).resolve().parents[1] / "build" / "codestra-http3-probe"
if not probe.is_file():
    raise SystemExit("CADDY_HTTP3_CANARY=FAIL:probe_missing")
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
