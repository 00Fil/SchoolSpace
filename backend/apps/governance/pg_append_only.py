"""Trigger PostgreSQL anti-modifica per audit e snapshot (GAP-E08).

Difesa in profondità rispetto al REVOKE dei privilegi (infra/postgres/02_privileges.sql):
UPDATE, DELETE e TRUNCATE falliscono anche per il proprietario, salvo la manutenzione
governata della retention, che richiede *entrambe* le condizioni:

* ruolo corrente membro del proprietario della tabella (app_owner), e
* ``SET LOCAL app.audit_maintenance = 'on'`` nella transazione.

Unica eccezione: TRUNCATE nei database di test di Django (nome ``test_*``), necessario al
flush dei TransactionTestCase. Il file infra/postgres/03_append_only_triggers.sql è generato da
questo modulo (``python manage.py governance_append_only_sql``) e un test ne verifica l'allineamento.
"""

# Tabelle protette dalla migrazione governance.0004 (elenco congelato).
INITIAL_TABLES = (
    "lesson_calendar_calendaraudit",
    "governance_pathauditevent",
    "scheduling_planningaudit",
    "scheduling_planningsnapshot",
    "governance_auditevent",
    "privacy_retentionrun",
)
# Aggiunta dalla migrazione governance.0005: sostituisce il trigger di s1 (che non
# consentiva la minimizzazione governata dell'IP richiesta dalla retention D09).
IDENTITY_AUDIT_TABLE = "identity_identityauditevent"
APPEND_ONLY_TABLES = INITIAL_TABLES + (IDENTITY_AUDIT_TABLE,)

S1_TRIGGER_DROP = (
    "DROP TRIGGER IF EXISTS identity_audit_no_update ON identity_identityauditevent;"
)
S1_TRIGGER_RESTORE = (
    "CREATE TRIGGER identity_audit_no_update BEFORE UPDATE OR DELETE ON "
    "identity_identityauditevent FOR EACH ROW EXECUTE FUNCTION "
    "identity_audit_append_only();"
)

FUNCTION = """CREATE OR REPLACE FUNCTION app_append_only_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE owner_name name;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO owner_name FROM pg_class c WHERE c.oid = TG_RELID;
  IF coalesce(current_setting('app.audit_maintenance', true), '') = 'on'
     AND pg_has_role(current_user, owner_name, 'MEMBER') THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'TRUNCATE' AND current_database() LIKE 'test\\_%' THEN
    RETURN NULL;
  END IF;
  RAISE EXCEPTION 'Tabella append-only %: % non consentito', TG_TABLE_NAME, TG_OP
    USING ERRCODE = '42501';
END $$;
"""


def install_sql(tables=APPEND_ONLY_TABLES):
    parts = [FUNCTION]
    for table in tables:
        parts.append(
            f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};\n"
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}\n"
            f"  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();\n"
            f"DROP TRIGGER IF EXISTS {table}_append_only_truncate ON {table};\n"
            f"CREATE TRIGGER {table}_append_only_truncate BEFORE TRUNCATE ON {table}\n"
            f"  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();\n"
        )
    return "\n".join(parts)


def remove_sql(tables=APPEND_ONLY_TABLES):
    parts = []
    for table in tables:
        parts.append(
            f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};\n"
            f"DROP TRIGGER IF EXISTS {table}_append_only_truncate ON {table};"
        )
    parts.append("DROP FUNCTION IF EXISTS app_append_only_guard();")
    return "\n".join(parts)


def script():
    """Script completo e idempotente per tutte le tabelle append-only."""
    header = (
        "-- GENERATO da apps/governance/pg_append_only.py: non modificare a mano.\n"
        "-- Trigger anti-modifica per audit e snapshot (GAP-E08). Idempotente.\n"
        "BEGIN;\n"
    )
    return header + install_sql() + S1_TRIGGER_DROP + "\nCOMMIT;\n"
