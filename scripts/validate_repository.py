#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from caddy_kong_contract import validate_exact_kong_routes

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
SITE_DIR = CONFIG / "sites"
CONF_DIR = CONFIG / "conf.d"
WORKFLOWS = ROOT / ".github/workflows"

REQUIRED_PATHS = (
    CONFIG / "Caddyfile",
    CONFIG / "caddy-kong-contract.v2.json",
    CONFIG / "n8n-editor-community.v2.json",
    CONFIG / "observability-exposure.v2.json",
    CONFIG / "release-baseline.v1.json",
    CONFIG / "runtime-values.example",
    CONFIG / "github/protected-branches-ruleset.json",
    CONFIG / "snippets/security.caddy",
    CONFIG / "snippets/logging.caddy",
    SITE_DIR / "api.codestra.co.caddy",
    SITE_DIR / "legacy-api.codestra.agency.caddy",
    SITE_DIR / "automation.codestra.co.caddy",
    SITE_DIR / "codestra.media.observability.caddy",
    ROOT / "Dockerfile",
    ROOT / "deploy/compose.runtime.yaml",
    ROOT / "scripts/caddy_readonly_validator.py",
    ROOT / "scripts/run-immutable-runtime.sh",
    ROOT / "scripts/rollback-runtime.sh",
    ROOT / "scripts/verify-rollback-baseline.sh",
    ROOT / "scripts/production-canary.sh",
    ROOT / "scripts/hash_config_tree.py",
    ROOT / "scripts/verify-image-attestation.py",
    ROOT / "scripts/validate_complete_redaction.py",
    WORKFLOWS / "validate.yml",
    WORKFLOWS / "immutable-release.yml",
    WORKFLOWS / "promotion-guard.yml",
    WORKFLOWS / "apply-branch-ruleset.yml",
)


def require_tokens(source: str, tokens: tuple[str, ...], scope: str) -> None:
    for token in tokens:
        if token not in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR={scope}:{token}")


