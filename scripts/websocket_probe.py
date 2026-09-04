#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE_EVIDENCE = ROOT / "config/caddy-kong-middleware-route-evidence.v1.json"
DEFAULT_N8N_SECRET_FILE = Path(
    "/etc/codestra/caddy/secrets/n8n-automation-client-secret"
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def fail(reason: str) -> None:
    raise SystemExit(f"CADDY_RUNTIME_CANARY=FAIL:{reason}")


def run_curl(arguments: list[str], *, expected: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["/usr/bin/curl", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=25,
    )
    if expected is None and result.returncode != 0:
        fail("curl_transport")
    if expected is not None and result.returncode not in expected:
        fail("curl_exit")
    return result


def decode_jwt_claims(token: str) -> dict[str, object]:
    if token.count(".") != 2:
        fail("token_shape")
    encoded = token.split(".", 2)[1]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        claims = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        fail(f"token_payload:{exc.__class__.__name__}")
    if not isinstance(claims, dict):
        fail("token_claims")
    return claims


def parse_runtime_env(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        fail("staging_env_file")
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail("staging_env_syntax")
        name, value = line.split("=", 1)
        if name in result or not name or not value:
            fail("staging_env_value")
        result[name] = value
    return result


def normalize_version_url(upstream: str) -> str:
    raw = upstream if "://" in upstream else f"http://{upstream}"
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        fail("middleware_version_upstream")
    path = parsed.path.rstrip("/") + "/version"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def certify_caddy_kong_middleware(*, ip: str, port: int) -> None:
    env_file_value = os.environ.get("CADDY_STAGING_ENV_FILE", "")
    if not env_file_value:
        return
    if port != 18443 or ip != "127.0.0.1":
        fail("bounded_staging_listener_required")

    secret_path = Path(
        os.environ.get(
            "CADDY_STAGING_N8N_CLIENT_SECRET_FILE",
            str(DEFAULT_N8N_SECRET_FILE),
        )
    )
    try:
        secret_stat = secret_path.lstat()
    except FileNotFoundError:
        fail("n8n_client_secret_missing")
    if not stat.S_ISREG(secret_stat.st_mode) or secret_path.is_symlink():
        fail("n8n_client_secret_file")
    if secret_stat.st_uid != 0 or stat.S_IMODE(secret_stat.st_mode) not in {0o400, 0o600}:
        fail("n8n_client_secret_permissions")
    secret_bytes = secret_path.read_bytes()
    if not 8 <= len(secret_bytes) <= 4096 or secret_bytes != secret_bytes.strip():
        fail("n8n_client_secret_format")
    del secret_bytes

    runtime_env = parse_runtime_env(Path(env_file_value))
    middleware_upstream = runtime_env.get("CADDY_STAGING_API_UPSTREAM", "")
    if not middleware_upstream:
        fail("middleware_version_upstream_missing")

    try:
        source_contract = json.loads(MIDDLEWARE_EVIDENCE.read_text(encoding="utf-8"))
        expected_middleware_sha = source_contract["middleware"]["protectedMainSha"]
        proof = source_contract["runtimeProofContract"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        fail("middleware_source_contract")
    if not isinstance(expected_middleware_sha, str) or not re.fullmatch(
        r"[0-9a-f]{40}", expected_middleware_sha
    ):
        fail("middleware_source_sha")
    expected_path = proof.get("path") if isinstance(proof, dict) else None
    expected_status = proof.get("expectedAuthenticatedStatus") if isinstance(proof, dict) else None
    expected_error = proof.get("expectedErrorCode") if isinstance(proof, dict) else None
    if (
        not isinstance(expected_path, str)
        or not expected_path.startswith("/v1/integrations/n8n/operations/")
        or expected_status != 404
        or expected_error != "command_not_found"
    ):
        fail("middleware_runtime_proof_contract")

    with tempfile.TemporaryDirectory(prefix="caddy-middleware-proof-") as temporary:
        temp = Path(temporary)
        token_response_path = temp / "token.json"
        token_result = run_curl(
            [
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--max-time",
                "15",
                "--output",
                str(token_response_path),
                "--write-out",
                "%{http_code}",
                "--resolve",
                f"auth.codestra.co:{port}:{ip}",
                "--header",
                "Content-Type: application/x-www-form-urlencoded",
                "--data-urlencode",
                "grant_type=client_credentials",
                "--data-urlencode",
                "client_id=n8n-automation",
                "--data-urlencode",
                f"client_secret@{secret_path}",
                f"https://auth.codestra.co:{port}/realms/codestra/protocol/openid-connect/token",
            ]
        )
        if token_result.stdout.strip() != "200":
            fail("keycloak_client_credentials")
        try:
            token_payload = json.loads(token_response_path.read_text(encoding="utf-8"))
            access_token = token_payload["access_token"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            fail("keycloak_token_response")
        if not isinstance(access_token, str) or len(access_token) > 16384:
            fail("keycloak_access_token")

        claims = decode_jwt_claims(access_token)
        now = int(time.time())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        audience = claims.get("aud")
        audiences = {audience} if isinstance(audience, str) else set(audience or [])
        scopes = set(str(claims.get("scope", "")).split())
        tenant = claims.get("tenant_id")
        if (
            claims.get("iss") != "https://auth.codestra.co/realms/codestra"
            or claims.get("azp") != "n8n-automation"
            or "middleware-api" not in audiences
            or "middleware.status.read" not in scopes
            or not isinstance(issued_at, int)
            or not isinstance(expires_at, int)
            or not issued_at <= now < expires_at
            or not 1 <= expires_at - issued_at <= 300
            or not isinstance(tenant, str)
            or not TENANT_RE.fullmatch(tenant)
        ):
            fail("keycloak_token_claims")

        curl_config = temp / "request.conf"
        curl_config.write_text(
            "header = \"Authorization: Bearer "
            + access_token
            + "\"\nheader = \"X-Tenant-ID: "
            + tenant
            + "\"\nheader = \"X-Correlation-ID: caddy-kong-middleware-certification\"\n"
            + "header = \"Accept: application/json\"\n",
            encoding="utf-8",
        )
        curl_config.chmod(0o600)
        del access_token

        route_body = temp / "route.json"
        route_result = run_curl(
            [
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--max-time",
                "15",
                "--config",
                str(curl_config),
                "--output",
                str(route_body),
                "--write-out",
                "%{http_code}",
                "--resolve",
                f"api.codestra.co:{port}:{ip}",
                f"https://api.codestra.co:{port}{expected_path}",
            ]
        )
        route_status = route_result.stdout.strip()
        try:
            route_payload = json.loads(route_body.read_text(encoding="utf-8"))
            route_error = route_payload["error"]["code"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            fail("middleware_route_response")
        if route_status != str(expected_status) or route_error != expected_error:
            fail(f"middleware_route:{route_status}:{route_error}")

        version_body = temp / "version.json"
        version_url = normalize_version_url(middleware_upstream)
        version_result = run_curl(
            [
                "--noproxy",
                "*",
                "--silent",
                "--show-error",
                "--max-time",
                "15",
                "--output",
                str(version_body),
                "--write-out",
                "%{http_code}",
                version_url,
            ]
        )
        if version_result.stdout.strip() != "200":
            fail("middleware_version_status")
        try:
            version = json.loads(version_body.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fail("middleware_version_json")
        runtime_sha = version.get("source_sha") or version.get("git_sha")
        image_digest = version.get("image_digest")
        configuration_checksum = version.get("configuration_checksum")
        if (
            runtime_sha != expected_middleware_sha
            or not isinstance(image_digest, str)
            or not SHA256_RE.fullmatch(image_digest)
            or not isinstance(configuration_checksum, str)
            or not HEX64_RE.fullmatch(configuration_checksum)
            or version.get("environment") != "staging"
        ):
            fail("middleware_version_identity")

        evidence = {
            "schema": "codestra.caddy-kong-middleware-runtime.v1",
            "caddy_source_sha": os.environ.get("CADDY_STAGING_SOURCE_SHA"),
            "caddy_image": os.environ.get("CADDY_STAGING_IMAGE"),
            "caddy_config_sha256": os.environ.get("CADDY_STAGING_CONFIG_SHA256"),
            "keycloak": {
                "issuer": claims.get("iss"),
                "client_id": claims.get("azp"),
                "audience": sorted(audiences),
                "scope_verified": "middleware.status.read",
                "token_lifetime_seconds": expires_at - issued_at,
            },
            "route": {
                "method": "GET",
                "path": expected_path,
                "status": int(route_status),
                "middleware_error_code": route_error,
                "caddy_to_kong_to_middleware": "PASS",
            },
            "middleware": {
                "source_sha": runtime_sha,
                "image_digest": image_digest,
                "configuration_checksum": configuration_checksum,
                "environment": version.get("environment"),
            },
            "application_mutations": 0,
            "provider_effects": 0,
            "external_effects_authorized": False,
            "result": "PASS",
        }
        output = ROOT / "caddy-kong-middleware-runtime-evidence.json"
        output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output.chmod(0o600)


if len(sys.argv) not in (4, 5):
    raise SystemExit("usage: websocket_probe.py HOST IP PATH [PORT]")
host, ip, path = sys.argv[1:4]
if len(sys.argv) == 5:
    try:
        port = int(sys.argv[4])
    except ValueError as exc:
        raise SystemExit("WEBSOCKET_CANARY=FAIL:invalid_port") from exc
else:
    # The bounded staging runtime maps its isolated HTTPS listener to the
    # host-loopback port 18443. Other callers retain canonical port 443.
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

# The exact-head hosted canary builds this probe and uses the canonical port;
# bounded staging and production jobs make their own signed-image HTTP/3
# request, so absence here is not treated as a protocol success or failure.
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

certify_caddy_kong_middleware(ip=ip, port=port)
