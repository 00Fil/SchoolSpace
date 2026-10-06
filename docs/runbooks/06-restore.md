# 06 — Backup, restore e PITR (GAP-L01, L02, L03)

Obiettivi (da approvare con D08/D09): **RPO 15 min**, **RTO 4 h**.

| Livello | Mezzo | RPO | Dove |
|---|---|---|---|
| PITR | backup continuo + WAL del PostgreSQL 17 gestito (fornitore UE) | ≤ 15 min (archiviazione WAL continua) | fornitore |
| Copia indipendente | `scripts/backup.sh`: `pg_dump -Fc` cifrato con age, giornaliero | ≤ 24 h | bucket UE con versioning/object lock |
| Prova | `scripts/restore-drill.sh` mensile su DB isolato | — | `docs/evidence/` |

## Backup

Esecuzione giornaliera (timer systemd o cron sull'host di backup, **non** sul server applicativo):

```bash
PGHOST=<db-privato> PGDATABASE=ripetizioni PGUSER=app_backup PGPASSFILE=/etc/ripetizioni/pgpass \
PGSSLMODE=verify-full PGSSLROOTCERT=/etc/ripetizioni/pg-ca.pem \
BACKUP_AGE_RECIPIENTS_FILE=/etc/ripetizioni/backup-recipients.txt \
BACKUP_UPLOAD_CMD=/usr/local/bin/ripetizioni-upload BACKUP_TEXTFILE_DIR=/var/lib/node_exporter \
scripts/backup.sh
```

- Ruolo `app_backup` (`scripts/sql/backup-role.sql`, `pg_read_all_data`, sola lettura): `app_readonly` non
  basta (nessun accesso alle sequenze, timeout 60 s).
- Cifratura con **chiavi pubbliche** age: l'host di backup non può decifrare. Due destinatari: chiave
  operativa (RT) e chiave di emergenza in busta sigillata/cassaforte (Titolare). Le chiavi private non
  stanno mai sul server.
- Verifiche a ogni esecuzione: dimensione minima, `pg_restore --list` con `TABLE DATA`, SHA-256 del chiaro
  e del cifrato nel manifest; errore = exit ≠ 0, file parziali rimossi, `backup-status.failed.json` e metrica
  `ripetizioni_backup_last_run_success 0`.
- Retention locale `BACKUP_RETENTION_DAYS` (default 35, **D09 da approvare**); stessa durata come lifecycle
  rule del bucket. L'alert `BackupAssente` scatta se l'ultimo successo ha più di 26 h.

## PITR

Configurazione presso il fornitore (da verificare in contratto, D08): PostgreSQL 17, region UE, backup
automatici con retention ≥ 7 giorni, archiviazione WAL continua, cifratura a riposo, rete privata, TLS
obbligatorio. Alert `ArchiviazioneWALFallita` e `WALQuasiPieno` dalle metriche del fornitore.

Ripristino a un istante (`T` = ultimo istante sano, UTC):

1. **Congelare**: `scripts/maintenance.sh on`; fermare worker e beat
   (`docker compose -f compose.prod.yaml stop worker-solver worker-notifications beat`) per non generare
   nuove scritture né invii.
2. Ripristino PITR presso il fornitore in una **nuova istanza** all'istante `T` (mai sovrascrivere
   l'originale: serve per l'analisi).
3. Sull'istanza nuova, come amministratore: `CREATE EXTENSION IF NOT EXISTS btree_gist`; verificare i ruoli
   (`infra/postgres/01_roles.sql` è idempotente) e riapplicare `scripts/pg-privileges.sh`; `04_verify.sql` deve
   restituire zero righe; `psql -f scripts/sql/restore-invariants.sql` zero righe.
4. Puntare l'applicazione alla nuova istanza (`DB_HOST` nel secret manager) e avviare **solo** `web`.
5. **Riconciliazione** (obbligatoria, prima dei worker):
   ```bash
   docker compose -f compose.prod.yaml exec web python manage.py post_restore_reconcile \
     --restore-point <T> --report /tmp/reconcile-dry.json          # dry-run, leggere il report
   docker compose -f compose.prod.yaml exec web python manage.py post_restore_reconcile \
     --restore-point <T> --apply --report /tmp/reconcile.json
   ```
   Passi: heartbeat azzerati; run del solver interrotti → `FAILED`; sessioni, inviti e reset password
   invalidati (tutti devono rientrare: il DB ripristinato non conosce le revoche successive a `T`);
   ledger privacy (`apps.privacy.reconcile`, s4: cancellazioni ed export avvenuti dopo `T` vanno
   **ri-eseguiti** — richieste mancanti dal DB = esito non conforme da registrare a mano); comunicazioni
   (s3): email `PENDING/SENDING` messe in quarantena `AMBIGUOUS` e riconciliate col provider prima di ogni
   reinvio; controllo indipendente delle sovrapposizioni delle prenotazioni.
6. Avviare worker e beat, `scripts/smoke.sh https://<host>`, `scripts/maintenance.sh off`.
7. Comunicazione (CEN): cosa è stato perso tra `T` e il guasto (lezioni spostate, messaggi), da ripetere.
8. Registro: istanti, durata (RTO effettivo), dati persi (RPO effettivo), report di riconciliazione.

## Restore da copia indipendente

Se il PITR non è disponibile (fornitore compromesso, errore logico scoperto oltre la retention): come sopra
ma il passo 2 è `scripts/restore-drill.sh` con `RESTORE_KEEP=1` e `RESTORE_DB_NAME=ripetizioni_restore_<data>`
su un server di destinazione, poi rinomina/puntamento. RPO = età del dump (≤ 24 h).

## Restore drill (mensile)

```bash
PGHOST=<server-di-prova> PGUSER=<admin> RESTORE_CONFIRM_HOST=<server-di-prova> \
PROD_DB_HOSTS=<host-produzione> RESTORE_AGE_IDENTITY_FILE=<chiave-privata> \
RESTORE_MANAGE_CMD="docker compose -f compose.prod.yaml run --rm -T web python manage.py" \
scripts/restore-drill.sh /var/backups/ripetizioni/<file>.dump.age
```

Rifiuta host di produzione, bersagli non confermati e nomi senza `drill`/`restore`; crea sempre un DB nuovo;
verifica hash e manifest, ripristina in un'unica transazione, applica ruoli/privilegi/trigger s4, esegue
`04_verify.sql`, `restore-invariants.sql` e `post_restore_reconcile` in dry-run, misura RTO e età del backup e
scrive `docs/evidence/restore-drill-<data>.json` (exit ≠ 0 se non conforme). Esempio reale su PostgreSQL 17:
`docs/evidence/restore-drill-20261002T185536Z.json`.
