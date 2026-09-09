"""Exercise the actual bounded staging curl commands against local TLS servers."""
from __future__ import annotations

import os
import re
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


class StagingProbeTLSTests(unittest.TestCase):
    def probe(self, variable: str, certificate_host: str, trust: bool) -> subprocess.CompletedProcess[str]:
        source = (ROOT / "scripts/bounded-staging-runtime-v2.sh").read_text()
        match = re.search(rf'{variable}="\$\((.*?)\)"', source, re.DOTALL)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            cert, key = work / "cert.pem", work / "key.pem"
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "1", "-subj", "/CN=" + certificate_host,
                "-addext", "subjectAltName=DNS:" + certificate_host,
                "-keyout", str(key), "-out", str(cert),
            ], check=True, capture_output=True)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                command = match.group(1).replace("18443", str(server.server_port))
                environment = {
                    "PATH": os.defpath, "CURL": "/usr/bin/curl",
                    "staging_ca": str(cert) if trust else "/etc/ssl/certs/ca-certificates.crt",
                    "AUTH_HEADER_NAME": "Authorization", "AUTH_SCHEME": "Bearer",
                }
                return subprocess.run(["bash", "-c", command], env=environment,
                                      capture_output=True, text=True, timeout=20)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_internal_probe_accepts_candidate_ca_and_matching_hostname(self) -> None:
        result = self.probe("staging_api_status", "api.staging.internal.codestra.agency", True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "200")

    def test_internal_probe_rejects_untrusted_certificate(self) -> None:
        result = self.probe("staging_api_status", "api.staging.internal.codestra.agency", False)
        self.assertEqual(result.returncode, 60)

    def test_internal_probe_rejects_wrong_hostname(self) -> None:
        result = self.probe("staging_api_status", "wrong.example.invalid", True)
        self.assertEqual(result.returncode, 60)

    def test_bridge_probe_rejects_self_signed_certificate(self) -> None:
        result = self.probe("bridge_staging_status", "bridge-staging.codestra.agency", True)
        self.assertEqual(result.returncode, 60)


if __name__ == "__main__":
    unittest.main()
