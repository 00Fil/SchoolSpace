#!/usr/bin/env bash
# Backup logico cifrato di PostgreSQL (GAP-L01). Complementare al PITR del servizio
# gestito (WAL continui, RPO 15 min): questo dump è la copia indipendente dal provider,
# verificabile e ripristinabile anche altrove (docs/runbooks/06-restore.md#backup).
#
# Passi: pg_dump -Fc -> verifica pg_restore --list -> sha256 -> cifratura age (chiave
# pubblica: l'host di backup NON può decifrare) -> manifest -> upload -> retention ->
# stato (JSON per /metrics + textfile Prometheus). Qualunque errore: exit != 0, file di
# stato di fallimento e nessun file parziale lasciato come "buono".
#
# Connessione: variabili libpq standard (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSFILE o
# PGPASSWORD, PGSSLMODE=verify-full, PGSSLROOTCERT). Ruolo consigliato: app_readonly.
#
# Variabili:
#   BACKUP_DIR                 directory locale (default /var/backups/ripetizioni)
#   BACKUP_AGE_RECIPIENTS_FILE chiavi pubbliche age dei destinatari (obbligatoria)
#   BACKUP_UPLOAD_CMD          comando eseguito come: $BACKUP_UPLOAD_CMD <file> <nome>
#                              (es. "scripts/upload-s3.sh"); vuoto = solo copia locale
#   BACKUP_RETENTION_DAYS      giorni di conservazione locale (default 35; D09 da approvare)
#   BACKUP_STATUS_FILE         stato JSON (default $BACKUP_DIR/backup-status.json)
#   BACKUP_TEXTFILE_DIR        directory del textfile collector di node_exporter (facoltativa)
#   BACKUP_MIN_BYTES           dimensione minima plausibile del dump (default 4096)
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"

BACKUP_DIR=${BACKUP_DIR:-/var/backups/ripetizioni}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-35}
BACKUP_STATUS_FILE=${BACKUP_STATUS_FILE:-$BACKUP_DIR/backup-status.json}
BACKUP_MIN_BYTES=${BACKUP_MIN_BYTES:-4096}
BACKUP_UPLOAD_CMD=${BACKUP_UPLOAD_CMD:-}
BACKUP_TEXTFILE_DIR=${BACKUP_TEXTFILE_DIR:-}

require_cmd pg_dump pg_restore psql age sha256sum
require_env PGDATABASE BACKUP_AGE_RECIPIENTS_FILE
[ -s "$BACKUP_AGE_RECIPIENTS_FILE" ] || die "file dei destinatari age vuoto o assente"
[[ $BACKUP_RETENTION_DAYS =~ ^[0-9]+$ ]] && [ "$BACKUP_RETENTION_DAYS" -ge 1 ] ||
  die "BACKUP_RETENTION_DAYS non valido"

umask 077
mkdir -p "$BACKUP_DIR"
started=$(epoch)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
base="ripetizioni-${PGDATABASE}-${stamp}"
work=$(mktemp -d "$BACKUP_DIR/.work-${stamp}-XXXXXX")
plain="$work/$base.dump"
enc="$BACKUP_DIR/$base.dump.age"
manifest="$BACKUP_DIR/$base.manifest.json"

write_metrics() { # write_metrics <esito 1|0> <epoch> <bytes>
  [ -n "$BACKUP_TEXTFILE_DIR" ] || return 0
  mkdir -p "$BACKUP_TEXTFILE_DIR"
  {
    echo "# HELP ripetizioni_backup_last_run_success Esito dell'ultimo backup (1 = riuscito)"
    echo "# TYPE ripetizioni_backup_last_run_success gauge"
    echo "ripetizioni_backup_last_run_success $1"
    echo "# HELP ripetizioni_backup_last_run_timestamp_seconds Fine dell'ultimo tentativo"
    echo "# TYPE ripetizioni_backup_last_run_timestamp_seconds gauge"
    echo "ripetizioni_backup_last_run_timestamp_seconds $2"
    if [ "$1" = 1 ]; then
      echo "# HELP ripetizioni_backup_last_success_timestamp_seconds Ultimo backup riuscito"
      echo "# TYPE ripetizioni_backup_last_success_timestamp_seconds gauge"
      echo "ripetizioni_backup_last_success_timestamp_seconds $2"
      echo "# HELP ripetizioni_backup_last_size_bytes Dimensione dell'ultimo backup cifrato"
      echo "# TYPE ripetizioni_backup_last_size_bytes gauge"
      echo "ripetizioni_backup_last_size_bytes $3"
    fi
  } | write_atomic "$BACKUP_TEXTFILE_DIR/ripetizioni_backup.prom"
}

