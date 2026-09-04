#!/usr/bin/env python3
"""Fail-closed controller for the manual Caddy production orchestrator.

The controller never deploys Caddy directly. It only adopts or reruns the two
existing production-push workflow runs, waits for their exact attempts, and
validates the evidence they publish.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_RE = re.compile(
    r"^ghcr\.io/appolon1908-hue/codestra-caddy@sha256:[0-9a-f]{64}$"
)
ALLOWED_WORKFLOWS = {
    ".github/workflows/immutable-release.yml",
    ".github/workflows/bounded-runtime-certification.yml",
}
PASS_RELEASE_GATES = {
    "SBOM",
    "IMAGE_PROVENANCE",
    "SOURCE_PROVENANCE",
    "BINARY_BUILD_ATTESTATION",
    "SIGNATURE",
    "VULNERABILITY_GATE",
    "CANARY_CERTIFICATION",
    "HTTP3_CANARY",
    "ROLLBACK_BASELINE",
    "ROLLBACK_REHEARSAL",
}


class OrchestrationError(RuntimeError):
    """Expected fail-closed orchestration error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OrchestrationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    require(root.is_dir(), f"evidence directory missing: {root}")
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    require(bool(files), f"evidence directory empty: {root}")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_digest = bytes.fromhex(sha256_file(path))
        digest.update(file_digest)
    return digest.hexdigest()


def find_one(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    require(len(matches) == 1, f"expected exactly one {name}, found {len(matches)}")
    require(matches[0].is_file() and not matches[0].is_symlink(), f"invalid {name}")
    return matches[0]


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path.name} must contain a JSON object")
    return value


def parse_key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#"):
            continue
        require("=" in raw, f"malformed evidence line in {path.name}")
        key, value = raw.split("=", 1)
        require(key and key not in result, f"duplicate evidence key {key}")
        result[key] = value
    return result


def append_github_outputs(values: dict[str, str]) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            require("\n" not in value and "\r" not in value, f"unsafe output {key}")
            handle.write(f"{key}={value}\n")


class GitHubAPI:
    def __init__(self, repository: str, token: str) -> None:
        require(
            bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)),
            "invalid repository",
        )
        require(bool(token), "GITHUB_TOKEN is required")
        self.repository = repository
        self.token = token

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repository}/{path.lstrip('/')}"
        body = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "codestra-caddy-manual-orchestrator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", "replace")[:1000]
            raise OrchestrationError(
                f"GitHub API {method} {path} failed with HTTP {exc.code}: {message}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OrchestrationError(f"GitHub API connection failed: {exc.reason}") from exc
        if not raw:
            return {}
        value = json.loads(raw)
        require(isinstance(value, dict), "unexpected GitHub API response")
        return value

    def list_runs(self, source_sha: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "branch": "production",
                "event": "push",
                "head_sha": source_sha,
                "per_page": "100",
            }
        )
        payload = self.request("GET", f"actions/runs?{query}")
        runs = payload.get("workflow_runs")
        require(isinstance(runs, list), "workflow run collection missing")
        return [item for item in runs if isinstance(item, dict)]


def select_exact_run(
    runs: Iterable[dict[str, Any]], workflow_path: str, source_sha: str
) -> dict[str, Any] | None:
    require(workflow_path in ALLOWED_WORKFLOWS, "workflow is not allowlisted")
    require(bool(SHA40_RE.fullmatch(source_sha)), "invalid source SHA")
    candidates = [
        run
        for run in runs
        if run.get("path") == workflow_path
        and run.get("head_sha") == source_sha
        and run.get("head_branch") == "production"
        and run.get("event") == "push"
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda run: (
            int(run.get("id") or 0),
            int(run.get("run_attempt") or 0),
        ),
        reverse=True,
    )
    return candidates[0]


def validate_run(
    run: dict[str, Any],
    *,
    workflow_path: str,
    source_sha: str,
    require_success: bool,
) -> None:
    require(run.get("path") == workflow_path, "workflow path mismatch")
    require(run.get("head_sha") == source_sha, "workflow source SHA mismatch")
    require(run.get("head_branch") == "production", "workflow branch mismatch")
    require(run.get("event") == "push", "workflow event mismatch")
    require(isinstance(run.get("id"), int), "workflow run ID missing")
    require(int(run.get("run_attempt") or 0) >= 1, "workflow run attempt missing")
    if require_success:
        require(run.get("status") == "completed", "workflow is not completed")
        require(run.get("conclusion") == "success", "workflow did not succeed")


