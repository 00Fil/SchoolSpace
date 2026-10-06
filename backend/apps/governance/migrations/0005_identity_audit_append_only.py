from django.db import migrations

from apps.governance.pg_append_only import (
    FUNCTION,
    IDENTITY_AUDIT_TABLE,
    S1_TRIGGER_DROP,
    S1_TRIGGER_RESTORE,
    install_sql,
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        sql = install_sql((IDENTITY_AUDIT_TABLE,)).replace(FUNCTION, "")
        schema_editor.execute(S1_TRIGGER_DROP + "\n" + sql, params=None)


def remove(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        t = IDENTITY_AUDIT_TABLE
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {t}_append_only ON {t};\n"
            f"DROP TRIGGER IF EXISTS {t}_append_only_truncate ON {t};\n"
            + S1_TRIGGER_RESTORE,
            params=None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("governance", "0004_postgres_append_only"),
        ("identity", "0003_security_baseline"),
    ]
    operations = [migrations.RunPython(install, remove, elidable=False)]
