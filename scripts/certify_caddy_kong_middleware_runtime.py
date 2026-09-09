#!/usr/bin/env python3
"""GET-only staging proof for Keycloak -> Caddy -> Kong -> Middleware."""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE_EVIDENCE = ROOT / "config/caddy-kong-middleware-route-evidence.v1.json"
DEFAULT_SECRET_FILE = Path(
    "/etc/codestra/caddy/secrets/n8n-automation-client-secret"
)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ALLOWED_ROUTE_HOSTS = {
    "api.codestra.co": "canonical",
    "bridge-staging.codestra.agency": "staging",
}


class CertificationError(RuntimeError):
    """Fail-closed runtime certification error without sensitive values."""


def fail(reason: str) -> None:
    raise CertificationError(reason)


def run_curl(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["/usr/bin/curl", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=25,
    )
    if result.returncode != 0:
        fail("curl_transport")
    return result


def decode_jwt_claims(token: str) -> dict[str, object]:
    if token.count(".") != 2:
        fail("token_shape")
    encoded = token.split(".", 2)[1]
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        claims = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        fail("token_payload")
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


def validate_secret_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail("n8n_client_secret_missing")
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        fail("n8n_client_secret_file")

    mode = stat.S_IMODE(metadata.st_mode)
    effective_uid = os.geteuid()
    readable_groups = set(os.getgroups()) | {os.getegid()}
    owner_private = metadata.st_uid == effective_uid and mode in {0o400, 0o600}
    root_group_private = (
        metadata.st_uid == 0
        and metadata.st_gid != 0
        and metadata.st_gid in readable_groups
        and mode in {0o440, 0o640}
    )
    if not (owner_private or root_group_private) or mode & 0o007:
        fail("n8n_client_secret_permissions")
    if not os.access(path, os.R_OK):
        fail("n8n_client_secret_unreadable")

    value = path.read_bytes()
    if not 8 <= len(value) <= 4096 or value != value.strip():
        fail("n8n_client_secret_format")


def load_source_contract() -> tuple[dict, dict, str]:
    try:
        source = json.loads(SOURCE_EVIDENCE.read_text(encoding="utf-8"))
        identity = source["keycloak"]
        middleware_sha = source["middleware"]["protectedMainSha"]
        proof = source["runtimeProofContract"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        fail("source_contract")
    if (
        not isinstance(identity, dict)
        or not isinstance(proof, dict)
        or not isinstance(middleware_sha, str)
        or not SHA_RE.fullmatch(middleware_sha)
    ):
        fail("source_contract")
    return identity, proof, middleware_sha


def certify(*, ip: str, port: int) -> None:
    """Run only during the exact bounded staging listener invocation."""

    env_file_value = os.environ.get("CADDY_STAGING_ENV_FILE", "")
    if not env_file_value:
        return
    if ip != "127.0.0.1" or port != 18443:
        fail("bounded_staging_listener_required")
    route_host = os.environ.get("CADDY_PROOF_API_HOST", "api.codestra.co").strip()
    gateway_environment = ALLOWED_ROUTE_HOSTS.get(route_host)
    if gateway_environment is None:
        fail("proof_api_host")
    os.umask(0o077)

    configured = os.environ.get("CADDY_STAGING_N8N_CLIENT_SECRET_FILE", "").strip()
    secret_path = Path(configured) if configured else DEFAULT_SECRET_FILE
    validate_secret_file(secret_path)

    runtime_env = parse_runtime_env(Path(env_file_value))
    middleware_upstream = runtime_env.get("CADDY_STAGING_API_UPSTREAM", "")
    if not middleware_upstream:
        fail("middleware_version_upstream_missing")

    identity, proof, expected_middleware_sha = load_source_contract()
    identity_host = identity.get("stagingHost")
    expected_issuer = identity.get("stagingIssuer")
    client_id = identity.get("clientId")
    expected_audience = identity.get("audience")
    maximum_lifetime = identity.get("maximumAccessTokenLifetimeSeconds")
    required_scopes = set(identity.get("requiredScopes") or [])
    expected_path = proof.get("path")
    expected_status = proof.get("expectedAuthenticatedStatus")
    expected_error = proof.get("expectedErrorCode")
    if (
        identity_host != "auth-staging.codestra.co"
        or expected_issuer != "https://auth-staging.codestra.co/realms/codestra"
        or client_id != "n8n-automation"
        or expected_audience != "middleware-api"
        or maximum_lifetime != 300
        or "middleware.status.read" not in required_scopes
        or proof.get("identityEnvironment") != "staging"
        or proof.get("expectedIssuer") != expected_issuer
        or not isinstance(expected_path, str)
        or not expected_path.startswith("/v1/integrations/n8n/operations/")
        or expected_status != 404
        or expected_error != "command_not_found"
        or proof.get("expectedMiddlewareSourceSha") != expected_middleware_sha
        or proof.get("mutationAllowed") is not False
        or proof.get("externalEffectsAllowed") is not False
    ):
        fail("runtime_proof_contract")

    with tempfile.TemporaryDirectory(prefix="caddy-middleware-proof-") as temporary:
        temp = Path(temporary)
        token_path = temp / "token.json"
        token_result = run_curl(
            [
                "--noproxy", "*", "--silent", "--show-error", "--max-time", "15",
                "--output", str(token_path), "--write-out", "%{http_code}",
                "--resolve", f"{identity_host}:{port}:{ip}",
                "--header", "Content-Type: application/x-www-form-urlencoded",
                "--data-urlencode", "grant_type=client_credentials",
                "--data-urlencode", f"client_id={client_id}",
                "--data-urlencode", f"client_secret@{secret_path}",
                f"https://{identity_host}:{port}/realms/codestra/protocol/openid-connect/token",
            ]
        )
        if token_result.stdout.strip() != "200":
            fail("keycloak_client_credentials")
        try:
            token = json.loads(token_path.read_text(encoding="utf-8"))["access_token"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            fail("keycloak_token_response")
        if not isinstance(token, str) or not 32 <= len(token) <= 16384:
            fail("keycloak_access_token")

        claims = decode_jwt_claims(token)
        now = int(time.time())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        audience = claims.get("aud")
        if isinstance(audience, str):
            audiences = {audience}
        elif isinstance(audience, list) and all(isinstance(item, str) for item in audience):
            audiences = set(audience)
        else:
            audiences = set()
        scopes = set(str(claims.get("scope", "")).split())
        tenant = claims.get("tenant_id")
        if (
            claims.get("iss") != expected_issuer
            or claims.get("azp") != client_id
            or expected_audience not in audiences
            or "middleware.status.read" not in scopes
            or not isinstance(issued_at, int)
            or not isinstance(expires_at, int)
            or not issued_at <= now < expires_at
            or not 1 <= expires_at - issued_at <= maximum_lifetime
            or not isinstance(tenant, str)
            or not TENANT_RE.fullmatch(tenant)
        ):
            fail("keycloak_token_claims")

        curl_config = temp / "request.conf"
        curl_config.write_text(
            f'header = "Authorization: Bearer {token}"\n'
            f'header = "X-Tenant-ID: {tenant}"\n'
            'header = "X-Correlation-ID: caddy-kong-middleware-certification"\n'
            'header = "Accept: application/json"\n',
            encoding="utf-8",
        )
        curl_config.chmod(0o600)
        del token

        route_body = temp / "route.json"
        route_result = run_curl(
            [
                "--noproxy", "*", "--silent", "--show-error", "--max-time", "15",
                "--config", str(curl_config), "--output", str(route_body),
                "--write-out", "%{http_code}", "--resolve",
                f"{route_host}:{port}:{ip}",
                f"https://{route_host}:{port}{expected_path}",
            ]
        )
        try:
            route_error = json.loads(route_body.read_text(encoding="utf-8"))["error"]["code"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            fail("middleware_route_response")
        route_status = route_result.stdout.strip()
        if route_status != str(expected_status) or route_error != expected_error:
            fail("middleware_route_result")

        version_body = temp / "version.json"
        version_result = run_curl(
            [
                "--noproxy", "*", "--silent", "--show-error", "--max-time", "15",
                "--output", str(version_body), "--write-out", "%{http_code}",
                normalize_version_url(middleware_upstream),
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
        config_checksum = version.get("configuration_checksum")
        if (
            runtime_sha != expected_middleware_sha
            or not isinstance(image_digest, str)
            or not SHA256_RE.fullmatch(image_digest)
            or not isinstance(config_checksum, str)
            or not HEX64_RE.fullmatch(config_checksum)
            or version.get("environment") != "staging"
        ):
            fail("middleware_version_identity")

        evidence = {
            "schema": "codestra.caddy-kong-middleware-runtime.v1",
            "caddy_source_sha": os.environ.get("CADDY_STAGING_SOURCE_SHA"),
            "caddy_image": os.environ.get("CADDY_STAGING_IMAGE"),
            "caddy_config_sha256": os.environ.get("CADDY_STAGING_CONFIG_SHA256"),
            "gateway_environment": gateway_environment,
            "keycloak": {
                "source_sha": identity.get("protectedMainSha"),
                "environment": "staging",
                "issuer": claims.get("iss"),
                "client_id": claims.get("azp"),
                "audience": sorted(audiences),
                "scope_verified": "middleware.status.read",
                "tenant_claim_present": True,
                "token_lifetime_seconds": expires_at - issued_at,
            },
            "route": {
                "method": "GET",
                "edge_host": route_host,
                "gateway_environment": gateway_environment,
                "path": expected_path,
                "status": int(route_status),
                "middleware_error_code": route_error,
                "caddy_to_kong_to_middleware": "PASS",
            },
            "middleware": {
                "source_sha": runtime_sha,
                "image_digest": image_digest,
                "configuration_checksum": config_checksum,
                "environment": version.get("environment"),
            },
            "application_mutations": 0,
            "provider_effects": 0,
            "external_effects_authorized": False,
            "result": "PASS",
        }
        output = ROOT / "caddy-kong-middleware-runtime-evidence.json"
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.chmod(0o600)


def main() -> int:
    try:
        certify(ip=os.environ.get("CADDY_PROOF_IP", "127.0.0.1"), port=int(os.environ.get("CADDY_PROOF_PORT", "18443")))
    except (CertificationError, ValueError) as exc:
        reason = str(exc) or "invalid_runtime_input"
        raise SystemExit(f"CADDY_RUNTIME_CANARY=FAIL:{reason}") from exc
    print("CADDY_KONG_MIDDLEWARE_RUNTIME=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
