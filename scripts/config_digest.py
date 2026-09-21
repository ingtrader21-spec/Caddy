#!/usr/bin/env python3
"""Emit the deterministic SHA-256 of the canonical Caddy desired state."""
from __future__ import annotations

from pathlib import Path

from mission5_desired_state import configuration_sha256, desired_state_material


ROOT = Path(__file__).resolve().parents[1]

print(configuration_sha256(desired_state_material(ROOT)))