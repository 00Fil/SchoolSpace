-- Verifiche post-deploy (eseguire come amministratore o app_readonly). Tutte le query
-- devono restituire ZERO righe; qualsiasi riga è una non conformità GAP-E08.
\set ON_ERROR_STOP on

-- 1. Il runtime non possiede oggetti e non può creare nello schema.
SELECT 'runtime owns ' || c.relname AS problem FROM pg_class c
JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'app_runtime';
SELECT 'runtime can CREATE in public' AS problem
WHERE has_schema_privilege('app_runtime', 'public', 'CREATE');

-- 2. Nessun UPDATE/DELETE/TRUNCATE del runtime sulle tabelle append-only.
SELECT 'runtime has ' || p.priv || ' on ' || t.tbl AS problem
FROM unnest(ARRAY['lesson_calendar_calendaraudit','governance_pathauditevent',
  'scheduling_planningaudit','scheduling_planningsnapshot','governance_auditevent',
  'privacy_retentionrun','identity_identityauditevent']) AS t(tbl)
CROSS JOIN unnest(ARRAY['UPDATE','DELETE','TRUNCATE']) AS p(priv)
WHERE to_regclass(t.tbl) IS NOT NULL AND has_table_privilege('app_runtime', t.tbl, p.priv);

-- 3. Trigger anti-modifica presenti e abilitati.
SELECT 'missing trigger on ' || t.tbl AS problem
FROM unnest(ARRAY['lesson_calendar_calendaraudit','governance_pathauditevent',
  'scheduling_planningaudit','scheduling_planningsnapshot','governance_auditevent',
  'privacy_retentionrun','identity_identityauditevent']) AS t(tbl)
WHERE to_regclass(t.tbl) IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM pg_trigger g WHERE g.tgrelid = to_regclass(t.tbl)
  AND g.tgname = t.tbl || '_append_only' AND g.tgenabled <> 'D');

-- 4. Il ruolo di sola lettura non scrive.
SELECT 'readonly can write ' || c.relname AS problem FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
WHERE c.relkind = 'r' AND (has_table_privilege('app_readonly', c.oid, 'INSERT')
  OR has_table_privilege('app_readonly', c.oid, 'UPDATE')
  OR has_table_privilege('app_readonly', c.oid, 'DELETE'));
