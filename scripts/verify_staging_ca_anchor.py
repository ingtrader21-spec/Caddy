#!/usr/bin/env python3
"""Fail-closed comparison of the established staging CA and candidate CA."""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

OPENSSL = "/usr/bin/openssl"


class AnchorError(RuntimeError):
    pass


def validate_certificate(path: Path, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise AnchorError(f"{label}_missing") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise AnchorError(f"{label}_not_regular")
    payload = path.read_bytes()
    if not payload:
        raise AnchorError(f"{label}_empty")
    if not Path(OPENSSL).is_file() or os.path.islink(OPENSSL):
        raise AnchorError("openssl_unavailable")
    result = subprocess.run(
        [OPENSSL, "x509", "-in", str(path), "-noout", "-checkend", "0"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise AnchorError(f"{label}_invalid")
    return payload


def verify(expected: Path, candidate: Path) -> str:
    expected_payload = validate_certificate(expected, "expected_ca")
    candidate_payload = validate_certificate(candidate, "candidate_ca")
    if candidate_payload != expected_payload:
        raise AnchorError("ca_identity_mismatch")
    return hashlib.sha256(expected_payload).hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        raise AnchorError("arguments")
    digest = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"STAGING_CA_ANCHOR=PASS sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AnchorError, OSError, subprocess.SubprocessError) as exc:
        print(f"STAGING_CA_ANCHOR=FAIL:{exc}", file=sys.stderr)
        raise SystemExit(2)
