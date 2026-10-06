from django.db import models
from apps.education.models import Entity, Student, Tutor


class AvailabilityRule(Entity):
    tutor = models.ForeignKey(Tutor, on_delete=models.PROTECT, null=True, blank=True)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    weekday = models.PositiveSmallIntegerField(help_text="0=lunedì, 6=domenica")
    start_time = models.TimeField()
    end_time = models.TimeField()
    period_start = models.DateField()
    period_end = models.DateField()
    timezone = models.CharField(max_length=64, default="Europe/Rome")
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    location = models.CharField(
        max_length=8, choices=[("ON_SITE", "Sede"), ("REMOTE", "Remoto")]
    )
    status = models.CharField(
        max_length=8,
        choices=[
            ("DRAFT", "Bozza"),
            ("APPROVED", "Approvata"),
            ("REVOKED", "Revocata"),
        ],
        default="DRAFT",
    )
    author = models.ForeignKey("identity.Account", on_delete=models.PROTECT)
    approved_by = models.ForeignKey(
        "identity.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_availability_rules",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tutor__isnull=False, student__isnull=True)
                    | models.Q(tutor__isnull=True, student__isnull=False)
                ),
                name="availability_subject_xor",
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__lte=6), name="availability_weekday"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="availability_time_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="availability_date_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(mode="ONLINE")
                    | models.Q(mode="IN_PERSON", location="ON_SITE")
                ),
                name="availability_mode_location",
            ),
        ]


class AvailabilityDeclaration(Entity):
    tutor = models.OneToOneField(Tutor, on_delete=models.PROTECT, null=True, blank=True)
    student = models.OneToOneField(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    state = models.CharField(
        max_length=16,
        choices=[
            ("APPROVED", "Dati approvati"),
            ("DECLARED_NONE", "Nessuna disponibilità"),
            ("UNKNOWN", "Dati incompleti"),
        ],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tutor__isnull=False, student__isnull=True)
                    | models.Q(tutor__isnull=True, student__isnull=False)
                ),
                name="availability_declaration_xor",
            )
        ]


class AvailabilityException(Entity):
    tutor = models.ForeignKey(Tutor, on_delete=models.PROTECT, null=True, blank=True)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    location = models.CharField(
        max_length=8, choices=[("ON_SITE", "Sede"), ("REMOTE", "Remoto")]
    )
    kind = models.CharField(
        max_length=20,
        choices=[("ADD_AVAILABLE", "Aggiunta"), ("REMOVE_AVAILABLE", "Rimozione")],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tutor__isnull=False, student__isnull=True)
                    | models.Q(tutor__isnull=True, student__isnull=False)
                ),
                name="availability_exception_xor",
            ),
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="exception_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(mode="ONLINE")
                | models.Q(mode="IN_PERSON", location="ON_SITE"),
                name="exception_location",
            ),
        ]


class AvailabilityConflict(Entity):
    tutor = models.ForeignKey(Tutor, on_delete=models.PROTECT, null=True, blank=True)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    reason = models.CharField(max_length=160)
    open = models.BooleanField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tutor__isnull=False, student__isnull=True)
                    | models.Q(tutor__isnull=True, student__isnull=False)
                ),
                name="availability_conflict_xor",
            )
        ]
