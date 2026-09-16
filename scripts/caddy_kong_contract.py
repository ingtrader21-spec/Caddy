#!/usr/bin/env python3
"""Validate the exact Caddy-to-Kong route ownership boundary."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping

KONG_MATCHER_RE = re.compile(r"(?m)^[ \t]*@kong[ \t]+path[ \t]+([^\r\n#]+?)\s*$")
SINGLE_LINE_MATCHER_RE = re.compile(r"^@([A-Za-z0-9_]+)\s+(path|path_regexp|method)\s+(.+)$")
BLOCK_MATCHER_RE = re.compile(r"^@([A-Za-z0-9_]+)\s*\{$")
BLOCK_MATCHER_LINE_RE = re.compile(r"^(path|path_regexp|method)\s+(.+)$")
HANDLE_RE = re.compile(r"^handle(?:\s+@([A-Za-z0-9_]+))?\s*\{$")
REVERSE_PROXY_RE = re.compile(r"^reverse_proxy\s+\{\$([A-Za-z0-9_]+)\}")
PATH_PARAMETER_RE = re.compile(r"\{[a-z_]+\}")
KONG_UPSTREAM = "CADDY_KONG_UPSTREAM"
LEGACY_UPSTREAM = "CADDY_LEGACY_API_UPSTREAM"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Probe values for path parameters; any public id shape works because the
# Caddy matchers are prefix based, never parameter aware.
PROBE_IDS = {"{campaign_id}": "TEST_SYN", "{event_id}": "EVT-PROBE"}
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


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


def parse_site_routing(
    site_source: str,
) -> tuple[dict[str, dict[str, list[str]]], list[tuple[str | None, str | None]]]:
    """Named matchers and ordered ``handle`` blocks of one site block.

    Returns ``({matcher: {"path": [...], "method": [...]}}, [(matcher, upstream)])``
    where ``matcher`` is ``None`` for the unconditional fallback ``handle {`` and
    ``upstream`` is the ``{$VAR}`` dialed by the block's ``reverse_proxy`` (or
    ``None`` when the block proxies nowhere).
    """
    matchers: dict[str, dict[str, list[str]]] = {}
    handles: list[list[str | None]] = []
    block: str | None = None
    for raw in site_source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if block is not None:
            if line == "}":
                block = None
                continue
            inline = BLOCK_MATCHER_LINE_RE.match(line)
            if inline:
                matchers[block].setdefault(inline.group(1), []).extend(inline.group(2).split())
            continue
        single = SINGLE_LINE_MATCHER_RE.match(line)
        if single:
            matchers.setdefault(single.group(1), {}).setdefault(single.group(2), []).extend(
                single.group(3).split()
            )
            continue
        opened = BLOCK_MATCHER_RE.match(line)
        if opened:
            block = opened.group(1)
            matchers.setdefault(block, {})
            continue
        handle = HANDLE_RE.match(line)
        if handle:
            handles.append([handle.group(1), None])
            continue
        proxy = REVERSE_PROXY_RE.match(line)
        if proxy and handles and handles[-1][1] is None:
            handles[-1][1] = proxy.group(1)
    return matchers, [(name, upstream) for name, upstream in handles]


def _path_matches(tokens: Iterable[str], path: str) -> bool:
    for token in tokens:
        if token.endswith("*"):
            if path.startswith(token[:-1]):
                return True
        elif path == token:
            return True
    return False


def _path_regexp_matches(patterns: Iterable[str], path: str) -> bool:
    return any(re.search(pattern, path) is not None for pattern in patterns)


def resolve_request(site_source: str, method: str, path: str) -> tuple[str | None, str | None, bool]:
    """``(upstream, matcher, matcher_declares_method)`` for one request.

    Walks the ``handle`` blocks in source order exactly as Caddy's ``route``
    directive does and stops at the first matcher the request satisfies.
    """
    matchers, handles = parse_site_routing(site_source)
    for name, upstream in handles:
        if name is None:
            return upstream, None, False
        matcher = matchers.get(name, {})
        paths = matcher.get("path")
        path_regexps = matcher.get("path_regexp")
        methods = matcher.get("method")
        if paths and not _path_matches(paths, path):
            continue
        if path_regexps and not _path_regexp_matches(path_regexps, path):
            continue
        if methods and method.upper() not in {value.upper() for value in methods}:
            continue
        return upstream, name, bool(methods)
    return None, None, False


def concrete_path(template: str) -> str:
    for placeholder, value in PROBE_IDS.items():
        template = template.replace(placeholder, value)
    return PATH_PARAMETER_RE.sub("PROBE-1", template)


def contract_sha256(document: Mapping[str, object]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_contract_hash(pinned_digest: object, document: Mapping[str, object]) -> None:
    if not isinstance(pinned_digest, str) or not SHA256_RE.fullmatch(pinned_digest):
        raise ValueError("service_jwt_contract_hash_missing")
    actual = contract_sha256(document)
    if actual != pinned_digest:
        raise ValueError(f"service_jwt_contract_hash_mismatch:{actual}")


def validate_service_jwt_routes(site_source: str, contract: Mapping[str, object]) -> None:
    """Fail unless every service-JWT route is method-exact and Kong-bound.

    ``contract`` is the ``serviceJwtRouteContract`` object. Every route must
    reach ``CADDY_KONG_UPSTREAM`` through a matcher that declares its HTTP
    method; unsupported methods and retired paths must never reach the legacy
    fallback; and every Kong handle must precede the fallback.
    """
    digest = contract.get("sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ValueError("service_jwt_contract_hash_missing")
    routes = contract.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("service_jwt_routes_missing")
    allowed_by_path: dict[str, set[str]] = {}
    for route in routes:
        allowed_by_path.setdefault(str(route["path"]), set()).add(str(route["method"]).upper())
    for route in routes:
        method = str(route["method"]).upper()
        path = concrete_path(str(route["path"]))
        upstream, matcher, declares_method = resolve_request(site_source, method, path)
        label = f"{method} {route['path']}"
        if upstream != KONG_UPSTREAM:
            raise ValueError(f"service_jwt_route_not_kong:{label}")
        if not declares_method:
            raise ValueError(f"service_jwt_matcher_without_method:{label}")
        if route.get("matcher") and matcher != route["matcher"]:
            raise ValueError(f"service_jwt_matcher_mismatch:{label}:{matcher}")
        for wrong in HTTP_METHODS:
            if wrong in allowed_by_path[str(route["path"] )]:
                continue
            wrong_upstream, _matcher, _declares = resolve_request(site_source, wrong, path)
            if wrong_upstream in (LEGACY_UPSTREAM, None):
                raise ValueError(f"unsupported_method_reaches_legacy:{wrong} {route['path']}")
    for prefix in contract.get("retiredPathPrefixes") or ():
        for method in ("GET", "POST"):
            upstream, _matcher, _declares = resolve_request(site_source, method, f"{prefix}")
            if upstream in (LEGACY_UPSTREAM, None):
                raise ValueError(f"retired_path_reaches_legacy:{method} {prefix}")
    _matchers, handles = parse_site_routing(site_source)
    kong_positions = [i for i, (name, upstream) in enumerate(handles) if name and upstream == KONG_UPSTREAM]
    fallback_positions = [i for i, (name, _upstream) in enumerate(handles) if name is None]
    if not kong_positions:
        raise ValueError("kong_handle_missing")
    if fallback_positions and max(kong_positions) > min(fallback_positions):
        raise ValueError("kong_handle_after_legacy_fallback")
