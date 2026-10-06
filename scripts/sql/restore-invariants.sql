-- Invarianti strutturali dopo un restore (GAP-L03). Ogni riga restituita è un problema.
-- Eseguire sul database ripristinato:  psql -X -At -v ON_ERROR_STOP=1 -f restore-invariants.sql
-- Le invarianti applicative (catene audit, ledger privacy, sovrapposizioni, consegne)
-- sono verificate da `manage.py post_restore_reconcile`.
\set ON_ERROR_STOP on

-- 1. Estensione necessaria al vincolo di esclusione delle prenotazioni.
SELECT 'missing extension btree_gist'
WHERE NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist');

-- 2. Migrazioni presenti (dump non vuoto e coerente con il codice).
SELECT 'django_migrations is empty'
WHERE NOT EXISTS (SELECT 1 FROM django_migrations);

-- 3. Tabelle essenziali presenti.
SELECT 'missing table ' || t
FROM unnest(ARRAY[
  'identity_account', 'identity_rolegrant', 'governance_auditevent',
  'lesson_calendar_lessonoccurrence', 'lesson_calendar_resourcebooking',
  'scheduling_schedulerun', 'scheduling_planningsnapshot', 'privacy_privacyrequest',
  'communications_outboxevent', 'communications_delivery']) AS t
WHERE to_regclass(t) IS NULL;

-- 4. Vincoli di esclusione (no overlap) ancora presenti e validi.
SELECT 'no exclusion constraint on ' || t
FROM unnest(ARRAY['lesson_calendar_resourcebooking']) AS t
WHERE to_regclass(t) IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM pg_constraint c
  WHERE c.conrelid = to_regclass(t) AND c.contype = 'x' AND c.convalidated);

-- 5. Nessun vincolo o indice lasciato invalido dal restore.
SELECT 'invalid constraint ' || conname FROM pg_constraint
WHERE NOT convalidated AND connamespace = 'public'::regnamespace;
SELECT 'invalid index ' || indexrelid::regclass FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
WHERE NOT i.indisvalid AND c.relnamespace = 'public'::regnamespace;

-- 6. Sequenze non indietro rispetto ai dati (un INSERT successivo non deve collidere).
-- Le chiavi primarie sono quasi tutte UUID: si controllano solo le identity/serial.
SELECT format('sequence %s behind %s.%s', s.seq, s.tbl, s.col)
FROM (
  SELECT pg_get_serial_sequence(format('%I', c.relname), a.attname) AS seq,
         c.relname AS tbl, a.attname AS col
  FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
  WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
    AND a.attnum > 0 AND NOT a.attisdropped
    AND pg_get_serial_sequence(format('%I', c.relname), a.attname) IS NOT NULL
) s
CROSS JOIN LATERAL (
  SELECT (xpath('/row/m/text()', query_to_xml(
    format('SELECT max(%I) AS m FROM %I', s.col, s.tbl), false, true, '')))[1]::text::bigint AS mx
) m
CROSS JOIN LATERAL (
  SELECT (xpath('/row/v/text()', query_to_xml(
    format('SELECT last_value AS v FROM %s', s.seq), false, true, '')))[1]::text::bigint AS lv
) l
WHERE m.mx IS NOT NULL AND l.lv < m.mx;
