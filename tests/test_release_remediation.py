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
            'docker compose -f "$COMPOSE" pull caddy',
            "run --rm --no-deps caddy",
            "up -d --pull never --no-build",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
