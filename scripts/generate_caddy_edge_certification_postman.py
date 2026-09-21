#!/usr/bin/env python3
"""Generate PAS-145 Caddy edge-certification Postman artifacts deterministically.

The collection is a test surface, not edge authority. It is derived from the
checked-in public-edge and webhook registries and defaults to a loopback target
with live execution disabled.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = ROOT / "config" / "public-edge-registry.v1.json"
WEBHOOK_PATH = ROOT / "config" / "webhook-edge-registry.v1.json"
COLLECTION_PATH = ROOT / "postman" / "Caddy-V3-Edge-Certification.postman_collection.json"
ENV_PATH = ROOT / "postman" / "Caddy-V3-Edge-Certification.postman_environment.json"


class GenerationError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GenerationError(f"{path} must contain a JSON object")
    return value


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_event(script: str) -> dict[str, Any]:
    return {
        "listen": "test",
        "script": {"type": "text/javascript", "exec": [script]},
    }


def request_item(
    name: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    idempotency: bool = False,
    body: str | None = None,
    tests: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    headers: list[dict[str, str]] = [
        {"key": "X-Correlation-ID", "value": "{{correlation_id}}", "type": "text"}
    ]
    if token is not None:
        headers.insert(
            0,
            {"key": "Authorization", "value": f"Bearer {{{{{token}}}}}", "type": "text"},
        )
    if idempotency:
        headers.append(
            {"key": "Idempotency-Key", "value": "{{idempotency_key}}", "type": "text"}
        )
    if body is not None:
        headers.append({"key": "Content-Type", "value": "application/json", "type": "text"})

    request: dict[str, Any] = {
        "method": method,
        "header": headers,
        "url": "{{base_url}}" + path,
    }
    if description:
        request["description"] = description
    if body is not None:
        request["body"] = {
            "mode": "raw",
            "raw": body,
            "options": {"raw": {"language": "json"}},
        }

    item: dict[str, Any] = {"name": name, "request": request}
    if tests:
        item["event"] = [test_event(script) for script in tests]
    return item


def private_items(public: dict[str, Any]) -> list[dict[str, Any]]:
    private = {
        row["path"]: row
        for row in public.get("entries", [])
        if row.get("classification") == "PRIVATE"
    }
    required = ["/metrics*", "/internal/*"]
    if not all(path in private for path in required):
        raise GenerationError("private edge registry is incomplete")
    probes = [
        ("metrics-root", "/metrics"),
        ("metrics-subpath", "/metrics/runtime"),
        ("internal-auth", "/internal/v1/authorization/check"),
        ("internal-db", "/internal/v1/database/health"),
    ]
    return [
        request_item(
            name,
            "GET",
            path,
            tests=["pm.test('public edge returns 404', () => pm.response.to.have.status(404));"],
        )
        for name, path in probes
    ]


def pending_items(public: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in public.get("entries", [])
        if row.get("classification") == "DENIED_PENDING_CONTRACT"
    ]
    if not rows:
        raise GenerationError("pending-contract denial registry is empty")
    items: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda value: str(value.get("id"))):
        path = str(row["path"]).replace("*", "TEST_SYN")
        method = str(row.get("method_class") or "POST").upper()
        items.append(
            request_item(
                str(row["id"]),
                method,
                path,
                body="{}" if method in {"POST", "PUT", "PATCH", "DELETE"} else None,
                tests=["pm.test('pending contract is fail-closed', () => pm.response.to.have.status(404));"],
            )
        )
    return items


def webhook_wrong_method_items(webhooks: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in sorted(webhooks.get("entries", []), key=lambda value: str(value.get("id"))):
        methods = [str(value).upper() for value in row.get("methods", [])]
        if methods != ["POST"]:
            raise GenerationError(f"webhook method drift: {row.get('id')}")
        path = str(row["path"]).replace("*", "TEST_SYN")
        items.append(
            request_item(
                f"{row['id']}-wrong-method",
                "GET",
                path,
                tests=[
                    "pm.test('wrong webhook method fails closed', () => pm.expect([404,405]).to.include(pm.response.code));"
                ],
            )
        )
    return items


def render_collection(public: dict[str, Any], webhooks: dict[str, Any]) -> dict[str, Any]:
    api_items = [
        request_item(
            "platform-kernel-describe",
            "GET",
            "/platform/v1/kernel/describe",
            token="access_token",
            description="Positive transport probe; requires a valid token when executed.",
        ),
        request_item(
            "platform-command-submit",
            "POST",
            "/platform/v1/commands",
            token="access_token",
            idempotency=True,
            body="{{command_body}}",
            description="Positive transport probe; payload/business semantics remain Middleware-owned.",
        ),
        request_item(
            "automation-command-submit",
            "POST",
            "/v2/automation/commands",
            token="automation_token",
            idempotency=True,
            body="{{automation_command_body}}",
        ),
        request_item(
            "odoo-event-ingress",
            "POST",
            "/api/v1/odoo/events",
            token="odoo_token",
            idempotency=True,
            body="{{odoo_event_body}}",
        ),
        request_item(
            "n8n-result-ingress",
            "POST",
            "/api/v1/integrations/n8n/results",
            token="n8n_token",
            idempotency=True,
            body="{{n8n_result_body}}",
        ),
    ]
    wrong_method_items = [
        request_item(
            "platform-command-wrong-method",
            "DELETE",
            "/platform/v1/commands",
            token="access_token",
            tests=[
                "pm.test('wrong API method fails closed', () => pm.expect([404,405]).to.include(pm.response.code));"
            ],
        ),
        request_item(
            "operation-replay-wrong-method",
            "PUT",
            "/platform/v1/operations/{{operation_id}}/replay",
            token="access_token",
            tests=[
                "pm.test('wrong API method fails closed', () => pm.expect([404,405]).to.include(pm.response.code));"
            ],
        ),
        request_item(
            "odoo-event-wrong-method",
            "GET",
            "/api/v1/odoo/events",
            token="odoo_token",
            tests=[
                "pm.test('wrong ingress method fails closed', () => pm.expect([404,405]).to.include(pm.response.code));"
            ],
        ),
        request_item(
            "n8n-result-wrong-method",
            "GET",
            "/api/v1/integrations/n8n/results",
            token="n8n_token",
            tests=[
                "pm.test('wrong ingress method fails closed', () => pm.expect([404,405]).to.include(pm.response.code));"
            ],
        ),
    ]

    guard = {
        "listen": "prerequest",
        "script": {
            "type": "text/javascript",
            "exec": [
                "if (pm.environment.get('RUN_CADDY_EDGE_CERTIFICATION') !== 'true') {",
                "  throw new Error('Live Caddy edge certification is disabled. Select an isolated candidate environment and set RUN_CADDY_EDGE_CERTIFICATION=true explicitly.');",
                "}",
            ],
        },
    }
    return {
        "info": {
            "_postman_id": "caddy-pas145-edge-certification-v1",
            "name": "Caddy V3 Edge Certification",
            "description": (
                "PAS-145 edge/API/private/webhook probes. Caddy owns transport only; "
                "Kong owns API identity/policy and Middleware owns business semantics."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": [guard],
        "item": [
            {"name": "API Transport", "item": api_items},
            {"name": "Wrong Method", "item": wrong_method_items},
            {"name": "Private Route Denial", "item": private_items(public)},
            {"name": "Pending Contract Denial", "item": pending_items(public)},
            {"name": "Webhook Wrong Method", "item": webhook_wrong_method_items(webhooks)},
        ],
    }


def render_environment() -> dict[str, Any]:
    values = [
        ("base_url", "https://127.0.0.1:9443"),
        ("RUN_CADDY_EDGE_CERTIFICATION", "false"),
        ("access_token", ""),
        ("automation_token", ""),
        ("odoo_token", ""),
        ("n8n_token", ""),
        ("correlation_id", "TEST_SYN-caddy-edge"),
        ("idempotency_key", "TEST_SYN-caddy-idem-0001"),
        ("operation_id", "OP-TEST-SYN-0001"),
        ("command_body", "{}"),
        ("automation_command_body", "{}"),
        ("odoo_event_body", "{}"),
        ("n8n_result_body", "{}"),
    ]
    return {
        "id": "caddy-pas145-safe-local-env-v1",
        "name": "Caddy V3 Edge Certification - Safe Local",
        "values": [
            {"key": key, "value": value, "enabled": True}
            for key, value in values
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_using": "Codestra PAS-145 deterministic generator",
    }


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(value), encoding="utf-8", newline="\n")


def check(path: Path, value: Any) -> None:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current.replace("\r\n", "\n") != dump(value):
        raise GenerationError(f"generated artifact is stale: {path.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        public = load_json(PUBLIC_PATH)
        webhooks = load_json(WEBHOOK_PATH)
        collection = render_collection(public, webhooks)
        environment = render_environment()
        if args.write:
            write(COLLECTION_PATH, collection)
            write(ENV_PATH, environment)
        if args.check:
            check(COLLECTION_PATH, collection)
            check(ENV_PATH, environment)
    except GenerationError as exc:
        print("CADDY_POSTMAN_GENERATION=FAIL")
        print(f"ERROR={exc}")
        return 1

    print("CADDY_POSTMAN_GENERATION=PASS")
    print(f"COLLECTION={COLLECTION_PATH.relative_to(ROOT).as_posix()}")
    print(f"ENVIRONMENT={ENV_PATH.relative_to(ROOT).as_posix()}")
    print("LIVE_RUN_DEFAULT=FALSE")
    print("DEFAULT_BASE_URL=https://127.0.0.1:9443")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
