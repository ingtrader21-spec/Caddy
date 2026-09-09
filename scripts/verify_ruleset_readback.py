#!/usr/bin/env python3
"""Compare every reviewed policy field with GitHub's ruleset readback."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


class PolicyMismatch(ValueError):
    """The live ruleset differs from the reviewed policy."""


def compare_policy(expected: Any, actual: Any, location: str = "policy") -> None:
    # GitHub adds response metadata and optional default parameters. Compare every
    # committed field, including false booleans and empty exclusions/bypass lists.
    if type(expected) is not type(actual):
        raise PolicyMismatch(f"{location}: type mismatch")
    if isinstance(expected, dict):
        for key, value in expected.items():
            if key not in actual:
                raise PolicyMismatch(f"{location}.{key}: missing")
            compare_policy(value, actual[key], f"{location}.{key}")
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            raise PolicyMismatch(f"{location}: item count mismatch")
        # Policy lists represent sets; GitHub may reorder rules, refs and checks.
        unmatched = list(actual)
        for item in expected:
            for index, candidate in enumerate(unmatched):
                try:
                    compare_policy(item, candidate, location)
                except PolicyMismatch:
                    continue
                unmatched.pop(index)
                break
            else:
                raise PolicyMismatch(f"{location}: item mismatch")
    elif expected != actual:
        raise PolicyMismatch(f"{location}: value mismatch")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PolicyMismatch("duplicate JSON key")
        value[key] = item
    return value


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_ruleset_readback.py REVIEWED_POLICY LIVE_READBACK", file=sys.stderr)
        return 2
    try:
        values = [json.loads(Path(p).read_text(), object_pairs_hook=unique_object)
                  for p in sys.argv[1:]]
        if not all(isinstance(value, dict) for value in values):
            raise PolicyMismatch("policy object required")
        compare_policy(*values)
    except (OSError, ValueError) as exc:
        # Do not echo API payloads, which may contain administrative metadata.
        reason = str(exc) if isinstance(exc, PolicyMismatch) else type(exc).__name__
        print(f"CADDY_BRANCH_RULESET_READBACK=FAIL:{reason}", file=sys.stderr)
        return 2
    print("CADDY_BRANCH_RULESET_READBACK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
