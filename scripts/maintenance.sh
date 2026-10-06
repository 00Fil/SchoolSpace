#!/usr/bin/env bash
# Pagina di manutenzione (GAP-J08): il proxy risponde 503 + maintenance.html a tutte le
# richieste (tranne la challenge ACME) finché esiste /srv/maintenance/on nel volume
# "maintenance". Uso: scripts/maintenance.sh on|off|status
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
require_cmd docker
project=${COMPOSE_PROJECT_NAME:-ripetizioni}
volume=${MAINTENANCE_VOLUME:-${project}_maintenance}
helper=${MAINTENANCE_HELPER_IMAGE:-busybox:1.37}
in_volume() { docker run --rm --network none -v "$volume:/m" "$helper" sh -c "$1"; }
case ${1:-status} in
  on)
    in_volume 'date -u +%Y-%m-%dT%H:%M:%SZ > /m/on'
    info "manutenzione ATTIVA" volume="$volume" ;;
  off)
    in_volume 'rm -f /m/on'
    info "manutenzione disattivata" volume="$volume" ;;
  status)
    if in_volume 'test -f /m/on'; then echo on; else echo off; fi ;;
  *) die "uso: maintenance.sh on|off|status" ;;
esac
