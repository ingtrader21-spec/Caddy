#!/usr/bin/env python3
"""Validate the exact Caddy-to-Kong route ownership boundary."""
from __future__ import annotations
import re
from collections.abc import Iterable
KONG_MATCHER_RE = re.compile(r"(?m)^[ \t]*@kong[ \t]+path[ \t]+([^\r\n#]+?)\s*$")
def routed_kong_prefixes(site_source: str) -> tuple[str, ...]:
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