def main() -> int:
    for path in REQUIRED_PATHS:
        if not path.is_file():
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=missing:{path.relative_to(ROOT)}")

    if (ROOT / "candidate").exists():
        raise SystemExit("CADDY_REPOSITORY_ERROR=competing_candidate_tree")
    if (SITE_DIR / "current-production.caddy").exists():
        raise SystemExit("CADDY_REPOSITORY_ERROR=legacy_aggregate_site_tree")

    caddyfile = (CONFIG / "Caddyfile").read_text(encoding="utf-8")
    require_tokens(
        caddyfile,
        (
            "admin unix//run/caddy/admin.sock",
            "default_bind {$CADDY_PUBLIC_BIND} 127.0.0.1",
            "metrics",
            "bind {$CADDY_PRIVATE_METRICS_BIND}",
            "metrics /metrics",
            "import snippets/*.caddy",
            "import sites/*.caddy",
            "import conf.d/*.caddy",
        ),
        "root_contract",
    )
    if "0.0.0.0:2019" in caddyfile or "admin :2019" in caddyfile:
        raise SystemExit("CADDY_REPOSITORY_ERROR=public_admin_api")

    contract = json.loads((CONFIG / "caddy-kong-contract.v2.json").read_text())
    if (
        contract.get("schema") != "codestra.caddy-kong-edge.v2"
        or contract.get("principalRepository") != "appolon1908-hue/Caddy"
    ):
        raise SystemExit("CADDY_REPOSITORY_ERROR=contract_authority")
    if contract.get("legacyApiFallback") != {
        "enabled": False,
        "unrestrictedCatchAllAllowed": False,
        "unknownPathsReturn": 404,
    }:
        raise SystemExit("CADDY_REPOSITORY_ERROR=legacy_fallback_not_closed")

    managed = contract.get("kongManagedPathPrefixes") or []
    compatibility = contract.get("explicitCompatibilityPaths") or []
    for site_name in ("api.codestra.co.caddy", "legacy-api.codestra.agency.caddy"):
        source = (SITE_DIR / site_name).read_text(encoding="utf-8")
        validate_exact_kong_routes(source, managed)
        if "{$CADDY_KONG_UPSTREAM}" not in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=kong_missing:{site_name}")
        if "CADDY_LEGACY_API_UPSTREAM" in source or "127.0.0.1:18101" in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=legacy_catchall:{site_name}")
        if 'respond "Not Found" 404' not in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=unknown_path_not_closed:{site_name}")
        match = re.search(r"(?m)^\s*@realtime\s+path\s+([^\n#]+)$", source)
        if not match:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=realtime_matcher_missing:{site_name}")
        routed = {
            token[:-1] if token.endswith("*") else token
            for token in match.group(1).split()
        }
        if routed != set(compatibility):
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=realtime_contract_drift:{site_name}")

    logging = (CONFIG / "snippets/logging.caddy").read_text(encoding="utf-8")
    require_tokens(
        logging,
        (
            "request>headers>Authorization delete",
            "request>headers>Proxy-Authorization delete",
            "request>headers>Cookie delete",
            "request>headers>Apikey delete",
            "request>headers>X-Api-Key delete",
            "request>headers>X-Auth-Request-Access-Token delete",
            "request>headers>X-Access-Token delete",
            "request>headers>X-Id-Token delete",
            "request>headers>X-Refresh-Token delete",
            "request>headers>X-Vault-Token delete",
            "request>headers>X-Bao-Token delete",
            "delete api-key",
            "delete api_key",
            "delete apikey",
            "delete client_secret",
            "delete code",
            "delete id_token",
            "delete refresh_token",
            "delete session_state",
            "delete state",
            "resp_headers>Authorization delete",
            "resp_headers>Set-Cookie delete",
            "resp_headers>X-Auth-Request-Access-Token delete",
        ),
        "redaction",
    )

    for path in sorted([*SITE_DIR.glob("*.caddy"), *CONF_DIR.glob("*.caddy")]):
        source = path.read_text(encoding="utf-8")
        if "log {" in source and "import sanitized_access_log" not in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=unsanitized_log:{path.relative_to(ROOT)}")
        if "response>headers>" in source:
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=invalid_log_field:{path.relative_to(ROOT)}")
        if (
            "tls internal" not in source
            and "tls /etc/" not in source
            and "import security_headers" not in source
            and "Strict-Transport-Security" not in source
        ):
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=missing_hsts:{path.relative_to(ROOT)}")

    all_source = "\n".join(path.read_text() for path in CONFIG.rglob("*.caddy"))
    for header in (
        "X-Authenticated-Client",
        "X-Authenticated-Tenant",
        "X-Authenticated-Role",
        "X-Codestra-Gateway-Secret",
    ):
        if re.search(rf"header_up\s+{re.escape(header)}\b", all_source):
            raise SystemExit(f"CADDY_REPOSITORY_ERROR=trusted_identity_header:{header}")

    compose = (ROOT / "deploy/compose.runtime.yaml").read_text(encoding="utf-8")
    require_tokens(
        compose,
        (
            "container_name: codestra-caddy",
            "ghcr.io/appolon1908-hue/codestra-caddy@sha256:${CADDY_IMAGE_SHA256:",
            'user: "65532:65532"',
            "read_only: true",
            "cap_drop:\n      - ALL",
            "cap_add:\n      - NET_BIND_SERVICE",
            "no-new-privileges:true",
            "network_mode: host",
            "io.codestra.caddy.source.sha",
            "io.codestra.caddy.image.digest",
            "io.codestra.caddy.config.sha256",
            "healthcheck:",
        ),
        "runtime",
    )
    if "ports:" in compose or "latest" in compose:
        raise SystemExit("CADDY_REPOSITORY_ERROR=mutable_or_bridged_runtime")

    validator = (ROOT / "scripts/caddy_readonly_validator.py").read_text(encoding="utf-8")
    require_tokens(
        validator,
        (
            'CONTAINER = "codestra-caddy"',
            '[DOCKER, "inspect", CONTAINER]',
            '[DOCKER, "image", "inspect", image_reference]',
            '[DOCKER, "exec", CONTAINER',
            '[DOCKER, "cp"',
            '[DOCKER, "top", CONTAINER',
            "org.opencontainers.image.revision",
            "io.codestra.caddy.config.sha256",
            "list-modules",
            "caddy_host_pid",
            "listener_ownership",
            'require_listener(sockets, "tcp", public_bind, 80, runtime_pid)',
            'require_listener(sockets, "tcp", public_bind, 443, runtime_pid)',
            'require_listener(sockets, "udp", public_bind, 443, runtime_pid)',
            'require_listener(sockets, "tcp", metrics_bind, 2020, runtime_pid)',
            'require_listener(sockets, "tcp", private_bind, 18080, runtime_pid)',
        ),
        "container_validator",
    )
    if "/usr/bin/systemctl" in validator or "caddy.service" in validator:
        raise SystemExit("CADDY_REPOSITORY_ERROR=host_systemd_validator")

    workflow = (WORKFLOWS / "validate.yml").read_text(encoding="utf-8")
    require_tokens(
        workflow,
        (
            "validate-source:",
            "validate-merge-result:",
            "promotion-guard:",
            "immutable-release-gate:",
            "github.event.pull_request.head.sha",
            "github.sha",
            "scripts/validate-ci.sh",
            "tests/runtime-canary-test.sh",
        ),
        "validation_workflow",
    )

    release = (WORKFLOWS / "immutable-release.yml").read_text(encoding="utf-8")
    require_tokens(
        release,
        (
            "branches: [production]",
            "scripts/build-release-inputs.sh",
            "CONFIG_SHA256=",
            "tests/runtime-bind-test.sh",
            "tests/runtime-canary-test.sh",
            "severity: CRITICAL,HIGH",
            "sbom: true",
            "provenance: mode=max",
            "cosign sign-blob",
            "cosign sign --yes",
            "cosign attest --yes",
            "BINARY_BUILD_ATTESTATION=PASS",
            "CANARY_CERTIFICATION=PASS",
            "ROLLBACK_BASELINE=PASS",
            "scripts/verify-rollback-baseline.sh",
        ),
        "release_workflow",
    )
    if "branches: [main]" in release:
        raise SystemExit("CADDY_REPOSITORY_ERROR=release_not_bound_to_production")

    ruleset = json.loads((CONFIG / "github/protected-branches-ruleset.json").read_text())
    refs = set(ruleset["conditions"]["ref_name"]["include"])
    expected_refs = {
        f"refs/heads/{name}"
        for name in ("development", "test", "staging", "production", "main")
    }
    if refs != expected_refs or ruleset.get("bypass_actors"):
        raise SystemExit("CADDY_REPOSITORY_ERROR=ruleset_scope_or_bypass")
    checks: set[str] = set()
    for rule in ruleset["rules"]:
        if rule["type"] == "required_status_checks":
            checks = {
                item["context"]
                for item in rule["parameters"]["required_status_checks"]
            }
    if checks != {
        "validate-source",
        "validate-merge-result",
        "promotion-guard",
        "immutable-release-gate",
    }:
        raise SystemExit("CADDY_REPOSITORY_ERROR=ruleset_checks")

    secret_patterns = (
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?i)client_secret\s*[=:]\s*[^<\s$][^\s]*",
        r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~-]+",
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for pattern in secret_patterns:
            if re.search(pattern, text):
                raise SystemExit(f"CADDY_REPOSITORY_ERROR=possible_secret:{path.relative_to(ROOT)}")

    print("CADDY_SINGLE_CONFIGURATION_AUTHORITY=PASS")
    print("CADDY_TO_KONG_CONTRACT=PASS")
    print("CADDY_UNRESTRICTED_LEGACY_FALLBACK=ABSENT")
    print("CADDY_CREDENTIAL_REDACTION=PASS")
    print("CADDY_CONTAINER_RUNTIME_CONTRACT=PASS")
    print("CADDY_CONTAINER_LISTENER_OWNERSHIP=PASS")
    print("CADDY_BRANCH_RULESET_CONTRACT=PASS")
    print("CADDY_REPOSITORY_READINESS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
