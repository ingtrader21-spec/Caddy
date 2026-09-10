#!/usr/bin/env python3
"""Validate that one Compose file owns the complete Caddy runtime."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "deploy/compose.runtime.yaml"
CANONICAL_RELATIVE = CANONICAL.relative_to(ROOT).as_posix()


def fail(reason: str) -> None:
    raise SystemExit(f"CADDY_UNIFIED_COMPOSE=FAIL:{reason}")


def compose_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        lower = path.name.lower()
        if "compose" in lower and path.suffix.lower() in {".yml", ".yaml"}:
            files.append(path)
    return sorted(files, key=lambda item: item.as_posix())


def main() -> int:
    if not CANONICAL.is_file():
        fail("canonical_file_missing")

    owners: list[str] = []
    for path in compose_files():
        source = path.read_text(encoding="utf-8")
        if (
            "container_name: codestra-caddy" in source
            or "ghcr.io/appolon1908-hue/codestra-caddy@sha256:" in source
        ):
            owners.append(path.relative_to(ROOT).as_posix())
    if owners != [CANONICAL_RELATIVE]:
        fail("competing_runtime_authority:" + ",".join(owners))

    source = CANONICAL.read_text(encoding="utf-8")
    required = (
        "name: codestra-caddy-edge",
        "x-codestra-runtime-authority:",
        "schema: codestra.caddy-compose.v1",
        "canonical_file: deploy/compose.runtime.yaml",
        "service: caddy",
        "configuration_root: config",
        "services:\n  caddy:",
        "container_name: codestra-caddy",
        "ghcr.io/appolon1908-hue/codestra-caddy@sha256:${CADDY_IMAGE_SHA256:",
        'user: "65532:65532"',
        "read_only: true",
        "cap_drop:\n      - ALL",
        "cap_add:\n      - NET_BIND_SERVICE",
        "no-new-privileges:true",
        "network_mode: host",
        "io.codestra.caddy.source.sha",
        "io.codestra.caddy.image.digest",
        "io.codestra.caddy.config.sha256",
        "io.codestra.caddy.release.id",
        "healthcheck:",
    )
    for token in required:
        if token not in source:
            fail("canonical_contract:" + token.replace("\n", "\\n"))
    if "\n    build:" in source:
        fail("runtime_build_prohibited")
    if "\n    ports:" in source:
        fail("runtime_port_mapping_prohibited")
    if ":latest" in source or " latest" in source:
        fail("mutable_image_prohibited")
    if source.count("container_name: codestra-caddy") != 1:
        fail("container_identity_not_unique")

    lifecycle = (
        ROOT / "scripts/run-immutable-runtime.sh",
        ROOT / "scripts/rollback-runtime.sh",
        ROOT / "scripts/verify-rollback-baseline.sh",
        ROOT / "scripts/validate-ci.sh",
    )
    for path in lifecycle:
        if not path.is_file():
            fail("lifecycle_missing:" + path.relative_to(ROOT).as_posix())
        text = path.read_text(encoding="utf-8")
        if "deploy/compose.runtime.yaml" not in text:
            fail("lifecycle_compose_drift:" + path.relative_to(ROOT).as_posix())

    # The community n8n security overlay is not a Caddy runtime authority. It
    # may remain a separate overlay only while it contains no Caddy service,
    # image, container identity, or lifecycle command.
    overlay = ROOT / "deploy/community-n8n/compose.security.yaml"
    if overlay.exists():
        text = overlay.read_text(encoding="utf-8")
        forbidden = (
            "container_name: codestra-caddy",
            "ghcr.io/appolon1908-hue/codestra-caddy",
            "services:\n  caddy:",
        )
        if any(token in text for token in forbidden):
            fail("community_overlay_became_runtime_authority")

    print(f"CADDY_UNIFIED_COMPOSE=PASS canonical={CANONICAL_RELATIVE}")
    print("CADDY_COMPOSE_RUNTIME_OWNERS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
