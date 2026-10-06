#!/usr/bin/env bash
# Prova end-to-end con Docker (GAP-J07): immagini di produzione, PostgreSQL 17 e Redis 7
# reali con TLS verificato (CA locale), ruoli s4, migrazione come job, proxy HTTPS, smoke e
# scenari di resilienza. Equivalente senza Docker (stessi passi su processi locali):
# scripts/e2e-local.sh. Richiede Docker Compose v2.24+.
#
# Uso: scripts/e2e-compose.sh [--keep]
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
. "$(dirname "$0")/lib/e2e-certs.sh"
ROOT=$(repo_root)
cd "$ROOT"
require_cmd docker openssl curl
export COMPOSE_PROJECT_NAME=ripetizioni-e2e IMAGE_TAG=e2e
compose() { docker compose -f compose.prod.yaml -f compose.e2e.yaml "$@"; }
keep=0; [ "${1:-}" = --keep ] && keep=1
base=https://localhost:8443
results=()
record() { results+=("$1=$2"); info "scenario $1: $2"; }
cleanup() {
  [ "$keep" = 1 ] || compose --profile jobs down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_status() { # wait_status <path> <codice> <secondi>
  local i code
  for ((i = 0; i < $3; i++)); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --cacert .e2e/ca.crt "$base$1" || true)
    [ "$code" = "$2" ] && return 0
    sleep 1
  done
  return 1
}
web_ready() { compose exec -T web python manage.py ops_check --checks "$1" >/dev/null 2>&1; }

# 0. Materiale TLS e ACL.
e2e_certs .e2e db redis
e2e_acl .e2e/redis-users.acl e2e-only-redis

# 1. Build delle immagini di produzione.
[ "${E2E_SKIP_BUILD:-0}" = 1 ] || compose build web proxy

# 2. DB e Redis, ruoli a privilegio minimo (s4) come amministratore.
compose up -d --wait db redis
compose exec -T db psql -X -q -v ON_ERROR_STOP=1 -U e2e_admin -d ripetizioni \
  -c "CREATE EXTENSION IF NOT EXISTS btree_gist"
compose exec -T db psql -X -q -v ON_ERROR_STOP=1 -U e2e_admin -d ripetizioni -v db=ripetizioni \
  -v pw_migrator=e2e-only-migrator -v pw_runtime=e2e-only-runtime -v pw_ro=e2e-only-ro \
  -f - <infra/postgres/01_roles.sql

# 3. Scenario "broker giù all'avvio": web parte, healthz ok, readiness 503 finché Redis manca.
compose stop redis
compose --profile jobs run --rm -T migrate
PSQL="docker compose -f compose.prod.yaml -f compose.e2e.yaml exec -T db psql -U e2e_admin -d ripetizioni" \
  "$ROOT/scripts/pg-privileges.sh"
compose up -d --no-deps web
sleep 15
if compose exec -T web python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" &&
  ! web_ready broker; then
  record broker_down_at_start ok
else
  record broker_down_at_start FAILED
fi
compose up -d --wait redis

# 4. Stack completo e smoke via proxy HTTPS.
compose up -d --wait
if SMOKE_CACERT=.e2e/ca.crt "$ROOT/scripts/smoke.sh" "$base"; then
  record smoke ok
else
  record smoke FAILED
fi

# 5. Redis riavviato: la readiness torna verde senza riavviare web e worker.
compose restart redis
if wait_status /api/v1/ready 200 60 && web_ready broker,cache; then
  record redis_restart ok
else
  record redis_restart FAILED
fi

# 6. Worker notifiche ucciso: l'heartbeat invecchia, al riavvio torna fresco.
compose kill -s KILL worker-notifications
compose up -d --wait worker-notifications
if timeout 120 bash -c "until docker compose -f compose.prod.yaml -f compose.e2e.yaml exec -T web \
  python manage.py ops_check --checks workers >/dev/null 2>&1; do sleep 5; done"; then
  record worker_kill_recovery ok
else
  record worker_kill_recovery FAILED
fi

# 7. Manutenzione: 503 con pagina dedicata, poi ritorno al servizio.
MAINTENANCE_VOLUME=${COMPOSE_PROJECT_NAME}_maintenance "$ROOT/scripts/maintenance.sh" on
if wait_status / 503 10; then record maintenance_on ok; else record maintenance_on FAILED; fi
MAINTENANCE_VOLUME=${COMPOSE_PROJECT_NAME}_maintenance "$ROOT/scripts/maintenance.sh" off
if wait_status / 200 10; then record maintenance_off ok; else record maintenance_off FAILED; fi

printf '%s\n' "${results[@]}"
for r in "${results[@]}"; do [[ $r == *=ok ]] || die "e2e compose: scenari falliti"; done
info "e2e compose superato"
