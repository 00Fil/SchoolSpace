from django.db import migrations


def seed(apps, schema_editor):
    """Matrice D09 con stato "da approvare": nessuna azione reale finché non approvata."""
    from apps.privacy.retention import DEFAULT_MATRIX

    Policy = apps.get_model("privacy", "RetentionPolicy")
    db = schema_editor.connection.alias
    for category, label, purpose, basis, days, action, backup, source in DEFAULT_MATRIX:
        Policy.objects.using(db).get_or_create(
            category=category,
            defaults=dict(
                label=label,
                purpose=purpose,
                legal_basis=basis,
                duration_days=days,
                action=str(action),
                backup_note=backup,
                source=source,
                status="PROPOSED",
            ),
        )


def unseed(apps, schema_editor):
    Policy = apps.get_model("privacy", "RetentionPolicy")
    Policy.objects.using(schema_editor.connection.alias).filter(
        status="PROPOSED", version=1
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("privacy", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
