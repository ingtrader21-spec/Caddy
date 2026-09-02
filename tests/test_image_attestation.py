import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/verify-image-attestation.py"
DIGEST = "a" * 64
REVISION = "b" * 40
REPOSITORY = "https://github.com/appolon1908-hue/Caddy"
WORKFLOW = REPOSITORY + "/.github/workflows/immutable-release.yml@refs/heads/production"


class ImageAttestationTests(unittest.TestCase):
    def verify(self, *, digest=DIGEST, revision=REVISION, repository=REPOSITORY):
        statement = {
            "subject": [{"name": "ghcr.io/appolon1908-hue/codestra-caddy", "digest": {"sha256": digest}}],
            "predicate": {
                "repository": repository,
                "revision": revision,
                "workflow_identity": WORKFLOW,
                "release_identity": revision,
            },
        }
        envelope = [{"payload": base64.b64encode(json.dumps(statement).encode()).decode()}]
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as stream:
            json.dump(envelope, stream)
            stream.flush()
            return subprocess.run(
                [str(VERIFIER), stream.name, DIGEST, REPOSITORY, REVISION],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_exact_tuple_passes(self):
        self.assertEqual(self.verify().returncode, 0)

    def test_old_new_other_repo_and_wrong_digest_fail(self):
        cases = (
            {"revision": "c" * 40},
            {"repository": "https://github.com/example/Caddy"},
            {"digest": "d" * 64},
        )
        for case in cases:
            with self.subTest(case=case):
                self.assertNotEqual(self.verify(**case).returncode, 0)


if __name__ == "__main__":
    unittest.main()
