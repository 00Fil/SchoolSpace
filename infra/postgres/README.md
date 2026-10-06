# PostgreSQL — ruoli a privilegio minimo e tabelle append-only (GAP-E08)

Stato: implementato e testato staticamente; i test su trigger reali (`tests/test_privacy_postgres.py`)
sono **skipped su SQLite** e vanno eseguiti in CI con PostgreSQL 17 prima di G4.

## Ruoli

| Ruolo | Login | Uso | Privilegi |
|---|---|---|---|
| `app_owner` | no | proprietario di schema e tabelle | DDL; manutenzione governata dell'audit |
| `app_migrator` | sì | solo job di migrazione (`SET ROLE app_owner`) | come `app_owner`, NOINHERIT |
| `app_runtime` | sì | web, worker Celery, beat | SELECT/INSERT/UPDATE/DELETE, nessun DDL, nessun TRUNCATE; **solo INSERT/SELECT** su audit e snapshot |
| `app_readonly` | sì | supporto e report | SELECT, sessione `read_only` |

Limiti del runtime: `statement_timeout=15s`, `idle_in_transaction_session_timeout=30s`, `lock_timeout=5s`.
Il worker solver può avere un ruolo dedicato con timeout più ampio se il benchmark G3 lo richiede (non creato qui).

## Tabelle append-only

`lesson_calendar_calendaraudit`, `governance_pathauditevent`, `scheduling_planningaudit`,
`scheduling_planningsnapshot`, `governance_auditevent` (audit unificato s4), `privacy_retentionrun` (ricevute), `identity_identityauditevent` (audit accessi s1: il trigger `identity_audit_no_update` di identity 0003 è sostituito dalla guardia comune con `governance.0005_identity_audit_append_only`, che lo ripristina in reverse).

Tre livelli di protezione:
1. **ORM**: queryset/`save`/`delete` che sollevano errore (già presenti per gli snapshot; `AuditEvent` in governance).
2. **Privilegi**: `REVOKE UPDATE, DELETE, TRUNCATE ... FROM app_runtime` (`02_privileges.sql`).
3. **Trigger** `app_append_only_guard()` (`03_append_only_triggers.sql`, installato anche dalla migrazione
   `governance.0004_postgres_append_only`): blocca UPDATE/DELETE/TRUNCATE con SQLSTATE `42501` anche per
   il proprietario. Eccezioni:
   - manutenzione governata: ruolo membro del proprietario **e** `SET LOCAL app.audit_maintenance='on'`
     (usata solo dai job di retention `audit_events` e `identity_audit_ip` e dall'anonimizzazione account per azzerare gli IP, dopo approvazione D09);
   - `TRUNCATE` nei database `test_*` (flush dei `TransactionTestCase` di Django).

## Sequenza di deploy

```bash
# 1. una tantum, come amministratore del servizio gestito
psql -v ON_ERROR_STOP=1 -v db=ripetizioni -v pw_migrator="$PW_MIGRATOR" \
     -v pw_runtime="$PW_RUNTIME" -v pw_ro="$PW_RO" -f infra/postgres/01_roles.sql
# 2. a ogni rilascio, con le credenziali del migratore
PGOPTIONS="-c role=app_owner" POSTGRES_USER=app_migrator python manage.py migrate
psql -v ON_ERROR_STOP=1 -f infra/postgres/02_privileges.sql
psql -v ON_ERROR_STOP=1 -f infra/postgres/03_append_only_triggers.sql   # idempotente
# 3. verifica: ogni riga restituita è una non conformità
psql -f infra/postgres/04_verify.sql
# 4. runtime
POSTGRES_USER=app_runtime gunicorn ...
```

Il job di retention per la categoria `audit_events` va eseguito con le credenziali del migratore
(`PGOPTIONS="-c role=app_owner" python manage.py privacy_retention --execute --category audit_events`):
con `app_runtime` fallisce per i privilegi revocati, come previsto.

`03_append_only_triggers.sql` è generato: `python manage.py governance_append_only_sql > infra/postgres/03_append_only_triggers.sql`.
Un test verifica che file e modulo `apps/governance/pg_append_only.py` coincidano.

## Punti aperti
- Separare `DATABASES` runtime/migrazione nelle impostazioni (proprietà s1/s5): oggi si usano variabili d'ambiente.
- `pg_stat_statements`, log delle query lente > 500 ms e TLS obbligatorio sono configurazione del servizio gestito (s5).
