#!/usr/bin/env python3
"""Render Caddy's Middleware edge ownership from the vendored contract."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "config/middleware-public-api-route-contract.v1.json"
PINNED = ROOT / "config/middleware-public-api-route-contract.sha256"
EDGE = ROOT / "config/caddy-kong-contract.v1.json"
SITE = ROOT / "sites/api.codestra.co.caddy"
START = "\t\t# BEGIN GENERATED MIDDLEWARE CONTRACT ROUTES"
END = "\t\t# END GENERATED MIDDLEWARE CONTRACT ROUTES"
PUBLIC_ID = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"


def canonical_sha256(document: dict) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def route_regex(path: str) -> str:
    marker = "CODESTRAPARAMETER"
    marked = re.sub(r"\{[a-z_]+\}", marker, path)
    return re.escape(marked).replace(marker, PUBLIC_ID)


def route_block(routes: list[dict]) -> str:
    lines = [
        START,
        "\t\t# Generated from config/middleware-public-api-route-contract.v1.json.",
        "\t\t# Caddy selects exact method+path pairs; Kong owns authentication and policy.",
    ]
    for method in sorted({row["method"] for row in routes}):
        selected = sorted(route_regex(row["path"]) for row in routes if row["method"] == method)
        expression = "^(" + "|".join(selected) + ")$"
        matcher = f"canonical_{method.lower()}"
        lines.extend(
            [
                f"\t\t@{matcher} {{",
                f"\t\t\tmethod {method}",
                f"\t\t\tpath_regexp {expression}",
                "\t\t}",
                f"\t\thandle @{matcher} {{",
                "\t\t\treverse_proxy {$CADDY_KONG_UPSTREAM} {",
                "\t\t\t\theader_up Host {host}",
                "\t\t\t\theader_up X-Real-IP {remote_host}",
                "\t\t\t}",
                "\t\t}",
                "",
            ]
        )
    lines.append(END)
    return "\n".join(lines)


def render() -> tuple[str, str]:
    contract = json.loads(VENDORED.read_text(encoding="utf-8"))
    digest = canonical_sha256(contract)
    if PINNED.read_text(encoding="utf-8").strip() != digest:
        raise SystemExit("vendored contract does not match its pinned hash")
    shared = [row for row in contract["routes"] if row["classification"] == "shared_edge"]
    denied = [row for row in contract["routes"] if row["classification"] == "denied"]

    edge = json.loads(EDGE.read_text(encoding="utf-8"))
    edge["kongManagedPathPrefixes"] = sorted(
        (set(edge["kongManagedPathPrefixes"]) - {
            "/api/v1/integration/campaign-actions",
            "/api/v1/odoo/campaign-actions",
        })
        | {
            "/v2/automation",
            "/platform/v1",
            "/api/v1/odoo/events",
        }
    )
    service = edge["serviceJwtRouteContract"]
    service["sourceSchema"] = contract["schema"]
    service["sha256"] = digest
    service["routes"] = [
        {
            "method": row["method"],
            "path": row["path"],
            "scope": row["scope"],
            "audience": row["audience"],
            "callingClient": row["calling_client"],
            "matcher": f"canonical_{row['method'].lower()}",
        }
        for row in shared
    ]
    service["retiredPathPrefixes"] = sorted(
        {row["path"].split("/{", 1)[0] for row in denied}
    )

    site = SITE.read_text(encoding="utf-8")
    if START in site and END in site:
        before, rest = site.split(START, 1)
        _old, after = rest.split(END, 1)
        site = before + route_block(shared) + after
    else:
        marker = "\t\t# Service-JWT integration routes."
        retired = "\t\t# Retired campaign-control surfaces."
        before, rest = site.split(marker, 1)
        _old, after = rest.split(retired, 1)
        site = before + route_block(shared) + "\n\n" + retired + after
    if "@kong path /v2/automation*" not in site:
        site = site.replace(
            "@kong path ",
            "@kong path /v2/automation* /platform/v1* /api/v1/odoo/events* ",
            1,
        )
    return json.dumps(edge, indent=2) + "\n", site


def main() -> None:
    edge, site = render()
    EDGE.write_text(edge, encoding="utf-8")
    SITE.write_text(site, encoding="utf-8")


if __name__ == "__main__":
    main()
