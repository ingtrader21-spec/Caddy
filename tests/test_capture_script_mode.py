from pathlib import Path
import stat
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CaptureScriptModeTests(unittest.TestCase):
    def test_capture_runtime_baseline_is_executable(self) -> None:
        mode = (ROOT / "scripts/capture-runtime-baseline.sh").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "baseline capture must be executable")
        self.assertTrue(mode & stat.S_IXGRP, "baseline capture must be executable")
        self.assertTrue(mode & stat.S_IXOTH, "baseline capture must be executable")


if __name__ == "__main__":
    unittest.main()
