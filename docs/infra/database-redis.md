# PostgreSQL 17 gestito e Redis privato (GAP-J04)

## PostgreSQL

Requisiti per il fornitore (D08):

| Requisito | Valore |
|---|---|
| Versione | PostgreSQL 17, aggiornamenti minori automatici in finestra concordata |
| Localizzazione | UE (region e backup), DPA art. 28 |
| Rete | endpoint **privato** (VPC/peering), nessun IP pubblico; accesso solo da host applicativo e host di backup |
| TLS | obbligatorio lato server; client `DB_SSLMODE=verify-full` con `DB_SSLROOTCERT` (CA del fornitore) |
| Estensioni | `btree_gist` **creata dall'amministratore** (`CREATE EXTENSION btree_gist`) prima della prima migrazione: i ruoli applicativi non hanno il privilegio |
| Backup | PITR con WAL continui, retention ≥ 7 giorni (D09), più la copia indipendente di `scripts/backup.sh` |
| Osservabilità | `pg_stat_statements`, `log_min_duration_statement = 500ms`, metriche di storage/WAL/archiviazione verso Prometheus |
| Limiti | `OPS_DB_STORAGE_LIMIT_BYTES`/`OPS_DB_WAL_LIMIT_BYTES` = limiti del piano (alert all'80 %) |

Ruoli (s4, `infra/postgres/README.md`): `app_owner` (NOLOGIN, proprietario), `app_migrator` (solo job
`migrate`, `PGOPTIONS=-c role=app_owner`), `app_runtime` (web/worker/beat, solo DML, timeout), `app_readonly`,
più `app_backup` (`scripts/sql/backup-role.sql`). Sequenza:

```bash
psql "<admin>" -v db=ripetizioni -v pw_migrator=... -v pw_runtime=... -v pw_ro=... -f infra/postgres/01_roles.sql
psql "<admin>" -v db=ripetizioni -v pw_backup=... -f scripts/sql/backup-role.sql
psql "<admin>" -d ripetizioni -c "CREATE EXTENSION IF NOT EXISTS btree_gist"
# a ogni rilascio (scripts/deploy.sh): migrate come app_migrator, poi
scripts/pg-privileges.sh     # 02_privileges + 03_append_only_triggers + 04_verify (zero righe)
```

Verificato in locale su PostgreSQL 17.10 (`scripts/e2e_local.py`): connessione TCP senza TLS rifiutata,
`app_runtime` senza DDL, migrazione come `app_migrator`, `04_verify.sql` pulito.

## Redis

Vedi `infra/redis/README.md`. In breve: Redis 7 privato (container dedicato o servizio gestito UE), solo TLS,
ACL con utente `app` senza comandi pericolosi, nessuna persistenza richiesta (è un trasporto), `noeviction`.
URL `rediss://` obbligatorie in produzione (`config.settings_production`), CA privata con `REDIS_CA_PATH`.
