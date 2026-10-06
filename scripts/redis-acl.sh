#!/usr/bin/env bash
# Genera ./secrets/redis-users.acl con password casuali (stampate una sola volta, da
# salvare subito nel secret manager). Uso: scripts/redis-acl.sh [file-di-uscita]
set -euo pipefail
out=${1:-./secrets/redis-users.acl}
umask 077
mkdir -p "$(dirname "$out")"
gen() { head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40; }
hash() { printf '%s' "$1" | sha256sum | cut -d' ' -f1; }
app=$(gen); exporter=$(gen)
sed -e "s|#<sha256-della-password-app>|#$(hash "$app")|" \
    -e "s|#<sha256-della-password-exporter>|#$(hash "$exporter")|" \
    -e '/^#/d' "$(dirname "$0")/../infra/redis/users.acl.example" > "$out"
echo "ACL scritta in $out"
echo "REDIS_APP_PASSWORD=$app"
echo "REDIS_EXPORTER_PASSWORD=$exporter"
echo "Salvare ora le password nel secret manager: non vengono conservate altrove." >&2
