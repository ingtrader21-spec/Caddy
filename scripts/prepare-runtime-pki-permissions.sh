#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

fail() {
  printf 'CADDY_PKI_PERMISSIONS=FAIL:%s\n' "$1" >&2
  exit 2
}

[[ $# -eq 0 ]] || fail arguments_not_allowed
[[ "$(id -u)" -eq 0 ]] || fail root_required

klyrow_dir=/etc/caddy/private/klyrow-events
middleware_dir=/etc/codestra/pki/middleware-private-ingress
klyrow_files=(tls-fullchain.crt tls.key klyrow-client.crt)
middleware_files=(server.crt server.key staging-server.crt staging-server.key client-ca.crt)

prepare_tree() {
  local directory="$1"
  shift
  [[ -d "$directory" && ! -L "$directory" ]] || fail "directory:$directory"
  chown 0:65532 "$directory"
  chmod 0750 "$directory"

  local name path
  for name in "$@"; do
    path="$directory/$name"
    [[ -f "$path" && ! -L "$path" ]] || fail "file:$path"
    chown 0:65532 "$path"
    chmod 0440 "$path"
  done

  if find "$directory" -mindepth 1 -type l -print -quit | grep -q .; then
    fail "symlink:$directory"
  fi
  if find "$directory" -mindepth 1 -maxdepth 1 ! -type f -print -quit | grep -q .; then
    fail "unexpected_entry:$directory"
  fi
}

prepare_tree "$klyrow_dir" "${klyrow_files[@]}"
prepare_tree "$middleware_dir" "${middleware_files[@]}"

printf 'CADDY_PKI_PERMISSIONS=PASS\n'
printf 'CADDY_PKI_RUNTIME_IDENTITY=65532:65532\n'
printf 'CADDY_PKI_FILE_MODE=0440\n'
printf 'CADDY_PKI_DIRECTORY_MODE=0750\n'
