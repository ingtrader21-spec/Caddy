#!/usr/bin/env python3
"""Validate the exact Caddy-to-Kong route ownership boundary."""

from __future__ import annotations

import re
from collections.abc import Iterable

KONG_MATCHER_RE = re.compile(r"(?m)^[ \t]*@kong[ \t]+path[ \t]+([^\r\n#]+?)\s*$")


def routed_kong_prefixes(site_source: str) -> tuple[str, ...]:
    """Return normalized prefixes from the sole named ``@kong path`` matcher."""
    matches = KONG_MATCHER_RE.findall(site_source)
    if len(matches) != 1:
        raise ValueError(f"kong_path_matcher_count:{len(matches)}")

    route_tokens = matches[0].split()
    if not route_tokens:
        raise ValueError("empty_kong_path_matcher")

    normalized: list[str] = []
    for token in route_tokens:
        if not token.startswith("/") or "*" in token[:-1]:
            raise ValueError(f"invalid_kong_route:{token}")
        prefix = token[:-1] if token.endswith("*") else token
        if not prefix or prefix == "/":
            raise ValueError(f"invalid_kong_route:{token}")
        normalized.append(prefix)

    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate_kong_route")
    return tuple(normalized)


def validate_exact_kong_routes(site_source: str, managed_paths: Iterable[str]) -> None:
    """Fail unless Caddy matcher routes and declared Kong paths are identical."""
    declared = tuple(managed_paths)
    if len(declared) != len(set(declared)):
        raise ValueError("duplicate_kong_managed_path")

    routed = set(routed_kong_prefixes(site_source))
    contracted = set(declared)
    uncontracted = sorted(routed - contracted)
    unrouted = sorted(contracted - routed)
    if uncontracted:
        raise ValueError(f"kong_route_not_contracted:{','.join(uncontracted)}")
    if unrouted:
        raise ValueError(f"kong_contract_not_routed:{','.join(unrouted)}")


TRUSTED_IDENTITY_HEADERS = (
    "X-Authenticated-Client",
    "X-Authenticated-Tenant",
    "X-Authenticated-Role",
    "X-Codestra-Gateway-Secret",
)
PRESERVED_EDGE_HEADERS = ("Authorization", "X-Correlation-ID", "Idempotency-Key", "traceparent", "tracestate")
HEADER_UP_RE = re.compile(r"(?m)^[ \t]*header_up[ \t]+(-?)([A-Za-z][A-Za-z0-9-]*)(?:[ \t]+([^\r\n#]*?))?[ \t]*$")


def header_up_directives(site_source: str) -> tuple[tuple[str, str], ...]:
    """Every ``header_up`` directive as (action, header): action is ``set`` or ``delete``."""
    return tuple(("delete" if minus else "set", name) for minus, name, _value in HEADER_UP_RE.findall(site_source))


def validate_identity_header_boundary(site_source: str, deleted_before_kong: Iterable[str]) -> None:
    """Caddy never sets a trusted identity header, deletes every contracted
    client-asserted one on the Kong handoff, and never touches the headers
    that must reach Kong and Middleware unchanged."""
    directives = header_up_directives(site_source)
    for action, name in directives:
        if action == "set" and name in TRUSTED_IDENTITY_HEADERS:
            raise ValueError(f"trusted_identity_header_set_by_caddy:{name}")
        if action == "delete" and name in PRESERVED_EDGE_HEADERS:
            raise ValueError(f"preserved_edge_header_deleted:{name}")
    for name in TRUSTED_IDENTITY_HEADERS:
        for line in site_source.splitlines():
            if name in line and line.strip() != f"header_up -{name}":
                raise ValueError(f"trusted_identity_header_in_caddy:{name}")
    deleted = {name for action, name in directives if action == "delete"}
    missing = sorted(set(deleted_before_kong) - deleted)
    if missing:
        raise ValueError(f"identity_header_not_deleted:{','.join(missing)}")
