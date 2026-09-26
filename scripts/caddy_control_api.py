#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from caddy_activation import ActivationError, ActivationManager
from caddy_candidate import CandidateBuildError, CandidateBuilder
from caddy_execution_store import ExecutionStore, ExecutionStoreError
from caddy_route_compiler import (
    DEFAULT_AUTHORITY,
    DEFAULT_INVENTORY,
    DEFAULT_OUTPUT,
    RouteAuthorityError,
    compile_caddy,
    compile_to_files,
    load_authority,
    normalize_routes,
)
from caddy_runtime_readback import CaddyRuntime, RuntimeReadbackError, canonical_json, sha256_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8784
DEFAULT_ADMIN_API = os.environ.get("CADDY_ADMIN_API", "http://127.0.0.1:2019")
DEFAULT_CANDIDATE_JSON = Path(
    os.environ.get("CADDY_RUNTIME_CANDIDATE_JSON", str(ROOT / "generated" / "pas144-runtime-candidate.json"))
)
DEFAULT_EVIDENCE_DIR = Path(
    os.environ.get(
        "CADDY_CONTROL_EVIDENCE_DIR",
        str(Path.home() / ".local" / "state" / "codestra-caddy-control" / "executions"),
    )
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ControlService:
    def __init__(
        self,
        authority_path: Path = DEFAULT_AUTHORITY,
        output_path: Path = DEFAULT_OUTPUT,
        inventory_path: Path = DEFAULT_INVENTORY,
        *,
        runtime: CaddyRuntime | None = None,
        store: ExecutionStore | None = None,
        candidate_path: Path = DEFAULT_CANDIDATE_JSON,
        mutation_enabled: bool | None = None,
        candidate_builder: CandidateBuilder | None = None,
    ) -> None:
        self.authority_path = authority_path
        self.output_path = output_path
        self.inventory_path = inventory_path
        self.runtime = runtime or CaddyRuntime(DEFAULT_ADMIN_API)
        self.store = store or ExecutionStore(DEFAULT_EVIDENCE_DIR)
        self.activation = ActivationManager(
            runtime=self.runtime,
            store=self.store,
            candidate_path=candidate_path,
            mutation_enabled=mutation_enabled,
        )
        self.candidate_builder = candidate_builder or CandidateBuilder(output=candidate_path)
        self.candidate_path = candidate_path
        self._lock = threading.Lock()

    def routes(self) -> dict[str, Any]:
        authority = load_authority(self.authority_path)
        return {
            "schema": "codestra.caddy.routes.readback.v1",
            "routes": [
                {
                    "route_id": r.route_id,
                    "host": r.host,
                    "path": r.path,
                    "methods": list(r.methods),
                    "visibility": r.visibility,
                    "upstream_service": r.upstream_service,
                    "upstream_ref": r.upstream_ref,
                    "owner": r.owner,
                }
                for r in normalize_routes(authority)
            ],
        }

    def digest(self) -> dict[str, Any]:
        authority = load_authority(self.authority_path)
        generated = compile_caddy(authority)
        canonical = json.dumps(authority, sort_keys=True, separators=(",", ":")).encode()
        return {
            "schema": "codestra.caddy.config-digest.v1",
            "authority_sha256": hashlib.sha256(canonical).hexdigest(),
            "compiled_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        }

    def status(self) -> dict[str, Any]:
        try:
            compile_to_files(self.authority_path, self.output_path, self.inventory_path, check=True)
            drift = False
            error = None
        except RouteAuthorityError as exc:
            drift = True
            error = str(exc)
        return {
            "schema": "codestra.caddy.config-status.v1",
            "drift": drift,
            "error": error,
            "runtime_reload_performed": False,
        }

    def compile(self) -> dict[str, Any]:
        with self._lock:
            inventory = compile_to_files(self.authority_path, self.output_path, self.inventory_path, check=False)
        return {
            "schema": "codestra.caddy.compile-result.v1",
            "compiled": True,
            "runtime_reload_performed": False,
            "inventory": inventory,
        }

    def validate(self) -> dict[str, Any]:
        authority = load_authority(self.authority_path)
        generated = compile_caddy(authority)
        return {
            "schema": "codestra.caddy.validate-result.v1",
            "valid": True,
            "generated_bytes": len(generated.encode("utf-8")),
            "route_count": len(normalize_routes(authority)),
            "runtime_reload_performed": False,
        }

    def build_runtime_candidate(self) -> dict[str, Any]:
        return self.candidate_builder.build(check=False)

    def runtime_status(self) -> dict[str, Any]:
        return self.runtime.status()

    def runtime_routes(self) -> dict[str, Any]:
        inventory = self.runtime.inventory()
        return {
            "schema": "codestra.caddy.runtime-routes.v1",
            "hosts": inventory["hosts"],
            "paths": inventory["paths"],
        }

    def runtime_upstreams(self) -> dict[str, Any]:
        inventory = self.runtime.inventory()
        return {
            "schema": "codestra.caddy.runtime-upstreams.v1",
            "upstreams": inventory["upstreams"],
        }

    def drift(self) -> dict[str, Any]:
        if not self.candidate_path.exists():
            return {
                "schema": "codestra.caddy.runtime-drift.v1",
                "state": "UNKNOWN",
                "reason": "CANDIDATE_MISSING",
            }
        try:
            candidate = json.loads(self.candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "schema": "codestra.caddy.runtime-drift.v1",
                "state": "UNKNOWN",
                "reason": "CANDIDATE_INVALID",
            }
        live = self.runtime.config()
        state = "IN_SYNC" if canonical_json(live) == canonical_json(candidate) else "DRIFTED"
        return {
            "schema": "codestra.caddy.runtime-drift.v1",
            "state": state,
            "candidate_sha256": sha256_json(candidate),
            "runtime_sha256": sha256_json(live),
        }

    def activation_dry_run(self) -> dict[str, Any]:
        return self.activation.dry_run()

    def activation_apply(self, idempotency_key: str) -> dict[str, Any]:
        return self.activation.apply(idempotency_key=idempotency_key)

    def activation_rollback(self, execution_id: str) -> dict[str, Any]:
        return self.activation.rollback(execution_id)

    def execution(self, execution_id: str) -> dict[str, Any]:
        return self.store.get(execution_id)

    def health(self) -> dict[str, Any]:
        return {
            "service": "caddy-control-api",
            "status": "ok",
            "mutation_enabled": self.activation.mutation_enabled,
        }


class Handler(BaseHTTPRequestHandler):
    service = ControlService()

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _request_id(self) -> str:
        supplied = (self.headers.get("X-Correlation-ID") or "").strip()
        return supplied[:128] if supplied else str(uuid.uuid4())

    def _send(self, status: int, body: dict[str, Any], request_id: str) -> None:
        payload = _json_bytes(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Correlation-ID", request_id)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _run(self, fn) -> None:
        request_id = self._request_id()
        try:
            result = fn()
        except RouteAuthorityError as exc:
            self._send(409, {"ok": False, "error": {"code": "route_authority_invalid", "message": str(exc)}}, request_id)
            return
        except ActivationError as exc:
            status = 403 if exc.code == "ACTIVATION_DISABLED" else 409
            self._send(status, {"ok": False, "error": {"code": exc.code, "message": str(exc)}}, request_id)
            return
        except CandidateBuildError as exc:
            self._send(409, {"ok": False, "error": {"code": "candidate_build_failed", "message": str(exc)}}, request_id)
            return
        except ExecutionStoreError as exc:
            status = 404 if str(exc) == "execution_not_found" else 409
            self._send(status, {"ok": False, "error": {"code": str(exc), "message": str(exc)}}, request_id)
            return
        except RuntimeReadbackError as exc:
            status = exc.status if exc.status and 400 <= exc.status < 600 else 503
            self._send(status, {"ok": False, "error": {"code": exc.code, "message": str(exc)}}, request_id)
            return
        except Exception:
            self._send(500, {"ok": False, "error": {"code": "internal_error", "message": "control operation failed"}}, request_id)
            return
        self._send(200, {"ok": True, **result}, request_id)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/platform/v1/caddy/routes":
            return self._run(self.service.routes)
        if path == "/platform/v1/caddy/config/digest":
            return self._run(self.service.digest)
        if path == "/platform/v1/caddy/config/status":
            return self._run(self.service.status)
        if path == "/platform/v1/caddy/runtime/status":
            return self._run(self.service.runtime_status)
        if path == "/platform/v1/caddy/runtime/routes":
            return self._run(self.service.runtime_routes)
        if path == "/platform/v1/caddy/runtime/upstreams":
            return self._run(self.service.runtime_upstreams)
        if path == "/platform/v1/caddy/drift":
            return self._run(self.service.drift)
        prefix = "/platform/v1/caddy/activation/executions/"
        if path.startswith(prefix):
            execution_id = path[len(prefix):].split("/", 1)[0]
            return self._run(lambda: {"execution": self.service.execution(execution_id)})
        if path in {"/platform/v1/caddy/health", "/health"}:
            return self._run(self.service.health)
        request_id = self._request_id()
        self._send(404, {"ok": False, "error": {"code": "not_found", "message": "route not found"}}, request_id)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if int(self.headers.get("Content-Length", "0") or 0) > 65536:
            request_id = self._request_id()
            return self._send(413, {"ok": False, "error": {"code": "payload_too_large", "message": "request body exceeds limit"}}, request_id)
        if path == "/platform/v1/caddy/config/compile":
            return self._run(self.service.compile)
        if path == "/platform/v1/caddy/config/validate":
            return self._run(self.service.validate)
        if path == "/platform/v1/caddy/activation/candidate":
            return self._run(self.service.build_runtime_candidate)
        if path == "/platform/v1/caddy/activation/dry-run":
            return self._run(self.service.activation_dry_run)
        if path == "/platform/v1/caddy/activation/apply":
            key = (self.headers.get("Idempotency-Key") or "").strip()
            return self._run(lambda: {"execution": self.service.activation_apply(key)})
        prefix = "/platform/v1/caddy/activation/executions/"
        if path.startswith(prefix) and path.endswith("/rollback"):
            execution_id = path[len(prefix):-len("/rollback")].rstrip("/")
            return self._run(lambda: {"execution": self.service.activation_rollback(execution_id)})
        request_id = self._request_id()
        self._send(404, {"ok": False, "error": {"code": "not_found", "message": "route not found"}}, request_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Private Caddy control API.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("refusing non-loopback bind")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
