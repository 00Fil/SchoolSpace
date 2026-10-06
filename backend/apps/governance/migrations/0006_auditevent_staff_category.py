# P1 (guida v3.1): categoria di audit per tutor e utenti del centro.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("governance", "0005_identity_audit_append_only")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="category",
            field=models.CharField(
                choices=[
                    ("FAMILY", "Famiglie e studenti"),
                    ("GUARDIANSHIP", "Deleghe"),
                    ("INVITE", "Inviti"),
                    ("EXPORT", "Esportazioni"),
                    ("IMPORT", "Importazioni"),
                    ("PRIVACY", "Diritti degli interessati"),
                    ("RETENTION", "Conservazione"),
                    ("ADMIN", "Amministrazione di emergenza"),
                    ("STAFF", "Tutor e utenti del centro"),
                ],
                max_length=16,
            ),
        ),
    ]
