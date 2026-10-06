#!/usr/bin/env bash
# Prova di restore isolata (GAP-L03): ripristina un backup di scripts/backup.sh in un
# database NUOVO su un server di prova, applica ruoli/privilegi/trigger di infra/postgres
# (s4), verifica le invarianti, esegue la riconciliazione applicativa in dry-run e scrive
# l'evidenza JSON con RPO/RTO misurati contro gli obiettivi (15 min / 4 h).
# Procedura completa e restore reale: docs/runbooks/06-restore.md.
#
# Uso: scripts/restore-drill.sh <file .dump.age | .dump>   (manifest accanto al file)
#
# Connessione amministrativa al server DI PROVA: variabili libpq (PGHOST, PGPORT, PGUSER,
# PGPASSWORD/PGPASSFILE, PGSSLMODE, PGSSLROOTCERT). Il database viene sempre creato nuovo.
# Variabili:
#   RESTORE_CONFIRM_HOST     deve essere uguale a PGHOST (conferma esplicita del bersaglio)
#   PROD_DB_HOSTS            host di produzione, separati da virgola: rifiutati sempre
#   RESTORE_AGE_IDENTITY_FILE chiave privata age (custodia: docs/runbooks/06-restore.md)
#   RESTORE_DB_NAME          nome del DB di prova (default ripetizioni_drill_<timestamp>)
#   RESTORE_SKIP_ROLES=1     ruoli già presenti sul server (non riapplicare 01_roles.sql)
#   RESTORE_MANAGE_CMD       comando Django per la riconciliazione, es.
#                            "docker compose -f compose.prod.yaml run --rm -T web python manage.py"
#                            riceve POSTGRES_DB/DB_HOST/DB_PORT/POSTGRES_USER/POSTGRES_PASSWORD
#   RESTORE_EVIDENCE_DIR     directory dell'evidenza (default docs/evidence)
#   RESTORE_KEEP=1           non eliminare il DB di prova alla fine
#   RPO_TARGET_SECONDS / RTO_TARGET_SECONDS   default 900 / 14400
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
ROOT=$(repo_root)

src=${1:-}
[ -n "$src" ] && [ -f "$src" ] || die "uso: restore-drill.sh <backup .dump.age|.dump>"
require_cmd psql pg_restore createdb dropdb sha256sum
require_env PGHOST RESTORE_CONFIRM_HOST
[ "$RESTORE_CONFIRM_HOST" = "$PGHOST" ] ||
  die "RESTORE_CONFIRM_HOST diverso da PGHOST: bersaglio non confermato"
IFS=, read -r -a prod_hosts <<<"${PROD_DB_HOSTS:-}"
for h in "${prod_hosts[@]}"; do
  [ -n "$h" ] && [ "$h" = "$PGHOST" ] && die "rifiutato: $PGHOST è un host di produzione"
done

