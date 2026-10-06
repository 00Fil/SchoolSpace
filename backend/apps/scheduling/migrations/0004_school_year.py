# P2 (guida v3.1): anno scolastico e periodi di studio.
import uuid

import django.db.models.deletion
from django.db import migrations, models

KINDS = [
    ("START", "Inizio lezioni"),
    ("CHRISTMAS", "Pausa natalizia"),
    ("EASTER", "Pausa pasquale"),
    ("SUMMER", "Pausa estiva"),
    ("BREAK", "Altra pausa"),
    ("RECOVERY", "Periodo per i recuperi"),
]


class Migration(migrations.Migration):
    dependencies = [("scheduling", "0003_v05_policy_series")]

    operations = [
        migrations.CreateModel(
            name="SchoolYear",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("name", models.CharField(max_length=40, unique=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["-start_date"]},
        ),
        migrations.AddConstraint(
            model_name="schoolyear",
            constraint=models.CheckConstraint(condition=models.Q(end_date__gt=models.F("start_date")), name="school_year_positive"),
        ),
        migrations.CreateModel(
            name="StudyPeriod",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("kind", models.CharField(choices=KINDS, max_length=10)),
                ("label", models.CharField(blank=True, max_length=80)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("closure", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="scheduling.closure")),
                ("school_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="periods", to="scheduling.schoolyear")),
            ],
            options={"ordering": ["start_date"]},
        ),
        migrations.AddConstraint(
            model_name="studyperiod",
            constraint=models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="study_period_positive"),
        ),
    ]
