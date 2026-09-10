# Production container synchronization

The production host uses a read-only checkout of the `production` branch and the immutable container launcher. The host must not maintain a separate Caddy route authority or edit `/etc/caddy` as the normal release path.

Required release tuple:

```text
CADDY_REVIEWED_SHA=<exact protected production SHA>
CADDY_IMAGE_SHA256=<signed GHCR digest without sha256: prefix>
CADDY_CONFIG_SHA256=<deterministic config/ hash>
```

The bounded activation sequence is:

1. fetch `origin/production` and check out the exact approved SHA with a clean worktree;
2. verify the signed image and v2 source attestation;
3. verify OCI source/revision/config labels against the reviewed SHA and `config/` hash;
4. validate the image's `/etc/caddy/Caddyfile` without starting it;
5. start `codestra-caddy` from `deploy/compose.runtime.yaml` with no build or mutable pull;
6. require healthy container read-back and the fixed no-argument production canary;
7. retain root-owned mode `0600` evidence.

The fixed runtime is non-root UID/GID `65532`, read-only, and has only `NET_BIND_SERVICE`. The Caddy data and runtime-config directories are host-owned persistent state; Klyrow and Middleware certificate directories are fixed read-only mounts. No deployment step changes SSH, firewall rules, DNS ownership, or unrelated workloads.

On activation failure, `scripts/run-immutable-runtime.sh` invokes the fixed rollback command. That command selects only the signed digest recorded in `config/release-baseline.v1.json`, computes the baseline image's exact embedded configuration checksum, restores the container, and verifies image/config read-back and health.