started=$(epoch)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
db=${RESTORE_DB_NAME:-ripetizioni_drill_${stamp,,}}
[[ $db =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || die "RESTORE_DB_NAME non valido"
[[ $db == *drill* || $db == *restore* ]] ||
  die "il DB di prova deve contenere 'drill' o 'restore' nel nome"
evidence_dir=${RESTORE_EVIDENCE_DIR:-$ROOT/docs/evidence}
RPO_TARGET_SECONDS=${RPO_TARGET_SECONDS:-900}
RTO_TARGET_SECONDS=${RTO_TARGET_SECONDS:-14400}
umask 077
work=$(mktemp -d)
created_db=0
problems=()

cleanup() {
  rm -rf "$work"
  if [ "$created_db" = 1 ] && [ "${RESTORE_KEEP:-0}" != 1 ]; then
    dropdb --if-exists --force "$db" 2>/dev/null || warn "drop del DB di prova fallito" db="$db"
  fi
}
trap cleanup EXIT
trap 'log ERROR "restore drill interrotto" line="$LINENO"' ERR

# 1. Manifest e integrità del file cifrato.
manifest="${src%.dump.age}"
manifest="${manifest%.dump}.manifest.json"
[ -f "$manifest" ] || die "manifest assente: $manifest"
jget() { sed -n "s/^ *\"$1\": *\"\{0,1\}\([^\",]*\)\"\{0,1\},\{0,1\}$/\1/p" "$manifest" | head -1; }
backup_epoch=$(jget finished_epoch)
backup_created=$(jget created_at)
[[ $backup_epoch =~ ^[0-9]+$ ]] || die "manifest senza finished_epoch"
plain=$src
if [[ $src == *.age ]]; then
  require_cmd age
  require_env RESTORE_AGE_IDENTITY_FILE
  [ "$(sha256_of "$src")" = "$(jget encrypted_sha256)" ] || die "hash del file cifrato non corrisponde"
  plain="$work/restore.dump"
  age --decrypt --identity "$RESTORE_AGE_IDENTITY_FILE" --output "$plain" "$src"
fi
[ "$(sha256_of "$plain")" = "$(jget dump_sha256)" ] || die "hash del dump non corrisponde"
pg_restore --list "$plain" >/dev/null
decrypted=$(epoch)
info "backup verificato" created_at="$backup_created" db="$db"

# 2. Database nuovo + estensione (sul servizio gestito: creata dall'amministratore).
psql -X -Atq -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$db'" | grep -q 1 &&
  die "il database $db esiste già: il drill non sovrascrive"
createdb "$db"
created_db=1
psql -X -q -v ON_ERROR_STOP=1 -d "$db" -c "CREATE EXTENSION IF NOT EXISTS btree_gist"

# 3. Ruoli a privilegio minimo (password casuali: i ruoli del drill non servono a nessuno).
if [ "${RESTORE_SKIP_ROLES:-0}" != 1 ]; then
  rnd() { head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
  psql -X -q -v ON_ERROR_STOP=1 -d "$db" -v db="$db" -v pw_migrator="$(rnd)" \
    -v pw_runtime="$(rnd)" -v pw_ro="$(rnd)" -f "$ROOT/infra/postgres/01_roles.sql" >/dev/null
fi

# 4. Restore in un'unica transazione: o tutto o niente.
pg_restore --exit-on-error --single-transaction --no-password -d "$db" "$plain"
restored=$(epoch)
info "restore completato" seconds="$((restored - decrypted))"

# 5. Privilegi e trigger append-only (idempotenti), poi verifiche s4 e invarianti s5.
psql -X -q -v ON_ERROR_STOP=1 -d "$db" -f "$ROOT/infra/postgres/02_privileges.sql" >/dev/null
psql -X -q -v ON_ERROR_STOP=1 -d "$db" -f "$ROOT/infra/postgres/03_append_only_triggers.sql" >/dev/null
while IFS= read -r line; do
  [ -n "$line" ] && problems+=("privileges: $line")
done < <(psql -X -At -v ON_ERROR_STOP=1 -d "$db" -f "$ROOT/infra/postgres/04_verify.sql")
while IFS= read -r line; do
  [ -n "$line" ] && problems+=("invariant: $line")
done < <(psql -X -At -v ON_ERROR_STOP=1 -d "$db" -f "$ROOT/scripts/sql/restore-invariants.sql")
tables=$(psql -X -Atq -d "$db" -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
accounts=$(psql -X -Atq -d "$db" -c "SELECT count(*) FROM identity_account" 2>/dev/null || echo -1)

# 6. Riconciliazione applicativa in dry-run (catene audit, ledger privacy, consegne, ...).
reconcile_status="skipped"
reconcile_report="$work/reconcile.json"
if [ -n "${RESTORE_MANAGE_CMD:-}" ]; then
  # shellcheck disable=SC2086 # il comando può contenere argomenti
  if POSTGRES_DB=$db DB_HOST=$PGHOST DB_PORT=${PGPORT:-5432} POSTGRES_USER=${PGUSER:-postgres} \
    POSTGRES_PASSWORD=${PGPASSWORD:-} $RESTORE_MANAGE_CMD post_restore_reconcile \
    --restore-point "$backup_created" --allow-missing --report "$reconcile_report" >&2; then
    reconcile_status="ok"
  else
    reconcile_status="failed"
    problems+=("post_restore_reconcile: non conforme (vedi report)")
  fi
fi
finished=$(epoch)

# 7. Evidenza. RPO del dump = età del backup all'inizio del drill; l'obiettivo di 15 min
# è raggiungibile solo con il PITR del servizio gestito (il dump giornaliero dà RPO <= 24 h).
backup_age=$((started - backup_epoch))
rto=$((finished - started))
rto_ok=false; [ "$rto" -le "$RTO_TARGET_SECONDS" ] && rto_ok=true
rpo_ok=false; [ "$backup_age" -le "$RPO_TARGET_SECONDS" ] && rpo_ok=true
ok=false; [ ${#problems[@]} -eq 0 ] && [ "$rto_ok" = true ] && [ "$reconcile_status" != failed ] && ok=true
mkdir -p "$evidence_dir"
evidence="$evidence_dir/restore-drill-${stamp}.json"
{
  printf '{\n  "format": "ripetizioni-restore-drill/1",\n'
  printf '  "drill_started_at": "%s",\n' "$(date -u -d "@$started" +%Y-%m-%dT%H:%M:%SZ)"
  printf '  "backup_file": "%s",\n  "backup_created_at": "%s",\n' "$(json_escape "$(basename "$src")")" "$backup_created"
  printf '  "target_host": "%s",\n  "target_database": "%s",\n' "$(json_escape "$PGHOST")" "$db"
  printf '  "decrypt_verify_seconds": %s,\n  "restore_seconds": %s,\n' "$((decrypted - started))" "$((restored - decrypted))"
  printf '  "rto_seconds": %s,\n  "rto_target_seconds": %s,\n  "rto_ok": %s,\n' "$rto" "$RTO_TARGET_SECONDS" "$rto_ok"
  printf '  "backup_age_seconds": %s,\n  "rpo_target_seconds": %s,\n  "rpo_ok_with_dump": %s,\n' "$backup_age" "$RPO_TARGET_SECONDS" "$rpo_ok"
  printf '  "rpo_note": "RPO 15 min solo con PITR del servizio gestito; il dump misura la copia indipendente",\n'
  printf '  "public_tables": %s,\n  "accounts": %s,\n' "$tables" "$accounts"
  printf '  "reconcile": "%s",\n' "$reconcile_status"
  printf '  "problems": ['
  sep=""
  for p in "${problems[@]}"; do printf '%s"%s"' "$sep" "$(json_escape "$p")"; sep=", "; done
  printf '],\n  "ok": %s\n}\n' "$ok"
} | write_atomic "$evidence"
if [ -s "$reconcile_report" ]; then cp "$reconcile_report" "${evidence%.json}.reconcile.json"; fi
info "evidenza scritta" file="$evidence" ok="$ok" rto_seconds="$rto"
echo "$evidence"
[ "$ok" = true ] || die "restore drill NON conforme" problems="${#problems[@]}"
