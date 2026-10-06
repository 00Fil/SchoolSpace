from django.db import migrations


def seed(apps, schema_editor):
    """Aggiunge le categorie nuove della matrice (stato "da approvare"), idempotente."""
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


class Migration(migrations.Migration):
    dependencies = [("privacy", "0003_identity_invitations")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
