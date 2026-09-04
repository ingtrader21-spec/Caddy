#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

readonly ACTIONLINT_VERSION=1.7.12
readonly ACTIONLINT_ARCHIVE="actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz"
readonly ACTIONLINT_SHA256=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
readonly ACTIONLINT_URL="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${ACTIONLINT_ARCHIVE}"

work="$(mktemp -d)"
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT

curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  --output "$work/$ACTIONLINT_ARCHIVE" "$ACTIONLINT_URL"
printf '%s  %s\n' "$ACTIONLINT_SHA256" "$work/$ACTIONLINT_ARCHIVE" | sha256sum -c -
tar --extract --gzip --file "$work/$ACTIONLINT_ARCHIVE" \
  --directory "$work" --no-same-owner --no-same-permissions
[[ -f "$work/actionlint" && ! -L "$work/actionlint" ]]
chmod 0700 "$work/actionlint"
"$work/actionlint" -version
"$work/actionlint" -color
printf 'GITHUB_ACTIONS_STATIC_VALIDATION=PASS\n'
