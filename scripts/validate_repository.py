#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    ".github/CODEOWNERS",
    ".github/SECURITY.md",
    ".github/workflows/apply-branch-ruleset.yml",
    ".github/workflows/bounded-runtime-certification.yml",
    ".github/workflows/immutable-release.yml",
    ".github/workflows/manual-production-orchestrator.yml",
    ".github/workflows/validate.yml",
    "AGENTS.md",
    "CADDY-UPSTREAM-MODULES.lock",
    "Dockerfile",
    "README.md",
    "SECURITY.md",
    "config/Caddyfile",
    "config/conf.d/automation-editor.caddy",
    "config/github/protected-branches-ruleset.json",
    "config/release-baseline.v1.json",
    "config/snippets/logging.caddy",
    "config/snippets/security.caddy",
    "config/snippets/transport.caddy",
    "config/sites/api.codestra.co.caddy",
    "config/sites/legacy-api.codestra.agency.caddy",
    "contracts/caddy-kong-route-contract.v1.json",
    "deploy/compose.runtime.yaml",
    "docs/CADDY-KONG-ROUTING-CONTRACT.md",
    "docs/COMMUNITY-N8N-SECURITY-MODEL.md",
    "scripts/build-caddy-release.sh",
    "scripts/build-release-inputs.sh",
    "scripts/caddy_readonly_validator.py",
    "scripts/capture-runtime-baseline.sh",
    "scripts/hash_config_tree.py",
    "scripts/prepare-runtime-pki-permissions.sh",
    "scripts/production-canary.sh",
    "scripts/rollback-runtime.sh",
    "scripts/run-immutable-runtime.sh",
    "scripts/validate-ci.sh",
    "scripts/validate_repository.py",
    "scripts/verify-image-attestation.py",
    "scripts/verify-rollback-baseline.sh",
    "scripts/verify_caddy_kong_contract.py",
    "tests/community-n8n-security-test.sh",
    "tests/runtime-bind-test.sh",
    "tests/runtime-canary-test.sh",
    "tests/test_bounded_runtime_certification.py",
    "tests/test_manual_production_orchestrator.py",
    "tests/test_release_remediation.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    require(not missing, f"missing canonical repository paths: {missing}")
    require(not (ROOT / "candidate").exists(), "candidate/ must not be deployable")
    require(not (ROOT / "Caddyfile").exists(), "root Caddyfile is a competing authority")
    require(
        not (ROOT / "config/sites/current-production.caddy").exists(),
        "current-production.caddy is a competing API authority",
    )

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    for token in (
        "ARG CADDY_RUNTIME_IMAGE=",
        "ARG CADDY_UPSTREAM_SHA=",
        "ARG CADDY_BINARY_SHA256=",
        "ARG CADDY_HTTP3_PROBE_SHA256=",
        "COPY --from=build /out/caddy",
        "COPY --from=build /out/codestra-http3-probe",
        "COPY --from=build /out/caddy-modules.txt",
        "LABEL org.opencontainers.image.revision=$VCS_REF",
        "LABEL io.codestra.caddy.config.sha256=$CONFIG_SHA256",
        'USER 65532:65532',
        'ENTRYPOINT ["/usr/bin/caddy"]',
    ):
        require(token in dockerfile, f"Dockerfile missing {token}")
    require("docker.io/library/caddy:" not in dockerfile, "runtime may not use stock Caddy")
    require("latest" not in dockerfile, "Dockerfile may not use latest")

    compose = (ROOT / "deploy/compose.runtime.yaml").read_text(encoding="utf-8")
    for token in (
        "container_name: codestra-caddy",
        "ghcr.io/appolon1908-hue/codestra-caddy@sha256:${CADDY_IMAGE_SHA256:?",
        'network_mode: host',
        'user: "65532:65532"',
        "read_only: true",
        "cap_drop:\n      - ALL",
        "cap_add:\n      - NET_BIND_SERVICE",
        "no-new-privileges:true",
        "CADDY_CONTAINER_NAME=codestra-caddy",
        "io.codestra.caddy.source.sha=${CADDY_REVIEWED_SHA:?",
        "io.codestra.caddy.image.digest=sha256:${CADDY_IMAGE_SHA256:?",
        "io.codestra.caddy.config.sha256=${CADDY_CONFIG_SHA256:?",
        "io.codestra.caddy.release.id=${CADDY_RELEASE_ID:?",
        "source: ${CADDY_DATA_DIR:?",
        "source: ${CADDY_CONFIG_DIR:?",
        "/etc/caddy/private/klyrow-events:ro",
        "/etc/codestra/pki/middleware-private-ingress:ro",
    ):
        require(token in compose, f"runtime Compose missing {token}")
    require("ports:" not in compose, "host-network runtime may not publish duplicate ports")
    require("latest" not in compose, "runtime Compose may not use latest")

    global_options = (ROOT / "config/conf.d/00-global-options.caddy").read_text(
        encoding="utf-8"
    )
    for token in (
        "admin 127.0.0.1:2019",
        "persist_config off",
        "metrics",
        "metrics_per_host off",
        "auto_https disable_redirects",
        "client_ip_headers X-Forwarded-For",
        "trusted_proxies static private_ranges",
    ):
        require(token in global_options, f"global options missing {token}")

    caddyfile = (ROOT / "config/Caddyfile").read_text(encoding="utf-8")
    imports = [line.strip() for line in caddyfile.splitlines() if line.strip()]
    require(imports == ["import conf.d/*.caddy", "import sites/*.caddy"], "root import contract")

    logging = (ROOT / "config/snippets/logging.caddy").read_text(encoding="utf-8")
    for token in (
        "request>headers>Authorization delete",
        "request>headers>Proxy-Authorization delete",
        "request>headers>Cookie delete",
        "request>headers>Apikey delete",
        "request>headers>X-Api-Key delete",
        "request>headers>X-Auth-Request-Access-Token delete",
        "request>uri>query>access_token delete",
        "request>uri>query>api-key delete",
        "request>uri>query>api_key delete",
        "request>uri>query>apikey delete",
        "request>uri>query>client_secret delete",
        "request>uri>query>code delete",
        "request>uri>query>id_token delete",
        "request>uri>query>refresh_token delete",
        "request>uri>query>session_state delete",
        "request>uri>query>state delete",
        "resp_headers>Set-Cookie delete",
        "resp_headers>X-Auth-Request-Access-Token delete",
        "roll_size 10MiB",
        "roll_keep 5",
    ):
        require(token in logging, f"logging redaction missing {token}")

    log_sources = 0
    for path in sorted((ROOT / "config").rglob("*.caddy")):
        text = path.read_text(encoding="utf-8")
        if "log {" in text:
            log_sources += 1
            require("import sanitized_access_log" in text, f"unsanitized access log: {path}")
    require(log_sources > 0, "no Caddy access logs discovered")

    security = (ROOT / "config/snippets/security.caddy").read_text(encoding="utf-8")
    for token in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        require(token in security, f"security headers missing {token}")

    api = (ROOT / "config/sites/api.codestra.co.caddy").read_text(encoding="utf-8")
    legacy = (ROOT / "config/sites/legacy-api.codestra.agency.caddy").read_text(encoding="utf-8")
    for text in (api, legacy):
        require("{$CADDY_KONG_UPSTREAM}" in text, "API host must route through Kong")
        require('respond "Not Found" 404' in text, "unknown API routes must fail closed")
        require("CADDY_LEGACY_API_UPSTREAM" not in text, "unrestricted legacy fallback")
        require("127.0.0.1:18101" not in text, "direct legacy middleware bypass")
    require("api.codestra.co" in api, "canonical API host missing")
    require("api.codestra.agency" in legacy, "legacy API host missing")

    contract = json.loads(
        (ROOT / "contracts/caddy-kong-route-contract.v1.json").read_text(encoding="utf-8")
    )
    require(contract.get("schema_version") == 1, "route contract schema")
    require(contract.get("kong_upstream") == "127.0.0.1:8000", "Kong upstream contract")
    require(contract.get("realtime_upstream") == "127.0.0.1:18102", "realtime upstream")
    require(
        contract.get("canonical_host", {}).get("name") == "api.codestra.co",
        "canonical host contract",
    )
    require(
        contract.get("legacy_host", {}).get("name") == "api.codestra.agency",
        "legacy host contract",
    )
    for route in contract.get("routes", []):
        require(route.get("auth_plugin"), f"route {route.get('name')} has no auth plugin")
        require(route.get("rate_limit_policy"), f"route {route.get('name')} has no rate limit")
        require(route.get("owner"), f"route {route.get('name')} has no owner")
        require(route.get("upstream_service"), f"route {route.get('name')} has no upstream")
    require(contract.get("unknown_route_policy", {}).get("status") == 404, "unknown route")

    validator = (ROOT / "scripts/caddy_readonly_validator.py").read_text(encoding="utf-8")
    for token in (
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
        "effective_access_log_redaction",
        'require_listener(sockets, "tcp", public_bind, 80, runtime_pid)',
        'require_listener(sockets, "tcp", public_bind, 443, runtime_pid)',
        'require_listener(sockets, "udp", public_bind, 443, runtime_pid)',
        'require_listener(sockets, "tcp", metrics_bind, 2020, runtime_pid)',
    ):
        require(token in validator, f"container validator missing {token}")
    require("systemctl" not in validator, "validator may not use host systemd")
    require("caddy.service" not in validator, "validator may not use service state")

    release = (ROOT / ".github/workflows/immutable-release.yml").read_text(encoding="utf-8")
    release_trigger = release.split("\npermissions:", 1)[0]
    require("workflow_call:" in release_trigger, "release must be reusable")
    require("\n  push:" not in release_trigger, "release must not auto-run on push")
    for token in (
        "source_sha:",
        "Reject every source except the current protected production head",
        "test \"$GITHUB_REF\" = refs/heads/production",
        "test \"$(git rev-parse origin/production)\" = \"$SOURCE_SHA\"",
        "build-release-inputs.sh",
        "runtime-bind-test.sh",
        "runtime-canary-test.sh",
        "trivy-action@",
        "cosign sign --yes",
        "cosign attest --yes",
        "sbom: true",
        "provenance: mode=max",
        "release_evidence_sha256",
        "rollback_evidence_sha256",
    ):
        require(token in release, f"release workflow missing {token}")

    bounded = (ROOT / ".github/workflows/bounded-runtime-certification.yml").read_text(
        encoding="utf-8"
    )
    bounded_trigger = bounded.split("\npermissions:", 1)[0]
    require("workflow_call:" in bounded_trigger, "bounded runtime must be reusable")
    require("\n  push:" not in bounded_trigger, "bounded runtime must not auto-run on push")
    for token in (
        "source_sha:",
        "image:",
        "image_digest:",
        "config_sha256:",
        "runs-on: [self-hosted, codestra-staging]",
        "environment: staging-readonly",
        "staging_evidence_sha256",
        "needs: bounded-staging-runtime",
        "runs-on: [self-hosted, codestra-production-canary]",
        "environment: production-readonly-canary",
        "production_canary_evidence_sha256",
        "bounded-staging-runtime-v2.sh",
        "bounded-production-readonly-canary-v2.sh",
    ):
        require(token in bounded, f"bounded runtime workflow missing {token}")

    orchestrator = (ROOT / ".github/workflows/manual-production-orchestrator.yml").read_text(
        encoding="utf-8"
    )
    orchestrator_trigger = orchestrator.split("\npermissions:", 1)[0]
    require("workflow_dispatch:" in orchestrator_trigger, "orchestrator must be manual")
    require("\n  push:" not in orchestrator_trigger, "orchestrator may not auto-run")
    for token in (
        "test \"$GITHUB_REF\" = refs/heads/production",
        "git merge-base --is-ancestor origin/staging",
        "uses: ./.github/workflows/immutable-release.yml",
        "uses: ./.github/workflows/bounded-runtime-certification.yml",
        "runs-on: [self-hosted, codestra-production]",
        "environment: production-activation",
        "scripts/capture-runtime-baseline.sh",
        "scripts/run-immutable-runtime.sh",
        "scripts/rollback-runtime.sh",
        "production-activation-evidence.json",
        "verify-complete-one-click-evidence-chain",
        "FULL_PRODUCTION_GO",
        '"unified_compose": "deploy/compose.runtime.yaml"',
    ):
        require(token in orchestrator, f"manual orchestrator missing {token}")
    require("latest" not in orchestrator, "orchestrator may not use mutable tags")

    baseline = json.loads(
        (ROOT / "config/release-baseline.v1.json").read_text(encoding="utf-8")
    )
    require(baseline.get("schema") == "codestra.caddy-release-baseline.v1", "baseline schema")
    require(re.fullmatch(r"[0-9a-f]{40}", baseline.get("source_sha", "")) is not None, "baseline SHA")
    require(
        re.fullmatch(
            r"ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}",
            baseline.get("image", ""),
        )
        is not None,
        "baseline image",
    )
    require(baseline.get("mutable") is False, "baseline must be immutable")

    capture = (ROOT / "scripts/capture-runtime-baseline.sh").read_text(encoding="utf-8")
    for token in (
        "CADDY_ROLLBACK_BASELINE_FILE",
        "codestra.caddy-runtime-rollback-baseline.v1",
        "signature_verified",
        "listener_ownership",
        "effective_access_log_redaction",
        "install -m 0600 -o root -g root",
        "CADDY_BASELINE_CAPTURE=PASS",
    ):
        require(token in capture, f"baseline capture missing {token}")

    rollback = (ROOT / "scripts/rollback-runtime.sh").read_text(encoding="utf-8")
    for token in (
        "CADDY_ROLLBACK_BASELINE_FILE",
        "codestra.caddy-release-baseline.v1",
        "codestra.caddy-runtime-rollback-baseline.v1",
        '"$COSIGN_BIN" verify',
        "up -d --pull never --no-build",
        "production-canary.sh",
        "CADDY_ROLLBACK=PASS",
    ):
        require(token in rollback, f"rollback script missing {token}")

    activation = (ROOT / "scripts/run-immutable-runtime.sh").read_text(encoding="utf-8")
    for token in (
        "CADDY_ROLLBACK_BASELINE_FILE",
        "rollback_baseline_required",
        "rollback-runtime.sh",
        "automatic_rollback",
        "final_identity_readback",
        "CADDY_ACTIVATION=PASS",
    ):
        require(token in activation, f"activation script missing {token}")

    ruleset = json.loads(
        (ROOT / "config/github/protected-branches-ruleset.json").read_text(
            encoding="utf-8"
        )
    )
    require(ruleset.get("enforcement") == "active", "ruleset must be active")
    require(ruleset.get("bypass_actors") == [], "ruleset may not define bypass actors")
    require(
        set(ruleset.get("conditions", {}).get("ref_name", {}).get("include", []))
        == {
            "refs/heads/development",
            "refs/heads/test",
            "refs/heads/staging",
            "refs/heads/production",
            "refs/heads/main",
        },
        "ruleset branch targets",
    )
    pull_rule = next(rule for rule in ruleset["rules"] if rule["type"] == "pull_request")
    require(
        pull_rule["parameters"]["required_approving_review_count"] == 0,
        "ruleset approvals must use repository-configured policy",
    )
    require(
        pull_rule["parameters"]["allowed_merge_methods"] == ["merge"],
        "squash and rebase must not erase promotion ancestry",
    )
    status_rule = next(
        rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
    )
    require(
        {item["context"] for item in status_rule["parameters"]["required_status_checks"]}
        == {
            "validate-source",
            "validate-merge-result",
            "promotion-guard",
            "immutable-release-gate",
        },
        "canonical required checks",
    )

    apply_ruleset = (ROOT / ".github/workflows/apply-branch-ruleset.yml").read_text(
        encoding="utf-8"
    )
    for token in (
        "CODESTRA_REPOSITORY_ADMIN_TOKEN",
        "Protect Caddy promotion branches",
        "required_approving_review_count",
        "allowed_merge_methods",
        "AI automated production gates",
        "Protect main",
        "--method DELETE",
        "CADDY_BRANCH_RULESET_APPLIED=PASS",
        "CADDY_LEGACY_MAIN_RULESETS_RETIRED=PASS",
    ):
        require(token in apply_ruleset, f"ruleset workflow missing {token}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for token in (
        "manual-production-orchestrator.yml",
        "one manual dispatch",
        "deploy/compose.runtime.yaml",
        "staging-readonly",
        "production-readonly-canary",
        "production-activation",
        "automatic rollback",
        "does not authorize application writes",
    ):
        require(token.lower() in readme.lower(), f"README missing {token}")

    print("CADDY_SINGLE_CONFIGURATION_AUTHORITY=PASS")
    print("CADDY_TO_KONG_CONTRACT=PASS")
    print("CADDY_UNRESTRICTED_LEGACY_FALLBACK=ABSENT")
    print("CADDY_CREDENTIAL_REDACTION=PASS")
    print("CADDY_CONTAINER_RUNTIME_CONTRACT=PASS")
    print("CADDY_CONTAINER_LISTENER_OWNERSHIP=PASS")
    print("CADDY_BRANCH_RULESET_CONTRACT=PASS")
    print("CADDY_MANUAL_ONE_CLICK_ORCHESTRATOR=PASS")
    print("CADDY_CAPTURED_ROLLBACK_BASELINE=PASS")
    print("CADDY_REPOSITORY_READINESS=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"CADDY_REPOSITORY_READINESS=FAIL:{exc}", file=sys.stderr)
        raise SystemExit(1)
