#!/usr/bin/env python3
from __future__ import annotations
import socket,ssl,sys
if len(sys.argv)!=4: raise SystemExit('usage: websocket_probe.py HOST IP PATH')
host,ip,path=sys.argv[1:]; context=ssl.create_default_context(); context.check_hostname=False; context.verify_mode=ssl.CERT_NONE
with socket.create_connection((ip,443),timeout=10) as raw:
    with context.wrap_socket(raw,server_hostname=host) as connection:
        connection.sendall((f'GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n').encode()); response=connection.recv(4096).decode('latin-1')
if not response.startswith('HTTP/1.1 101'): raise SystemExit(f"WEBSOCKET_CANARY=FAIL:{response.splitlines()[0] if response else 'empty'}")
print('WEBSOCKET_CANARY=PASS')
