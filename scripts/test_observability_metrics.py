#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("ensure-observability-metrics.py")
SPEC = importlib.util.spec_from_file_location("ensure_observability_metrics", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ObservabilityPatchTests(unittest.TestCase):
    def test_adds_global_options_and_private_listener(self) -> None:
        rendered = MODULE.render("example.com {\n\trespond 200\n}\n")
        self.assertIn("admin 127.0.0.1:2019", rendered)
        self.assertIn("\tmetrics\n", rendered)
        self.assertIn(":2020 {", rendered)
        self.assertIn("metrics /metrics", rendered)

    def test_preserves_existing_loopback_admin(self) -> None:
        rendered = MODULE.render("{\n\tadmin 127.0.0.1:2019\n}\n\nexample.com {\n}\n")
        self.assertEqual(rendered.count("admin 127.0.0.1:2019"), 1)

    def test_is_idempotent(self) -> None:
        first = MODULE.render("example.com {\n}\n")
        self.assertEqual(MODULE.render(first), first)

    def test_rejects_non_loopback_admin(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.render("{\n\tadmin 0.0.0.0:2019\n}\n")

    def test_rejects_conflicting_metrics_port(self) -> None:
        with self.assertRaises(SystemExit):
            MODULE.render(":2020 {\n\trespond 200\n}\n")


if __name__ == "__main__":
    unittest.main()
