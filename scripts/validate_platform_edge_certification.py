#!/usr/bin/env python3
"""Validate the fail-closed Caddy/platform edge-certification source contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .hash_config_tree import EXCLUDED_TOP_LEVEL, config_tree_hash
except ImportError:  # Direct script execution from scripts/.
    from hash_config_tree import EXCLUDED_TOP_LEVEL, config_tree_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts/platform-edge-certification.v1.json"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_TOP_LEVEL = {
    "schema",
    "recordedDate",
    "authorityIssue",
    "configurationAuthority",
    "integrationReleaseAuthority",
    "componentAuthorities",
    "sourceEvidence",
    "requiredRuntimeEvidence",
    "certificationChecks",
    "failClosedPolicy",
    "safetyBoundary",
    "promotion",
    "status",
}
EXPECTED_COMPONENTS = {
    "edge": {
        "repository": "appolon1908-hue/Caddy",
        "role": "tls-wss-edge",
    },
    "gateway": {
        "repository": "appolon1908-hue/Kong",
        "role": "authentication-authorization-rate-route-policy",
    },
    "identity": {
        "repository": "appolon1908-hue/Keycloak",
        "role": "oidc-token-issuer",
    },
    "middleware": {
        "repository": "appolon1908-hue/Middleware-",
        "role": "business-api-command-and-write-boundary",
    },
}
EXPECTED_CERTIFICATION_CHECKS = {
    "hostnamesAndTlsInventory",
    "certificateRenewalMonitoring",
    "privateUpstreamIdentity",
    "strictForwardingWithoutBypass",
    "healthReadinessVersionReadback",
    "certificateExpiryReadback",
    "deterministicFailClosedUpstreamBehavior",
    "routeParity",
    "isolatedStagingProof",
    "backupAndRollback",
}
EXPECTED_BLOCKED_ROUTES = {
    "/api/v1/control/callbacks",
    "/api/v1/callbacks",
    "/api/v1/automation/policy-check",
    "/api/v1/integrations/n8n/results",
}
EXPECTED_READBACKS = {
    "health",
    "readiness",
    "version",
    "certificate-expiry",
    "source-sha",
    "image-digest",
    "configuration-sha256",
}
EXPECTED_WORKFLOWS = {
    ".github/workflows/immutable-release.yml",
    ".github/workflows/staging-certification.yml",
    ".github/workflows/bounded-runtime-certification.yml",
}
EXPECTED_RUNTIME_SCRIPTS = {
    "scripts/bounded-staging-runtime-v2.sh",
    "scripts/certify_caddy_kong_middleware_runtime.py",
    "scripts/verify-rollback-baseline.sh",
}
EXPECTED_EVIDENCE_OUTPUTS = {
    "bounded-staging-runtime-evidence.json",
    "caddy-kong-middleware-runtime-evidence.json",
    "verified-staging-attestation.json",
    "one-click-rollback-evidence.json",
}
EXPECTED_PROMOTION_CHAIN = ["development", "test", "staging", "production", "main"]
CONFIG_IDENTITY_POLICY = "git-tree-and-content-digest-survive-squash"
RUNTIME_MARKERS = {
    "scripts/bounded-staging-runtime-v2.sh": {
        "certificate_expiry",
        "mtls_without_cert",
        "mtls_denial",
        "runtime_config_sha256",
        '"sanitized_logs": "PASS"',
        '"public_traffic_changed": False',
    },
    "scripts/certify_caddy_kong_middleware_runtime.py": {
        '"caddy_to_kong_to_middleware": "PASS"',
        '"application_mutations": 0',
        '"provider_effects": 0',
        '"external_effects_authorized": False',
    },
    "scripts/verify-rollback-baseline.sh": {
        "CADDY_ROLLBACK_REHEARSAL=PASS",
        "ROLLBACK_CONFIG_SHA256",
    },
}


class ContractError(ValueError):
    """Raised when the certification contract fails closed."""


def fail(reason: str) -> None:
    raise ContractError(reason)


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=strict_object,
        )
    except ContractError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid_contract:{exc.__class__.__name__}")
    if not isinstance(value, dict):
        fail("contract_object_required")
    return value


def require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"object_required:{name}")
    return value


def require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"string_required:{name}")
    return value


def require_string_set(value: Any, name: str) -> set[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        fail(f"unique_string_list_required:{name}")
    return set(value)


def require_exact_keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        fail(f"unexpected_keys:{name}")


def git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"git_evidence:{arguments[0]}:{exc.__class__.__name__}")
    value = result.stdout.strip()
    if not value:
        fail(f"git_evidence_empty:{arguments[0]}")
    return value


def resolve_repo_file(root: Path, raw: Any, name: str) -> Path:
    text = require_string(raw, name)
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"unsafe_repository_path:{name}")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        fail(f"evidence_file_missing:{text}")
    return path


def validate_configuration_authority(root: Path, raw: Any) -> dict[str, Any]:
    authority = require_dict(raw, "configurationAuthority")
    require_exact_keys(
        authority,
        {
            "repository",
            "role",
            "candidateBranch",
            "configurationRoot",
            "configurationTreeGitSha",
            "configurationDigestAlgorithm",
            "configurationSha256",
            "configurationIdentityPolicy",
            "excludedTopLevelRuntimeMounts",
        },
        "configurationAuthority",
    )
    tree_sha = require_string(
        authority.get("configurationTreeGitSha"),
        "configurationTreeGitSha",
    )
    digest = require_string(
        authority.get("configurationSha256"),
        "configurationSha256",
    )
    if (
        authority.get("repository") != "appolon1908-hue/Caddy"
        or authority.get("role") != "principal-caddy-configuration-source"
        or authority.get("candidateBranch") != "development"
        or authority.get("configurationRoot") != "config"
        or authority.get("configurationDigestAlgorithm")
        != "codestra.config-tree-sha256.v1"
        or authority.get("configurationIdentityPolicy") != CONFIG_IDENTITY_POLICY
        or not SHA40_RE.fullmatch(tree_sha)
        or not SHA64_RE.fullmatch(digest)
        or authority.get("excludedTopLevelRuntimeMounts") != ["private"]
        or EXCLUDED_TOP_LEVEL != {"private"}
    ):
        fail("configuration_authority")

    config_root = root / "config"
    if config_tree_hash(config_root) != digest:
        fail("configuration_digest_drift")
    if git(root, "rev-parse", "HEAD:config") != tree_sha:
        fail("current_configuration_tree_drift")
    if git(root, "cat-file", "-t", tree_sha) != "tree":
        fail("configuration_tree_object")
    return authority


def validate_contract(root: Path, contract_path: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    value = load_contract(contract_path.resolve(strict=True))
    require_exact_keys(value, EXPECTED_TOP_LEVEL, "root")

    if value.get("schema") != "codestra.caddy-platform-edge-certification.v1":
        fail("schema")
    if value.get("recordedDate") != "2026-09-04":
        fail("recorded_date")
    if value.get("authorityIssue") != "https://github.com/appolon1908-hue/Caddy/issues/105":
        fail("authority_issue")

    validate_configuration_authority(root, value.get("configurationAuthority"))

    integration = require_dict(
        value.get("integrationReleaseAuthority"),
        "integrationReleaseAuthority",
    )
    require_exact_keys(
        integration,
        {
            "repository",
            "role",
            "principalConfigurationSource",
            "mayReceiveNewCaddyFeatureDevelopment",
        },
        "integrationReleaseAuthority",
    )
    if integration != {
        "repository": "appolon1908-hue/codestra-production-platform",
        "role": "integration-release-runtime-evidence-authority",
        "principalConfigurationSource": False,
        "mayReceiveNewCaddyFeatureDevelopment": False,
    }:
        fail("integration_release_authority")

    components = require_dict(value.get("componentAuthorities"), "componentAuthorities")
    if components != EXPECTED_COMPONENTS:
        fail("component_authorities")

    source = require_dict(value.get("sourceEvidence"), "sourceEvidence")
    require_exact_keys(
        source,
        {"routeContract", "crossRepositoryEvidence", "validators"},
        "sourceEvidence",
    )
    if source.get("routeContract") != "config/caddy-kong-contract.v2.json":
        fail("route_contract")
    if source.get("crossRepositoryEvidence") != (
        "config/caddy-kong-middleware-route-evidence.v1.json"
    ):
        fail("cross_repository_evidence")
    if require_string_set(source.get("validators"), "validators") != {
        "scripts/validate_cross_repository_route_contract.py",
        "scripts/validate_platform_edge_certification.py",
    }:
        fail("validator_set")
    resolve_repo_file(root, source["routeContract"], "routeContract")
    resolve_repo_file(root, source["crossRepositoryEvidence"], "crossRepositoryEvidence")
    for path in source["validators"]:
        resolve_repo_file(root, path, "validator")

    runtime = require_dict(value.get("requiredRuntimeEvidence"), "requiredRuntimeEvidence")
    require_exact_keys(
        runtime,
        {
            "stagingEnvironment",
            "productionCanaryEnvironment",
            "workflows",
            "scripts",
            "evidenceOutputs",
            "requiredReadbacks",
        },
        "requiredRuntimeEvidence",
    )
    if (
        runtime.get("stagingEnvironment") != "staging-readonly"
        or runtime.get("productionCanaryEnvironment")
        != "production-readonly-canary"
        or require_string_set(runtime.get("workflows"), "workflows")
        != EXPECTED_WORKFLOWS
        or require_string_set(runtime.get("scripts"), "scripts")
        != EXPECTED_RUNTIME_SCRIPTS
        or require_string_set(runtime.get("evidenceOutputs"), "evidenceOutputs")
        != EXPECTED_EVIDENCE_OUTPUTS
        or require_string_set(runtime.get("requiredReadbacks"), "requiredReadbacks")
        != EXPECTED_READBACKS
    ):
        fail("runtime_evidence_contract")
    for path in runtime["workflows"] + runtime["scripts"]:
        resolve_repo_file(root, path, "runtimeEvidence")

    checks = require_dict(value.get("certificationChecks"), "certificationChecks")
    require_exact_keys(checks, EXPECTED_CERTIFICATION_CHECKS, "certificationChecks")
    if any(enabled is not True for enabled in checks.values()):
        fail("certification_check_disabled")

    fail_closed = require_dict(value.get("failClosedPolicy"), "failClosedPolicy")
    require_exact_keys(
        fail_closed,
        {
            "genericApiFallbackAllowed",
            "uncontractedRoutesReturn404",
            "privateUpstreamIdentityRequired",
            "blockedUntilImplemented",
        },
        "failClosedPolicy",
    )
    if (
        fail_closed.get("genericApiFallbackAllowed") is not False
        or fail_closed.get("uncontractedRoutesReturn404") is not True
        or fail_closed.get("privateUpstreamIdentityRequired") is not True
        or require_string_set(
            fail_closed.get("blockedUntilImplemented"),
            "blockedUntilImplemented",
        )
        != EXPECTED_BLOCKED_ROUTES
    ):
        fail("fail_closed_policy")

    safety = require_dict(value.get("safetyBoundary"), "safetyBoundary")
    require_exact_keys(
        safety,
        {
            "productionCanaryAllowedMethods",
            "maximumProductionCanaryPercent",
            "applicationMutationsAllowed",
            "providerEffectsAllowed",
            "externalEffectsAllowed",
            "publicTrafficMutationAuthorizedByThisContract",
            "dnsTlsFirewallSshMutationAuthorizedByThisContract",
        },
        "safetyBoundary",
    )
    if (
        require_string_set(
            safety.get("productionCanaryAllowedMethods"),
            "productionCanaryAllowedMethods",
        )
        != {"GET", "HEAD"}
        or type(safety.get("maximumProductionCanaryPercent")) is not int
        or safety.get("maximumProductionCanaryPercent") != 1
        or safety.get("applicationMutationsAllowed") is not False
        or safety.get("providerEffectsAllowed") is not False
        or safety.get("externalEffectsAllowed") is not False
        or safety.get("publicTrafficMutationAuthorizedByThisContract") is not False
        or safety.get("dnsTlsFirewallSshMutationAuthorizedByThisContract") is not False
    ):
        fail("safety_boundary")

    promotion = require_dict(value.get("promotion"), "promotion")
    require_exact_keys(
        promotion,
        {
            "chain",
            "rebuildOrRetagBetweenStagesAllowed",
            "sameImageDigestRequired",
            "sameConfigurationDigestRequired",
        },
        "promotion",
    )
    if (
        promotion.get("chain") != EXPECTED_PROMOTION_CHAIN
        or promotion.get("rebuildOrRetagBetweenStagesAllowed") is not False
        or promotion.get("sameImageDigestRequired") is not True
        or promotion.get("sameConfigurationDigestRequired") is not True
    ):
        fail("promotion_contract")

    status = require_dict(value.get("status"), "status")
    require_exact_keys(
        status,
        {"sourceContract", "runtimeCertification", "productionCertified"},
        "status",
    )
    if status != {
        "sourceContract": "READY",
        "runtimeCertification": "REQUIRED",
        "productionCertified": False,
    }:
        fail("status_must_remain_fail_closed")

    for path, markers in RUNTIME_MARKERS.items():
        text = resolve_repo_file(root, path, "runtimeMarkerSource").read_text(
            encoding="utf-8"
        )
        missing = sorted(marker for marker in markers if marker not in text)
        if missing:
            fail(f"runtime_evidence_marker_missing:{path}:{missing[0]}")

    return value


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        print(
            "usage: validate_platform_edge_certification.py [CONTRACT]",
            file=sys.stderr,
        )
        return 2
    contract_path = Path(arguments[0]) if arguments else DEFAULT_CONTRACT
    try:
        value = validate_contract(ROOT, contract_path)
    except (ContractError, OSError, ValueError) as exc:
        print(f"CADDY_PLATFORM_EDGE_SOURCE_CONTRACT=FAIL:{exc}", file=sys.stderr)
        return 2

    authority = value["configurationAuthority"]
    print(f"CADDY_CONFIG_TREE_GIT_SHA={authority['configurationTreeGitSha']}")
    print(f"CADDY_CONFIG_SHA256={authority['configurationSha256']}")
    print(f"CADDY_CONFIG_IDENTITY_POLICY={authority['configurationIdentityPolicy']}")
    print("PLATFORM_INTEGRATION_AUTHORITY=PASS")
    print("CADDY_PRINCIPAL_CONFIGURATION_AUTHORITY=PASS")
    print("CADDY_PLATFORM_EDGE_SOURCE_CONTRACT=PASS")
    print("RUNTIME_CERTIFICATION_REMAINS_REQUIRED=true")
    print("PRODUCTION_CERTIFIED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
