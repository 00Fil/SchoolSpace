-- Ruoli PostgreSQL a privilegio minimo (GAP-E08, guida tec4 §PostgreSQL).
-- Eseguire UNA volta per database come amministratore del servizio gestito, con psql:
--   psql -v ON_ERROR_STOP=1 -v db=ripetizioni \
--        -v pw_migrator="$PW_MIGRATOR" -v pw_runtime="$PW_RUNTIME" -v pw_ro="$PW_RO" \
--        -f 01_roles.sql
-- Le password arrivano dal secret manager: mai nel repository o nella shell history.
\set ON_ERROR_STOP on

-- Proprietario dello schema: NOLOGIN, usato solo tramite SET ROLE dal migratore.
SELECT 'CREATE ROLE app_owner NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_owner') \gexec

-- Job di migrazione: login, eredita app_owner. Django va avviato con
--   PGOPTIONS="-c role=app_owner" python manage.py migrate
-- così le tabelle nascono di proprietà di app_owner e non del migratore.
SELECT 'CREATE ROLE app_migrator LOGIN NOINHERIT IN ROLE app_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_migrator') \gexec
ALTER ROLE app_migrator PASSWORD :'pw_migrator';

-- Runtime web/worker: solo DML, nessun DDL, nessuna proprietà.
SELECT 'CREATE ROLE app_runtime LOGIN NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') \gexec
ALTER ROLE app_runtime PASSWORD :'pw_runtime';

-- Sola lettura per supporto e report.
SELECT 'CREATE ROLE app_readonly LOGIN NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_readonly') \gexec
ALTER ROLE app_readonly PASSWORD :'pw_ro';

-- Database e schema: nessuno crea oggetti tranne app_owner.
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO app_migrator, app_runtime, app_readonly;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO app_owner;
GRANT USAGE ON SCHEMA public TO app_runtime, app_readonly;

-- Privilegi di default per le tabelle create in futuro da app_owner.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO app_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Limiti di sicurezza (valori della guida; il worker solver può avere un ruolo dedicato).
ALTER ROLE app_runtime SET statement_timeout = '15s';
ALTER ROLE app_runtime SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE app_runtime SET lock_timeout = '5s';
ALTER ROLE app_readonly SET statement_timeout = '60s';
ALTER ROLE app_readonly SET default_transaction_read_only = on;
