-- Privilegi sugli oggetti esistenti. Idempotente: rieseguire DOPO OGNI `migrate`
-- (le nuove tabelle append-only devono ricevere di nuovo il REVOKE).
--   psql -v ON_ERROR_STOP=1 -f 02_privileges.sql
\set ON_ERROR_STOP on
BEGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM app_runtime;

-- Tabelle append-only (audit, snapshot, ricevute): il runtime inserisce e legge soltanto.
REVOKE UPDATE, DELETE, TRUNCATE ON
  lesson_calendar_calendaraudit,
  governance_pathauditevent,
  scheduling_planningaudit,
  scheduling_planningsnapshot,
  governance_auditevent,
  privacy_retentionrun,
  identity_identityauditevent
FROM app_runtime;

-- La tabella delle migrazioni non è affare del runtime.
REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM app_runtime;
COMMIT;
