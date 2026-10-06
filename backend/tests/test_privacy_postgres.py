"""GAP-E08: ruoli a privilegio minimo e audit/snapshot append-only anche contro SQL diretto.

I test statici girano ovunque; quelli sui trigger richiedono PostgreSQL reale.
"""

from pathlib import Path

import pytest
from django.db import connection, transaction

from apps.governance.audit import record
from apps.governance.pg_append_only import APPEND_ONLY_TABLES, script

INFRA = Path(__file__).resolve().parents[2] / "infra" / "postgres"
REQUIRED = (
    "lesson_calendar_calendaraudit",
    "governance_pathauditevent",
    "scheduling_planningaudit",
    "scheduling_planningsnapshot",
)


def test_generated_trigger_script_is_in_sync():
    assert (INFRA / "03_append_only_triggers.sql").read_text() == script()


def test_table_names_match_models():
    from django.apps import apps

    tables = {m._meta.db_table for m in apps.get_models()}
    assert set(APPEND_ONLY_TABLES) <= tables
    assert set(REQUIRED) <= set(APPEND_ONLY_TABLES)


def test_role_scripts_cover_least_privilege():
    roles = (INFRA / "01_roles.sql").read_text()
    for role in ("app_owner", "app_migrator", "app_runtime", "app_readonly"):
        assert role in roles
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in roles
    assert "statement_timeout" in roles and "PASSWORD :'pw_runtime'" in roles
    privileges = (INFRA / "02_privileges.sql").read_text()
    revoke = privileges[privileges.index("REVOKE UPDATE, DELETE, TRUNCATE ON") :]
    for table in APPEND_ONLY_TABLES:
        assert table in revoke.split("FROM app_runtime")[0]
    verify = (INFRA / "04_verify.sql").read_text()
    for table in APPEND_ONLY_TABLES:
        assert table in verify


pg_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires actual PostgreSQL triggers and roles",
)


@pg_only
@pytest.mark.django_db
@pytest.mark.parametrize("statement", ["UPDATE", "DELETE"])
def test_postgres_trigger_blocks_raw_modification(statement):
    from apps.identity.models import Account

    actor = Account.objects.create_user(
        username="pg-audit", email="pg-audit@example.invalid", password="x-Synthetic-1"
    )
    event = record("ADMIN", "PG", actor=actor)
    sql = {
        "UPDATE": "UPDATE governance_auditevent SET operation='X' WHERE id=%s",
        "DELETE": "DELETE FROM governance_auditevent WHERE id=%s",
    }[statement]
    from django.db import DatabaseError

    with pytest.raises(DatabaseError) as error:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql, [event.pk.hex])
    assert error.value.__cause__.sqlstate == "42501"


@pg_only
@pytest.mark.django_db
def test_postgres_triggers_installed_on_all_tables():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "WHERE t.tgname = c.relname || '_append_only'"
        )
        installed = {row[0] for row in cursor.fetchall()}
    assert set(APPEND_ONLY_TABLES) <= installed


@pg_only
@pytest.mark.django_db
def test_postgres_owner_maintenance_mode_allows_governed_minimization():
    from apps.identity.models import Account
    from apps.governance.models import AuditEvent

    actor = Account.objects.create_user(
        username="pg-owner", email="pg-owner@example.invalid", password="x-Synthetic-1"
    )
    event = record("ADMIN", "PG", actor=actor, details={"a": 1})
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL app.audit_maintenance = 'on'")
        cursor.execute(
            "UPDATE governance_auditevent SET details='{}'::jsonb WHERE id=%s",
            [event.pk.hex],
        )
    assert AuditEvent.objects.get(pk=event.pk).details == {}
