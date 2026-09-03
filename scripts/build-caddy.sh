#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CADDY_SOURCE_REPOSITORY='https://github.com/caddyserver/caddy.git'
readonly CADDY_SOURCE_SHA='e2eee6a7fce366321294c9c2a79f3146891dcbdf'

cd "$ROOT_DIR"
rm -rf build/caddy-source build/caddy build/codestra-set-bind-capability
mkdir -p build
config_sha256="$(python3 scripts/config_digest.py)"
printf '%s\n' "$config_sha256" > build/config.sha256

git clone --filter=blob:none "$CADDY_SOURCE_REPOSITORY" build/caddy-source
git -C build/caddy-source checkout --detach "$CADDY_SOURCE_SHA"
(
  cd build/caddy-source
  go get \
    golang.org/x/crypto@v0.55.0 \
    golang.org/x/net@v0.57.0 \
    golang.org/x/text@v0.41.0 \
    google.golang.org/grpc@v1.83.1
  go mod tidy
  CGO_ENABLED=0 go build -trimpath -ldflags '-s -w' -o ../caddy ./cmd/caddy
  ../caddy version
  ../caddy list-modules --packages > ../caddy-modules.txt
  go version -m ../caddy > ../caddy-go-version.txt
  git diff -- go.mod go.sum > ../caddy-module-overrides.patch
  jq -n \
    --arg repository "${CADDY_SOURCE_REPOSITORY%.git}" \
    --arg source_sha "$CADDY_SOURCE_SHA" \
    --arg wrapper_sha "${GITHUB_SHA:-local}" \
    --arg config_sha256 "$config_sha256" \
    --arg binary_sha256 "$(sha256sum ../caddy | cut -d' ' -f1)" \
    --arg go_mod_sha256 "$(sha256sum go.mod | cut -d' ' -f1)" \
    --arg go_sum_sha256 "$(sha256sum go.sum | cut -d' ' -f1)" \
    '{schema:"codestra.caddy.binary-build.v2",source_repository:$repository,source_sha:$source_sha,wrapper_sha:$wrapper_sha,config_sha256:$config_sha256,binary_sha256:$binary_sha256,go_mod_sha256:$go_mod_sha256,go_sum_sha256:$go_sum_sha256}' \
    > ../caddy-binary-build-attestation.json
)
CGO_ENABLED=0 go build -trimpath -ldflags '-s -w' \
  -o build/codestra-set-bind-capability build-tools/set-bind-capability/main.go
printf 'CADDY_BUILD=PASS\nCONFIG_SHA256=%s\n' "$config_sha256"
