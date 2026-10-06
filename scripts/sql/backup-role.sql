-- Ruolo dedicato al backup logico (GAP-L01), separato da app_readonly (che non legge le
-- sequenze e ha statement_timeout 60 s, insufficiente per pg_dump).
-- Eseguire una volta come amministratore del servizio gestito:
--   psql -v ON_ERROR_STOP=1 -v db=ripetizioni -v pw_backup="$PW_BACKUP" -f scripts/sql/backup-role.sql
\set ON_ERROR_STOP on
SELECT 'CREATE ROLE app_backup LOGIN NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backup') \gexec
ALTER ROLE app_backup PASSWORD :'pw_backup';
-- pg_read_all_data (PostgreSQL >= 14): SELECT su tabelle e sequenze, nessuna scrittura.
-- NOINHERIT + SET ROLE automatico: il privilegio vale solo per le sessioni di backup.
GRANT pg_read_all_data TO app_backup;
ALTER ROLE app_backup SET role = 'pg_read_all_data';
ALTER ROLE app_backup SET default_transaction_read_only = on;
ALTER ROLE app_backup SET statement_timeout = 0;
ALTER ROLE app_backup SET idle_in_transaction_session_timeout = '10min';
GRANT CONNECT ON DATABASE :"db" TO app_backup;
