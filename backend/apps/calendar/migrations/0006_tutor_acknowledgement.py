"""P3: presa visione e controproposta del tutor (DC-APPROVAZIONI)."""

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("lesson_calendar", "0005_postgres_protection_v2"),
        ("education", "0005_tutor_registry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TutorAcknowledgement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("state", models.CharField(choices=[("PENDING", "PENDING"), ("ACKNOWLEDGED", "ACKNOWLEDGED"), ("COUNTER", "COUNTER"), ("RESOLVED", "RESOLVED")], default="PENDING", max_length=12)),
                ("note", models.CharField(blank=True, default="", max_length=500)),
                ("items", models.JSONField(default=list)),
                ("decision", models.CharField(blank=True, default="", max_length=14)),
                ("decision_note", models.CharField(blank=True, default="", max_length=200)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("publication", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="acknowledgements", to="lesson_calendar.publication")),
                ("tutor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="education.tutor")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("publication", "tutor"), name="unique_ack_publication_tutor"),
                    models.CheckConstraint(condition=models.Q(("state__in", ["PENDING", "ACKNOWLEDGED", "COUNTER", "RESOLVED"])), name="tutor_ack_state_enum"),
                ],
            },
        ),
    ]
