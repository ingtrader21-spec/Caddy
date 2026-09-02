#!/usr/bin/env python3
"""Fail closed unless a verified cosign attestation binds the exact Caddy tuple."""

import base64
import json
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"BLOCKED: {message}")


if len(sys.argv) != 5:
    fail("attestation verifier requires file, digest, repository, and revision")

path, expected_digest, expected_repository, expected_revision = sys.argv[1:]
if re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
    fail("expected image digest is malformed")
if re.fullmatch(r"[0-9a-f]{40}", expected_revision) is None:
    fail("expected source revision is malformed")

try:
    raw = open(path, encoding="utf-8").read().strip()
    records = json.loads(raw)
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    fail(f"verified attestation output is unreadable: {error}")

if isinstance(records, dict):
    records = [records]
if not isinstance(records, list) or len(records) != 1:
    fail("exactly one verified source attestation is required")

try:
    envelope = records[0]
    payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
    subjects = payload["subject"]
    predicate = payload["predicate"]
except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
    fail(f"verified attestation payload is malformed: {error}")

if len(subjects) != 1 or subjects[0].get("digest", {}).get("sha256") != expected_digest:
    fail("attestation subject does not match the requested image digest")
expected_workflow = (
    "https://github.com/appolon1908-hue/Caddy/"
    ".github/workflows/immutable-release.yml@refs/heads/production"
)
required = {
    "repository": expected_repository,
    "revision": expected_revision,
    "workflow_identity": expected_workflow,
    "release_identity": expected_revision,
}
if not isinstance(predicate, dict) or any(predicate.get(k) != v for k, v in required.items()):
    fail("attested repository, revision, workflow, or release identity does not match")

print("CADDY_SOURCE_ATTESTATION=PASS")
