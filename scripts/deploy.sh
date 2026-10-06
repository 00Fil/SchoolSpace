#!/usr/bin/env bash
# Rilascio con compose (GAP-J03/L04): backup recente verificato -> job di migrazione ->
# privilegi PG -> rollout con attesa dei healthcheck -> smoke -> in caso di errore
# rollback automatico all'immagine precedente. Usato dalla CD (.github/workflows/cd.yml)
# e a mano dal runbook. Le migrazioni devono essere compatibili con la versione
# precedente (expand/contract, docs/runbooks/README.md#rilascio): il rollback NON le annulla.
#
# Uso: scripts/deploy.sh <image-tag>
# Variabili:
#   BASE_URL                URL pubblico per lo smoke (obbligatoria)
#   BACKUP_STATUS_FILE      stato dell'ultimo backup (default /var/backups/ripetizioni/backup-status.json)
#   BACKUP_MAX_AGE_HOURS    età massima del backup (default 24)
#   DEPLOY_RUN_BACKUP=1     se il backup è vecchio, eseguirlo ora (scripts/backup.sh)
#   DEPLOY_STATE_DIR        dove registrare la versione corrente (default /var/lib/ripetizioni)
#   DEPLOY_SKIP_PRIVILEGES=1 solo e2e senza psql (sconsigliato)
#   COMPOSE_FILES           default "-f compose.prod.yaml"
#   SMOKE_CMD               default scripts/smoke.sh
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
ROOT=$(repo_root)
cd "$ROOT"
tag=${1:-}
[[ $tag =~ ^[A-Za-z0-9._-]{1,128}$ ]] || die "uso: deploy.sh <image-tag>"
require_cmd docker
require_env BASE_URL
read -r -a files <<<"${COMPOSE_FILES:--f compose.prod.yaml}"
compose() { docker compose "${files[@]}" "$@"; }
state_dir=${DEPLOY_STATE_DIR:-/var/lib/ripetizioni}
mkdir -p "$state_dir"
previous=$(cat "$state_dir/current-tag" 2>/dev/null || true)
services=(web worker-solver worker-notifications beat proxy)
read -r -a smoke <<<"${SMOKE_CMD:-$ROOT/scripts/smoke.sh}"

# 1. Configurazione valida e immagini disponibili (firmate/scansionate dalla CI).
IMAGE_TAG=$tag compose config -q
IMAGE_TAG=$tag compose pull --quiet "${services[@]}" migrate 2>/dev/null ||
  warn "pull non riuscito: si usano immagini locali" tag="$tag"

# 2. Backup verificato nelle ultime 24 h (requisito G4: nessun rilascio senza copia).
status_file=${BACKUP_STATUS_FILE:-/var/backups/ripetizioni/backup-status.json}
max_age=$(( ${BACKUP_MAX_AGE_HOURS:-24} * 3600 ))
last=$(sed -n 's/.*"last_success_epoch": *\([0-9]*\).*/\1/p' "$status_file" 2>/dev/null || true)
if [ -z "$last" ] || [ $(( $(epoch) - last )) -gt "$max_age" ]; then
  if [ "${DEPLOY_RUN_BACKUP:-0}" = 1 ]; then
    info "backup assente o vecchio: lo eseguo ora"
    "$ROOT/scripts/backup.sh" >/dev/null
  else
    die "nessun backup riuscito nelle ultime ${BACKUP_MAX_AGE_HOURS:-24} h: rilascio bloccato"
  fi
fi

# 3. Migrazioni come job separato con il ruolo app_migrator, poi privilegi e trigger.
info "migrazioni" tag="$tag"
IMAGE_TAG=$tag compose --profile jobs run --rm -T migrate
if [ "${DEPLOY_SKIP_PRIVILEGES:-0}" != 1 ]; then
  "$ROOT/scripts/pg-privileges.sh"
fi

rollback() {
  if [ -z "$previous" ]; then
    die "rilascio fallito e nessuna versione precedente registrata: intervento manuale (runbook)"
  fi
  warn "rollback" from="$tag" to="$previous"
  IMAGE_TAG=$previous compose up -d --wait --wait-timeout 300 "${services[@]}"
  if "${smoke[@]}" "$BASE_URL"; then
    die "rilascio $tag fallito: ripristinata $previous (le migrazioni restano applicate)"
  fi
  die "rilascio $tag fallito e rollback a $previous NON verificato: SEV2, runbook"
}

# 4. Rollout: compose ricrea i servizi e attende i healthcheck (worker solver: stop grace
# 100 s, il run in corso termina o torna in coda grazie ad acks_late + lease).
info "rollout" tag="$tag" previous="${previous:-nessuna}"
if ! IMAGE_TAG=$tag compose up -d --wait --wait-timeout 300 --remove-orphans "${services[@]}"; then
  rollback
fi

# 5. Smoke sul percorso pubblico.
if ! "${smoke[@]}" "$BASE_URL"; then
  rollback
fi
printf '%s\n' "$tag" | write_atomic "$state_dir/current-tag"
[ -n "$previous" ] && printf '%s\n' "$previous" | write_atomic "$state_dir/previous-tag"
info "rilascio completato" tag="$tag"
