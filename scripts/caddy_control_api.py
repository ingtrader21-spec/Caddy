#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from caddy_runtime import CaddyRuntime, RuntimeApplyError, RuntimePaths
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

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8784


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ControlService:
    def __init__(
        self,
        authority_path: Path = DEFAULT_AUTHORITY,
        output_path: Path = DEFAULT_OUTPUT,
        inventory_path: Path = DEFAULT_INVENTORY,
        runtime: CaddyRuntime | None = None,
    ) -> None:
        self.authority_path = authority_path
        self.output_path = output_path
        self.inventory_path = inventory_path
        self.runtime = runtime
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
        import hashlib
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

    def runtime_status(self) -> dict[str, Any]:
        if self.runtime is None:
            return {"schema": "codestra.caddy.runtime-status.v1", "configured": False}
        return {"schema": "codestra.caddy.runtime-status.v1", "configured": True, **self.runtime.readback()}

    def apply(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.runtime is None:
            raise RuntimeApplyError("runtime_not_configured")
        with self._lock:
            compile_to_files(self.authority_path, self.output_path, self.inventory_path, check=False)
            return self.runtime.apply(
                self.output_path,
                source_sha=str(request.get("source_sha", "")),
                candidate_digest=str(request.get("candidate_digest", "")),
                expected_active_digest=request.get("expected_active_digest"),
                idempotency_key=request.get("idempotency_key"),
            )

    def rollback(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.runtime is None:
            raise RuntimeApplyError("runtime_not_configured")
        return self.runtime.rollback(expected_active_digest=request.get("expected_active_digest"))

    def history(self) -> dict[str, Any]:
        if self.runtime is None:
            return {"schema": "codestra.caddy.execution-history.v1", "executions": []}
        return {"schema": "codestra.caddy.execution-history.v1", "executions": self.runtime.history()}


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
        except RuntimeApplyError as exc:
            self._send(409, {"ok": False, "error": {"code": "runtime_apply_failed", "message": str(exc)}}, request_id)
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
        if path == "/platform/v1/caddy/executions":
            return self._run(self.service.history)
        if path == "/health":
            return self._run(lambda: {"service": "caddy-control-api", "status": "ok"})
        request_id = self._request_id()
        self._send(404, {"ok": False, "error": {"code": "not_found", "message": "route not found"}}, request_id)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 65536:
            request_id = self._request_id()
            return self._send(413, {"ok": False, "error": {"code": "payload_too_large", "message": "request body exceeds limit"}}, request_id)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(request, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            request_id = self._request_id()
            return self._send(400, {"ok": False, "error": {"code": "invalid_json", "message": "JSON object required"}}, request_id)
        if path == "/platform/v1/caddy/config/compile":
            return self._run(self.service.compile)
        if path == "/platform/v1/caddy/config/validate":
            return self._run(self.service.validate)
        if path == "/platform/v1/caddy/config/apply":
            return self._run(lambda: self.service.apply(request))
        if path == "/platform/v1/caddy/config/rollback":
            return self._run(lambda: self.service.rollback(request))
        request_id = self._request_id()
        self._send(404, {"ok": False, "error": {"code": "not_found", "message": "route not found"}}, request_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Private Caddy PAS-144 control API.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--live-config")
    parser.add_argument("--state-dir")
    parser.add_argument("--health-url", action="append", default=[])
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("refusing non-loopback bind")
    if bool(args.live_config) != bool(args.state_dir):
        raise SystemExit("--live-config and --state-dir must be supplied together")
    if args.live_config:
        Handler.service = ControlService(runtime=CaddyRuntime(
            RuntimePaths(Path(args.live_config), Path(args.state_dir)),
            health_urls=tuple(args.health_url),
        ))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
