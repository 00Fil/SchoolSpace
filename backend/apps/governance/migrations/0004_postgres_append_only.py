from django.db import migrations

from apps.governance.pg_append_only import INITIAL_TABLES, install_sql, remove_sql


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(install_sql(INITIAL_TABLES), params=None)


def remove(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(remove_sql(INITIAL_TABLES), params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("governance", "0003_auditevent"),
        ("lesson_calendar", "0001_initial"),
        ("scheduling", "0001_initial"),
        ("privacy", "0001_initial"),
    ]
    operations = [migrations.RunPython(install, remove, elidable=False)]