on_error() {
  local rc=$? line=${1:-?}
  trap - ERR
  rm -rf "$work"
  rm -f "$enc" "$manifest"
  local now
  now=$(epoch)
  printf '{"last_failure_epoch": %s, "last_failure_line": "%s", "last_failure_exit": %s}\n' \
    "$now" "$line" "$rc" | write_atomic "${BACKUP_STATUS_FILE%.json}.failed.json"
  write_metrics 0 "$now" 0 || true
  log ERROR "backup fallito" line="$line" exit="$rc"
  exit "$rc"
}
trap 'on_error $LINENO' ERR
trap 'rm -rf "$work"' EXIT

info "avvio backup" database="$PGDATABASE" host="${PGHOST:-local}"
server_version=$(psql -X -Atq -c "SHOW server_version")
dump_version=$(pg_dump --version | awk '{print $NF}')

# 1. Dump in formato custom (compresso, ripristinabile per oggetto, verificabile).
pg_dump --format=custom --compress=6 --no-password --lock-wait-timeout=60s \
  --file="$plain" "$PGDATABASE"
dump_bytes=$(file_size "$plain")
[ "$dump_bytes" -ge "$BACKUP_MIN_BYTES" ] ||
  { log ERROR "dump troppo piccolo" bytes="$dump_bytes"; false; }

# 2. Verifica strutturale: il TOC deve essere leggibile e contenere i dati delle tabelle.
toc=$(pg_restore --list "$plain")
toc_entries=$(grep -vc '^;' <<<"$toc" || true)
table_data=$(grep -c ' TABLE DATA ' <<<"$toc" || true)
[ "$table_data" -gt 0 ] || { log ERROR "dump senza TABLE DATA"; false; }
dump_sha=$(sha256_of "$plain")

# 3. Cifratura con le sole chiavi pubbliche, poi rimozione del chiaro.
age --encrypt --recipients-file "$BACKUP_AGE_RECIPIENTS_FILE" --output "$enc.part" "$plain"
mv -f "$enc.part" "$enc"
rm -f "$plain"
enc_bytes=$(file_size "$enc")
enc_sha=$(sha256_of "$enc")
finished=$(epoch)

# 4. Manifest (necessario al restore drill: hash del chiaro, versioni, istante).
cat <<JSON | write_atomic "$manifest"
{
  "format": "ripetizioni-backup/1",
  "created_at": "$(date -u -d "@$started" +%Y-%m-%dT%H:%M:%SZ)",
  "started_epoch": $started,
  "finished_epoch": $finished,
  "database": "$(json_escape "$PGDATABASE")",
  "server_version": "$(json_escape "$server_version")",
  "pg_dump_version": "$(json_escape "$dump_version")",
  "dump_sha256": "$dump_sha",
  "dump_bytes": $dump_bytes,
  "toc_entries": $toc_entries,
  "table_data_entries": $table_data,
  "encrypted_file": "$(basename "$enc")",
  "encrypted_sha256": "$enc_sha",
  "encrypted_bytes": $enc_bytes,
  "retention_days": $BACKUP_RETENTION_DAYS
}
JSON

# 5. Upload (copia fuori host, region UE, bucket con object lock/versioning).
if [ -n "$BACKUP_UPLOAD_CMD" ]; then
  # shellcheck disable=SC2086 # il comando può contenere argomenti
  $BACKUP_UPLOAD_CMD "$enc" "$(basename "$enc")"
  # shellcheck disable=SC2086
  $BACKUP_UPLOAD_CMD "$manifest" "$(basename "$manifest")"
  info "upload completato" file="$(basename "$enc")"
else
  warn "BACKUP_UPLOAD_CMD vuoto: copia solo locale (non sufficiente in produzione)"
fi

# 6. Retention locale (la retention remota è una lifecycle rule del bucket, stessa durata).
pruned=0
while IFS= read -r -d '' old; do
  rm -f "$old"
  pruned=$((pruned + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'ripetizioni-*.dump.age' -o -name 'ripetizioni-*.manifest.json' \) \
  -mtime "+$((BACKUP_RETENTION_DAYS - 1))" -print0)

# 7. Stato per /metrics (OPS_BACKUP_STATUS_FILE) e per il textfile collector.
cat <<JSON | write_atomic "$BACKUP_STATUS_FILE"
{"last_success_epoch": $finished, "size_bytes": $enc_bytes, "file": "$(basename "$enc")", "sha256": "$enc_sha", "duration_seconds": $((finished - started))}
JSON
rm -f "${BACKUP_STATUS_FILE%.json}.failed.json"
write_metrics 1 "$finished" "$enc_bytes"
info "backup completato" file="$(basename "$enc")" bytes="$enc_bytes" \
  seconds="$((finished - started))" pruned="$pruned"
echo "$enc"
