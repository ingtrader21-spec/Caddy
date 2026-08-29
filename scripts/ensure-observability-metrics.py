#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_BEGIN = "# BEGIN CODESTRA OBSERVABILITY METRICS"
MARKER_END = "# END CODESTRA OBSERVABILITY METRICS"
LISTENER = f"""{MARKER_BEGIN}
:2020 {{
	metrics /metrics
	respond /healthz 200
}}
{MARKER_END}
"""


def global_block_bounds(text: str) -> tuple[int, int] | None:
    offset = len(text) - len(text.lstrip())
    if not text[offset:].startswith("{"):
        return None
    depth = 0
    for index in range(offset, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return offset, index
    raise SystemExit("BLOCKED: unterminated Caddy global options block")


def render(text: str) -> str:
    bounds = global_block_bounds(text)
    if bounds is None:
        text = "{\n\tadmin 127.0.0.1:2019\n\tmetrics\n}\n\n" + text.lstrip()
    else:
        start, end = bounds
        block = text[start : end + 1]
        admin_lines = re.findall(r"(?m)^\s*admin\s+([^\s#]+)", block)
        if admin_lines and any(value != "127.0.0.1:2019" for value in admin_lines):
            raise SystemExit("BLOCKED: Caddy admin endpoint must remain 127.0.0.1:2019")
        additions: list[str] = []
        if not admin_lines:
            additions.append("\tadmin 127.0.0.1:2019")
        if not re.search(r"(?m)^\s*metrics\s*(?:#.*)?$", block):
            additions.append("\tmetrics")
        if additions:
            text = text[:end] + "\n" + "\n".join(additions) + text[end:]

    if MARKER_BEGIN not in text:
        if re.search(r"(?m)^\s*:2020(?:\s|\{)", text):
            raise SystemExit("BLOCKED: port 2020 is already configured outside the Codestra metrics block")
        text = text.rstrip() + "\n\n" + LISTENER
    elif MARKER_END not in text:
        raise SystemExit("BLOCKED: incomplete Codestra observability metrics block")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = args.path.read_text(encoding="utf-8")
    updated = render(original)
    if args.check:
        if updated != original:
            raise SystemExit("BLOCKED: canonical Caddyfile is missing the Codestra observability patch")
        print("Caddy observability metrics contract passed")
        return 0
    args.path.write_text(updated, encoding="utf-8")
    print(f"Applied Codestra observability metrics contract to {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
