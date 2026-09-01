# Server ↔ GitHub controller setup

This repository is intended to become the source of truth for Caddy. The first sync is special because the server currently owns the authoritative live configuration.

## Phase 1 — install the controller checkout

On the Caddy server, use a dedicated checkout such as `/srv/caddy-controller`.

```bash
sudo mkdir -p /srv/caddy-controller
sudo chown "$USER":"$USER" /srv/caddy-controller

git clone git@github.com:appolon1908-hue/Caddy.git /srv/caddy-controller
cd /srv/caddy-controller

git fetch --all --prune
git checkout development
git pull --ff-only origin development
```

Use a read/write deploy key only for the one-time import if the server must push the import branch. After bootstrap, prefer a read-only deployment credential and perform normal edits/PRs away from the production host.

## Phase 2 — import the current live configuration

Create a dedicated import branch from `development`:

```bash
cd /srv/caddy-controller
git checkout development
git pull --ff-only origin development
git checkout -b feat/import-live-caddy

./scripts/import-live-config.sh
./scripts/validate.sh
git diff --check
git status
```

Before committing, manually inspect `config/Caddyfile`. Remove inline credentials and replace them with environment-variable references or another protected runtime-secret mechanism.

Then commit and push the import branch:

```bash
git add config/Caddyfile
git commit -m "chore: import live Caddy configuration"
git push -u origin feat/import-live-caddy
```

Open a PR from `feat/import-live-caddy` to `development` and promote in order:

`development` → `test` → `staging` → `production` → `main`

Do not skip an environment.

## Phase 3 — switch the server to pull-only production control

After the imported configuration reaches `production`:

```bash
cd /srv/caddy-controller
git fetch origin
git checkout production
git reset --hard origin/production
git config pull.ff only

CADDY_REVIEWED_SHA="$(git rev-parse origin/production)" ./scripts/deploy-production.sh
```

After this cutover, normal production flow is:

1. change `config/Caddyfile` on a feature/fix branch based on `development`;
2. PR to `development`;
3. promote to `test`;
4. promote to `staging` and record smoke evidence;
5. promote to `production`;
6. server fetches the exact reviewed production commit;
7. an operator supplies the explicitly approved 40-character `CADDY_REVIEWED_SHA`;
8. `scripts/deploy-production.sh` proves that SHA equals both `HEAD` and
   `origin/production`, validates and atomically backs up/installs the complete
   `config/` tree (including imported fragments), reloads, and checks Caddy;
9. after deployment evidence, promote `production` to `main`.

For the immutable container runtime, use `deploy/compose.runtime.yaml`. It
enforces a read-only root filesystem plus writable non-root mounts for
`/run/caddy`, `/var/log/caddy`, `/data`, and `/config`. `CADDY_IMAGE` must be an
approved `ghcr.io/...@sha256:<digest>` identity; mutable tags are not accepted
for production release evidence.

## Drift rule

Do not edit `/etc/caddy/Caddyfile` manually after cutover except for an emergency rollback/recovery. If an emergency server edit occurs, immediately capture the difference and reconcile it through a Git PR before another release.

Useful drift check:

```bash
sudo diff -u /srv/caddy-controller/config/Caddyfile /etc/caddy/Caddyfile
```

An empty diff is the desired state.
