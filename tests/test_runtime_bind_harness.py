from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeBindHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (ROOT / "tests/runtime-bind-test.sh").read_text(encoding="utf-8")

    def test_privileged_bind_proof_is_network_namespace_isolated(self) -> None:
        self.assertIn("--network none", self.source)
        self.assertNotIn("--network host", self.source)
        self.assertNotIn("-p 80", self.source)
        self.assertNotIn("-p 443", self.source)
        self.assertIn("CADDY_RUNTIME_NETWORK=ISOLATED_NONE", self.source)

    def test_process_state_is_guarded_before_proc_readback(self) -> None:
        self.assertIn("process_snapshot()", self.source)
        self.assertIn("[[ \"$running\" == true ]] || return 1", self.source)
        self.assertIn("[[ -r \"$status\" ]] || return 1", self.source)
        self.assertIn("container_exited_before_socket_readback", self.source)
        self.assertIn("socket_readback_timeout", self.source)
        self.assertIn("2>/dev/null", self.source)

    def test_effective_nonroot_security_is_still_proven(self) -> None:
        for token in (
            "--user 65532:65532",
            "--read-only",
            "--cap-drop ALL",
            "--cap-add NET_BIND_SERVICE",
            "--security-opt no-new-privileges:true",
            "0000000000000400",
            "CADDY_EFFECTIVE_CAPABILITIES=NET_BIND_SERVICE_ONLY",
        ):
            self.assertIn(token, self.source)


if __name__ == "__main__":
    unittest.main()
