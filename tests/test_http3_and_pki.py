from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Http3AndPkiTests(unittest.TestCase):
    def test_http3_probe_is_built_attested_and_shipped(self):
        source = (ROOT / "build-tools/http3-probe/main.go").read_text()
        self.assertIn('"github.com/quic-go/quic-go/http3"', source)
        self.assertIn("resp.ProtoMajor != 3", source)
        self.assertIn("CADDY_HTTP3_CANARY=PASS", source)

        build = (ROOT / "scripts/build-release-inputs.sh").read_text()
        self.assertIn("$BUILD/codestra-http3-probe", build)
        self.assertIn("http3_probe_sha256", build)

        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn(
            "COPY --chown=65532:65532 build/codestra-http3-probe /usr/bin/codestra-http3-probe",
            dockerfile,
        )

    def test_isolated_and_production_canaries_make_real_quic_requests(self):
        websocket = (ROOT / "scripts/websocket_probe.py").read_text()
        self.assertIn("codestra-http3-probe", websocket)
        self.assertIn('"/api/v1/health"', websocket)

        production = (ROOT / "scripts/production-canary.sh").read_text()
        self.assertIn(
            "exec codestra-caddy /usr/bin/codestra-http3-probe",
            production,
        )
        self.assertIn("data['http3_canary']='PASS'", production)
        self.assertIn("HTTP3=PASS", production)

    def test_mtls_canary_uses_the_contract_method(self):
        canary = (ROOT / "tests/runtime-canary-test.sh").read_text()
        self.assertGreaterEqual(canary.count("--request POST --data '{}'"), 2)
        self.assertIn(
            "middleware-email-events.internal.codestra.agency:18080/internal/provider-events/klyrow",
            canary,
        )
        self.assertIn("CADDY_MTLS_CANARY=PASS", canary)

    def test_pki_preparer_has_fixed_paths_and_least_privilege_modes(self):
        preparer = (ROOT / "scripts/prepare-runtime-pki-permissions.sh").read_text()
        for token in (
            "/etc/caddy/private/klyrow-events",
            "/etc/codestra/pki/middleware-private-ingress",
            "chown 0:65532",
            "chmod 0750",
            "chmod 0440",
            "root_required",
            "arguments_not_allowed",
        ):
            self.assertIn(token, preparer)

        activation = (ROOT / "scripts/run-immutable-runtime.sh").read_text()
        self.assertIn("prepare-runtime-pki-permissions.sh", activation)
        self.assertIn("trust_directory_mode", activation)
        self.assertIn("trust_file_mode", activation)
        self.assertIn("root_required", activation)


if __name__ == "__main__":
    unittest.main()
