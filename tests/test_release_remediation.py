from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseRemediationTests(unittest.TestCase):
    def test_deployment_preserves_private_tree_and_has_working_rollback(self) -> None:
        source = (ROOT / "scripts/deploy-production.sh").read_text()
        copy_private = 'cp -a -- "$TARGET_DIR/private" "$staged/private"'
        harden_managed = 'find "$staged" -type f -exec chmod 0644 {} +'
        self.assertIn('test -L "$TARGET_DIR/private"', source)
        self.assertIn(copy_private, source)
        self.assertLess(source.index(harden_managed), source.index(copy_private))
        self.assertEqual(source.count('mv "$TARGET_DIR" "$failed"'), 2)
        self.assertEqual(source.count('mv "$previous" "$TARGET_DIR"'), 2)
        self.assertNotIn('mv "$TARGET_DIR" "$staged"', source)

    def test_deployment_stages_only_reviewed_git_tracked_configuration(self) -> None:
        source = (ROOT / "scripts/deploy-production.sh").read_text()
        tracked_archive = (
            'git -C "$ROOT" archive --format=tar "$REVIEWED_SHA" -- config'
        )
        self.assertIn(tracked_archive, source)
        self.assertIn('--strip-components=1', source)
        self.assertNotIn('cp -a "$SOURCE_DIR/." "$staged/"', source)
        self.assertLess(
            source.index(tracked_archive),
            source.index('cp -a -- "$TARGET_DIR/private" "$staged/private"'),
        )

    def test_container_runtime_is_exact_nonroot_and_host_bound(self) -> None:
        compose = (ROOT / "deploy/compose.runtime.yaml").read_text()
        self.assertIn(
            "ghcr.io/appolon1908-hue/codestra-caddy@sha256:${CADDY_IMAGE_SHA256:",
            compose,
        )
        self.assertNotIn("CADDY_IMAGE:?", compose)
        self.assertIn('user: "65532:65532"', compose)
        self.assertIn("XDG_DATA_HOME: /data", compose)
        self.assertIn("XDG_CONFIG_HOME: /config", compose)
        self.assertIn("network_mode: host", compose)
        self.assertNotIn("ports:", compose)
        self.assertIn("cap_drop:\n      - ALL", compose)
        self.assertIn("cap_add:\n      - NET_BIND_SERVICE", compose)
        self.assertIn("no-new-privileges:true", compose)
        for trust_path in (
            "/etc/caddy/private/klyrow-events",
            "/etc/codestra/pki/middleware-private-ingress",
        ):
            self.assertEqual(compose.count(trust_path), 2)
        self.assertEqual(compose.count("read_only: true"), 3)

    def test_launcher_rejects_mutable_or_unreviewed_runtime(self) -> None:
        source = (ROOT / "scripts/run-immutable-runtime.sh").read_text()
        for required in (
            '[[ ! "$IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]]',
            '[[ "$(git -C "$ROOT" branch --show-current)" != "production" ]]',
            '[[ "$head_sha" != "$REVIEWED_SHA" || "$remote_sha" != "$REVIEWED_SHA" ]]',
            '[[ "$owner" != "65532:65532" ]]',
            "(mode_value & 0200) == 0",
            "(mode_value & 0022) != 0",
            '"$COSIGN_BIN" verify',
            '"$COSIGN_BIN" verify-attestation',
            'scripts/verify-image-attestation.py',
            '--certificate-identity "$CERTIFICATE_IDENTITY"',
            '--certificate-oidc-issuer "$CERTIFICATE_ISSUER"',
            '"$DOCKER_BIN" pull "$IMAGE_REF"',
            'org.opencontainers.image.revision',
            'org.opencontainers.image.source',
            '[[ "$image_revision" != "$REVIEWED_SHA" ]]',
            "run --rm --no-deps caddy",
            "up -d --pull never --no-build",
        ):
            self.assertIn(required, source)

    def test_signed_revision_binding_precedes_any_container_execution(self) -> None:
        source = (ROOT / "scripts/run-immutable-runtime.sh").read_text()
        verify = source.index('"$COSIGN_BIN" verify')
        provenance = source.index('"$COSIGN_BIN" verify-attestation')
        pull = source.index('"$DOCKER_BIN" pull "$IMAGE_REF"')
        revision = source.index('[[ "$image_revision" != "$REVIEWED_SHA" ]]')
        validate = source.index('compose -f "$COMPOSE" run --rm --no-deps caddy')
        start = source.index('compose -f "$COMPOSE" up -d --pull never --no-build')
        self.assertLess(verify, pull)
        self.assertLess(provenance, pull)
        self.assertLess(pull, revision)
        self.assertLess(revision, validate)
        self.assertLess(validate, start)

        dockerfile = (ROOT / "Dockerfile").read_text()
        workflow = (ROOT / ".github/workflows/immutable-release.yml").read_text()
        self.assertIn('org.opencontainers.image.revision="$VCS_REF"', dockerfile)
        self.assertIn('VCS_REF=${{ github.sha }}', workflow)
        self.assertIn('cosign sign --yes "$SUBJECT"', workflow)
        self.assertIn('cosign attest --yes', workflow)
        self.assertIn('tests/runtime-bind-test.sh local/codestra-caddy:${{ github.sha }}', workflow)
        self.assertIn('codestra.caddy.source.v1', workflow)
        self.assertIn('branches: [production]', workflow)
        self.assertNotIn('branches: [main]', workflow)
        self.assertEqual(workflow.count('refs/heads/production$'), 3)
        self.assertNotIn('refs/heads/main$', workflow)
        self.assertIn('refs/heads/production"', source)

        bind_test = (ROOT / "tests/runtime-bind-test.sh").read_text()
        for required in (
            "--user 65532:65532",
            "--cap-drop ALL",
            "--cap-add NET_BIND_SERVICE",
            "--security-opt no-new-privileges:true",
            "http://127.0.0.1:80/",
            "https://127.0.0.1:443/",
            '"/proc/$pid/net/udp"',
            "0000000000000400",
        ):
            self.assertIn(required, bind_test)


if __name__ == "__main__":
    unittest.main()
