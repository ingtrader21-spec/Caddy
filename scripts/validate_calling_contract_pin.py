#!/usr/bin/env python3
"""Validate the pinned Codestra calling contract without enabling effects."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / ".codestra/calling-contract.lock.json"
EXPECTED = {
    "schema_version": "codestra.calling-contract-lock.v1",
    "version": "1.0.0",
    "sha256": "b39cdffe56a8185c91174228f0423df68b1137f34875f6ee52f9914f904bf724",
    "authority": "appolon1908-hue/codestra-production-platform#257",
    "role": "tls_edge",
    "external_effects_enabled": False,
}


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_document(text: str) -> object:
    return json.loads(text, object_pairs_hook=reject_duplicate_pairs)


def validate(document: object) -> None:
    if not isinstance(document, dict) or set(document) != set(EXPECTED):
        raise ValueError("calling contract lock schema mismatch")
    for field in ("schema_version", "version", "sha256", "authority", "role"):
        if type(document.get(field)) is not str or document[field] != EXPECTED[field]:
            raise ValueError(f"calling contract {field} mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", document["sha256"]):
        raise ValueError("calling contract digest malformed")
    if type(document.get("external_effects_enabled")) is not bool:
        raise ValueError("external_effects_enabled must be a JSON boolean")
    if document["external_effects_enabled"] is not False:
        raise ValueError("calling contract must remain fail closed")


def self_test() -> None:
    validate(copy.deepcopy(EXPECTED))
    invalid: list[object] = [
        None,
        [],
        {**EXPECTED, "external_effects_enabled": "false"},
        {**EXPECTED, "external_effects_enabled": 0},
        {**EXPECTED, "external_effects_enabled": None},
        {**EXPECTED, "external_effects_enabled": True},
        {key: value for key, value in EXPECTED.items() if key != "authority"},
        {**EXPECTED, "authority": "wrong/repository#1"},
        {**EXPECTED, "role": "wrong_role"},
        {**EXPECTED, "sha256": "0" * 64},
        {**EXPECTED, "unexpected": "field"},
    ]
    for number, document in enumerate(invalid, 1):
        try:
            validate(document)
        except ValueError:
            continue
        raise AssertionError(f"negative calling-contract fixture {number} accepted")

    duplicate_json = [
        '{"authority":"wrong","authority":"appolon1908-hue/codestra-production-platform#257"}',
        '{"role":"wrong_role","role":"tls_edge"}',
        '{"external_effects_enabled":true,"external_effects_enabled":false}',
    ]
    for number, text in enumerate(duplicate_json, 1):
        try:
            parse_document(text)
        except ValueError:
            continue
        raise AssertionError(f"duplicate-key JSON fixture {number} accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        validate(parse_document(LOCK.read_text(encoding="utf-8")))
    print("CALLING_CONTRACT_PIN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