def wait_for_attempt_start(
    api: GitHubAPI, run_id: int, previous_attempt: int, deadline: float
) -> dict[str, Any]:
    while time.monotonic() < deadline:
        run = api.request("GET", f"actions/runs/{run_id}")
        attempt = int(run.get("run_attempt") or 0)
        if attempt > previous_attempt:
            return run
        time.sleep(3)
    raise OrchestrationError("rerun attempt did not start before timeout")


def wait_for_completion(
    api: GitHubAPI,
    run_id: int,
    *,
    deadline: float,
    cancel_on_timeout: bool,
) -> dict[str, Any]:
    while time.monotonic() < deadline:
        run = api.request("GET", f"actions/runs/{run_id}")
        if run.get("status") == "completed":
            return run
        time.sleep(15)
    if cancel_on_timeout:
        try:
            api.request("POST", f"actions/runs/{run_id}/cancel")
        except OrchestrationError:
            pass
    raise OrchestrationError("workflow run timed out and was cancelled fail-closed")


def orchestrate_child(
    *,
    repository: str,
    workflow_path: str,
    source_sha: str,
    policy: str,
    timeout_minutes: int,
    output_path: Path,
) -> dict[str, Any]:
    require(workflow_path in ALLOWED_WORKFLOWS, "workflow is not allowlisted")
    require(bool(SHA40_RE.fullmatch(source_sha)), "invalid source SHA")
    require(policy in {"reuse-success", "rerun-completed"}, "invalid run policy")
    require(5 <= timeout_minutes <= 360, "timeout must be between 5 and 360 minutes")
    token = os.environ.get("GITHUB_TOKEN", "")
    api = GitHubAPI(repository, token)
    run = select_exact_run(api.list_runs(source_sha), workflow_path, source_sha)
    require(run is not None, f"no production push run exists for {workflow_path}")

    deadline = time.monotonic() + timeout_minutes * 60
    validate_run(
        run,
        workflow_path=workflow_path,
        source_sha=source_sha,
        require_success=False,
    )

    status = str(run.get("status") or "")
    conclusion = run.get("conclusion")
    should_rerun = status == "completed" and (
        policy == "rerun-completed" or conclusion != "success"
    )
    reused_success = status == "completed" and conclusion == "success" and not should_rerun

    if should_rerun:
        previous_attempt = int(run.get("run_attempt") or 0)
        api.request("POST", f"actions/runs/{run['id']}/rerun")
        run = wait_for_attempt_start(api, int(run["id"]), previous_attempt, deadline)

    if not reused_success:
        run = wait_for_completion(
            api,
            int(run["id"]),
            deadline=deadline,
            # Never cancel an exact production-push run merely adopted by the
            # manual controller. Only a new rerun attempt started by this
            # controller is owned by this invocation.
            cancel_on_timeout=should_rerun,
        )

    validate_run(
        run,
        workflow_path=workflow_path,
        source_sha=source_sha,
        require_success=True,
    )
    safe = {
        "schema": "codestra.caddy.child-workflow-run.v1",
        "repository": repository,
        "workflow_path": workflow_path,
        "source_sha": source_sha,
        "run_id": int(run["id"]),
        "run_attempt": int(run["run_attempt"]),
        "status": run["status"],
        "conclusion": run["conclusion"],
        "head_branch": run["head_branch"],
        "event": run["event"],
        "html_url": run.get("html_url"),
        "policy": policy,
        "reused_success": reused_success,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    append_github_outputs(
        {
            "run_id": str(safe["run_id"]),
            "run_attempt": str(safe["run_attempt"]),
            "run_url": str(safe["html_url"] or ""),
        }
    )
    return safe


def verify_release_evidence(
    *,
    directory: Path,
    run_json: Path,
    source_sha: str,
    output_path: Path,
) -> dict[str, Any]:
    require(bool(SHA40_RE.fullmatch(source_sha)), "invalid source SHA")
    run = read_json(run_json)
    require(run.get("workflow_path") == ".github/workflows/immutable-release.yml", "wrong release workflow")
    require(run.get("source_sha") == source_sha, "release run SHA mismatch")
    require(run.get("conclusion") == "success", "release run is not successful")

    evidence_path = find_one(directory, "caddy-release-evidence.txt")
    values = parse_key_values(evidence_path)
    require(values.get("SOURCE_SHA") == source_sha, "release evidence SHA mismatch")
    digest = values.get("IMAGE_DIGEST", "")
    config_sha256 = values.get("CONFIG_SHA256", "")
    require(bool(DIGEST_RE.fullmatch(digest)), "invalid release image digest")
    require(bool(SHA256_RE.fullmatch(config_sha256)), "invalid release config SHA-256")
    for gate in PASS_RELEASE_GATES:
        require(values.get(gate) == "PASS", f"release gate did not pass: {gate}")

    config_path = find_one(directory, "config-sha256.txt")
    require(
        config_path.read_text(encoding="utf-8").strip() == config_sha256,
        "release config evidence mismatch",
    )
    image = f"ghcr.io/appolon1908-hue/codestra-caddy@{digest}"
    require(bool(IMAGE_RE.fullmatch(image)), "invalid immutable image identity")

    receipt = {
        "schema": "codestra.caddy.manual-release-evidence.v1",
        "source_sha": source_sha,
        "image": image,
        "image_digest": digest,
        "config_sha256": config_sha256,
        "release_run_id": int(run["run_id"]),
        "release_run_attempt": int(run["run_attempt"]),
        "release_evidence_tree_sha256": sha256_tree(directory),
        "gates": {gate: "PASS" for gate in sorted(PASS_RELEASE_GATES)},
        "result": "PASS",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    append_github_outputs(
        {
            "source_sha": source_sha,
            "image": image,
            "image_digest": digest,
            "config_sha256": config_sha256,
            "release_run_id": str(receipt["release_run_id"]),
            "release_run_attempt": str(receipt["release_run_attempt"]),
            "release_evidence_sha256": receipt["release_evidence_tree_sha256"],
        }
    )
    return receipt


def verify_runtime_evidence(
    *,
    staging_directory: Path,
    canary_directory: Path,
    run_json: Path,
    source_sha: str,
    image: str,
    config_sha256: str,
    output_path: Path,
) -> dict[str, Any]:
    require(bool(SHA40_RE.fullmatch(source_sha)), "invalid source SHA")
    require(bool(IMAGE_RE.fullmatch(image)), "invalid image identity")
    require(bool(SHA256_RE.fullmatch(config_sha256)), "invalid config SHA-256")
    run = read_json(run_json)
    require(
        run.get("workflow_path")
        == ".github/workflows/bounded-runtime-certification.yml",
        "wrong runtime workflow",
    )
    require(run.get("source_sha") == source_sha, "runtime run SHA mismatch")
    require(run.get("conclusion") == "success", "runtime run is not successful")

    staging_path = find_one(
        staging_directory, "bounded-staging-runtime-evidence.json"
    )
    staging = read_json(staging_path)
    require(
        staging.get("schema") == "codestra.caddy.bounded-staging-runtime.v2",
        "wrong staging evidence schema",
    )
    for key, expected in {
        "source_sha": source_sha,
        "image": image,
        "config_sha256": config_sha256,
        "runtime_config_sha256": config_sha256,
        "nonroot_readonly_runtime": "PASS",
        "tcp_80_443_udp_443": "PASS",
        "http2_http3_websocket": "PASS",
        "certificate_expiry": "PASS",
        "redirects_hsts_limits": "PASS",
        "editor_openbao_denial": "PASS",
        "mtls_handshake_and_denial": "PASS",
        "sanitized_logs": "PASS",
        "result": "PASS",
    }.items():
        require(staging.get(key) == expected, f"staging evidence mismatch: {key}")
    for key in (
        "isolated_network",
        "host_bindings_loopback_only",
        "candidate_removed",
    ):
        require(staging.get(key) is True, f"staging boolean gate failed: {key}")
    for key in (
        "public_traffic_changed",
        "dns_changed",
        "firewall_changed",
        "ssh_changed",
    ):
        require(staging.get(key) is False, f"staging mutation detected: {key}")

    canary_path = find_one(canary_directory, "production-canary-evidence.json")
    canary = read_json(canary_path)
    require(
        canary.get("schema") == "codestra.caddy.production-readonly-canary.v2",
        "wrong production canary evidence schema",
    )
    for key, expected in {
        "candidate_source_sha": source_sha,
        "candidate_image": image,
        "candidate_config_sha256": config_sha256,
        "candidate_signature_and_attestation": "PASS",
        "bounded_staging_runtime": "PASS",
        "candidate_offline_config_validation": "PASS",
        "live_container_validation_before": "PASS",
        "live_container_validation_after": "PASS",
        "live_redirect_hsts_certificate": "PASS",
        "live_http2_http3_websocket": "PASS",
        "live_editor_openbao_denial": "PASS",
        "live_mtls_handshake_and_denial": "PASS",
        "result": "PASS",
    }.items():
        require(canary.get(key) == expected, f"canary evidence mismatch: {key}")
    require(canary.get("live_runtime_unchanged") is True, "live runtime changed")
    for key in (
        "write_requests_sent",
        "candidate_started_on_production",
        "public_traffic_changed",
        "dns_changed",
        "firewall_changed",
        "ssh_changed",
    ):
        require(canary.get(key) is False, f"production mutation detected: {key}")

    pre_path = find_one(canary_directory, "pre-canary-runtime.json")
    post_path = find_one(canary_directory, "post-canary-runtime.json")
    pre_sha = sha256_file(pre_path)
    post_sha = sha256_file(post_path)
    require(pre_path.read_bytes() == post_path.read_bytes(), "runtime snapshots differ")
    require(
        canary.get("live_runtime_snapshot_before_sha256") == pre_sha,
        "pre-canary hash mismatch",
    )
    require(
        canary.get("live_runtime_snapshot_after_sha256") == post_sha,
        "post-canary hash mismatch",
    )

    staging_sha = sha256_file(staging_path)
    identity_path = find_one(canary_directory, "staging-evidence-identity.txt")
    identity = parse_key_values(identity_path)
    require(
        identity.get("STAGING_EVIDENCE_SHA256") == staging_sha,
        "staging evidence handoff hash mismatch",
    )

    receipt = {
        "schema": "codestra.caddy.manual-runtime-evidence.v1",
        "source_sha": source_sha,
        "image": image,
        "config_sha256": config_sha256,
        "runtime_run_id": int(run["run_id"]),
        "runtime_run_attempt": int(run["run_attempt"]),
        "bounded_staging_evidence_sha256": staging_sha,
        "bounded_staging_evidence_tree_sha256": sha256_tree(staging_directory),
        "production_canary_evidence_tree_sha256": sha256_tree(canary_directory),
        "pre_canary_runtime_sha256": pre_sha,
        "post_canary_runtime_sha256": post_sha,
        "live_runtime_unchanged": True,
        "write_requests_sent": False,
        "candidate_started_on_production": False,
        "public_traffic_changed": False,
        "result": "PASS",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    append_github_outputs(
        {
            "runtime_run_id": str(receipt["runtime_run_id"]),
            "runtime_run_attempt": str(receipt["runtime_run_attempt"]),
            "staging_evidence_sha256": staging_sha,
            "runtime_evidence_sha256": receipt[
                "production_canary_evidence_tree_sha256"
            ],
        }
    )
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    child = subparsers.add_parser("child-run")
    child.add_argument("--repository", required=True)
    child.add_argument("--workflow", required=True, choices=sorted(ALLOWED_WORKFLOWS))
    child.add_argument("--source-sha", required=True)
    child.add_argument(
        "--policy", required=True, choices=("reuse-success", "rerun-completed")
    )
    child.add_argument("--timeout-minutes", required=True, type=int)
    child.add_argument("--output", required=True, type=Path)

    release = subparsers.add_parser("verify-release")
    release.add_argument("--directory", required=True, type=Path)
    release.add_argument("--run-json", required=True, type=Path)
    release.add_argument("--source-sha", required=True)
    release.add_argument("--output", required=True, type=Path)

    runtime = subparsers.add_parser("verify-runtime")
    runtime.add_argument("--staging-directory", required=True, type=Path)
    runtime.add_argument("--canary-directory", required=True, type=Path)
    runtime.add_argument("--run-json", required=True, type=Path)
    runtime.add_argument("--source-sha", required=True)
    runtime.add_argument("--image", required=True)
    runtime.add_argument("--config-sha256", required=True)
    runtime.add_argument("--output", required=True, type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "child-run":
            orchestrate_child(
                repository=args.repository,
                workflow_path=args.workflow,
                source_sha=args.source_sha,
                policy=args.policy,
                timeout_minutes=args.timeout_minutes,
                output_path=args.output,
            )
        elif args.command == "verify-release":
            verify_release_evidence(
                directory=args.directory,
                run_json=args.run_json,
                source_sha=args.source_sha,
                output_path=args.output,
            )
        elif args.command == "verify-runtime":
            verify_runtime_evidence(
                staging_directory=args.staging_directory,
                canary_directory=args.canary_directory,
                run_json=args.run_json,
                source_sha=args.source_sha,
                image=args.image,
                config_sha256=args.config_sha256,
                output_path=args.output,
            )
        else:
            raise AssertionError(args.command)
    except (OrchestrationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CADDY_MANUAL_ORCHESTRATOR=NO_GO:{exc}", file=sys.stderr)
        return 2
    print("CADDY_MANUAL_ORCHESTRATOR=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
