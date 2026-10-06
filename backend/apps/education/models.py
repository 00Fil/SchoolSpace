import uuid
from django.conf import settings
from django.db import models


from apps.scheduling.revision import TrackedQuerySet, tracked_save


class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    objects = TrackedQuerySet.as_manager()

    def save(self, *args, **kwargs):
        return tracked_save(self, super().save, args, kwargs)

    def delete(self, *args, **kwargs):
        return type(self).objects.filter(pk=self.pk).delete()

    class Meta:
        abstract = True


class Family(Entity):
    reference = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.reference


class Student(Entity):
    display_name = models.CharField(max_length=120)
    family = models.ForeignKey(Family, on_delete=models.PROTECT)
    level = models.CharField(max_length=60, blank=True)
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name


class GuardianLink(Entity):
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="guardian_links",
    )
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="guardian_links"
    )
    can_view = models.BooleanField(default=True)
    can_manage_availability = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="guardian_valid_period",
            )
        ]


class Tutor(Entity):
    # P1/T2: il centro crea il tutor prima dell'account; il collegamento avviene
    # all'accettazione dell'invito di ruolo TUTOR (stessa email).
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tutor_profile",
        null=True,
        blank=True,
    )
    display_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name


class Subject(Entity):
    name = models.CharField(max_length=80, unique=True)
    # v0.9.6: scheda materia. Una materia archiviata resta nello storico
    # (richieste, competenze, percorsi) ma non si propone per nuove richieste.
    description = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Resource(Entity):
    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(
        max_length=16, choices=[("SPACE", "Spazio"), ("VIDEO_CHANNEL", "Canale video")]
    )
    student_capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="SPACE",
                        student_capacity__gte=1,
                        student_capacity__isnull=False,
                    )
                    | models.Q(kind="VIDEO_CHANNEL", student_capacity__isnull=True)
                ),
                name="resource_capacity_by_kind",
            )
        ]


class TeachingRequest(Entity):
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    group = models.ForeignKey(
        "TeachingGroup", on_delete=models.PROTECT, null=True, blank=True
    )
    curriculum_block = models.OneToOneField(
        "CurriculumBlock",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="derived_request",
    )
    source_fingerprint = models.CharField(max_length=64, blank=True)
    mode = models.CharField(
        max_length=9,
        choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")],
        blank=True,
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    duration_minutes = models.PositiveSmallIntegerField(
        choices=[(60, "60"), (90, "90"), (120, "120")]
    )
    sessions_per_week = models.PositiveSmallIntegerField(default=1)
    priority = models.CharField(
        max_length=2, choices=[("P0", "P0"), ("P1", "P1"), ("P2", "P2")], default="P1"
    )
    mandatory = models.BooleanField(default=False)
    period_start = models.DateField()
    period_end = models.DateField()
    # v0.9.4: richieste inviate dalle famiglie, approvazione del centro e scelta
    # del tutor. Il motore usa solo le richieste APPROVED.
    status = models.CharField(
        max_length=10,
        choices=[
            ("PENDING", "Da approvare"),
            ("APPROVED", "Approvata"),
            ("REJECTED", "Rifiutata"),
            ("WITHDRAWN", "Ritirata"),
        ],
        default="APPROVED",
    )
    origin = models.CharField(
        max_length=8,
        choices=[("CENTER", "Centro"), ("GUARDIAN", "Famiglia")],
        default="CENTER",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_requests",
    )
    tutor_choice = models.CharField(
        max_length=9,
        choices=[
            ("ANY", "Qualsiasi tutor competente"),
            ("PREFERRED", "Tutor preferito"),
            ("REQUIRED", "Tutor obbligatorio"),
        ],
        default="ANY",
    )
    preferred_tutors = models.ManyToManyField(
        "Tutor", blank=True, related_name="preferred_in_requests"
    )
    notes = models.CharField(max_length=500, blank=True)
    # v0.9.6: tipo di richiesta.
    # - SINGLE: una sola lezione. Con fixed_time e period_start == period_end è
    #   piazzata dal centro in un giorno e orario precisi; con il solo giorno il
    #   motore cerca l'orario in quel giorno; con una settimana (lunedì–domenica)
    #   cerca lo spazio nella settimana.
    # - SERIES: lezioni ricorrenti, sessions_per_week ogni settimana nel periodo,
    #   sempre con lo stesso tutor (REQUIRED).
    # - WEEKLY: domanda settimanale storica e derivata dai percorsi parentali.
    kind = models.CharField(
        max_length=6,
        choices=[
            ("SINGLE", "Lezione singola"),
            ("SERIES", "Ricorrente con lo stesso tutor"),
            ("WEEKLY", "Settimanale sul periodo"),
        ],
        default="WEEKLY",
    )
    fixed_time = models.TimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # v0.9.9: dopo l'approvazione il motore colloca subito le lezioni della richiesta
    # (bozza dedicata, ``AutoPlan.request``). Il centro verifica l'elenco, risolve le
    # incongruenze e conferma: solo allora la richiesta è «completata».
    planning_state = models.CharField(
        max_length=6,
        choices=[("", "Non pianificata"), ("REVIEW", "Da verificare"), ("DONE", "Completata")],
        blank=True,
        default="",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    # v0.9.9: lezioni di gruppo create dal centro. ``student`` resta il primo
    # partecipante (vincolo student XOR group); l'elenco completo è in
    # ``participants`` (RequestParticipant).
    group_label = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(student__isnull=False, group__isnull=True)
                    | models.Q(student__isnull=True, group__isnull=False)
                ),
                name="request_target_xor",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="request_valid_period",
            ),
            models.CheckConstraint(
                condition=models.Q(sessions_per_week__gte=1),
                name="request_positive_sessions",
            ),
            models.CheckConstraint(
                condition=models.Q(fixed_time__isnull=True)
                | models.Q(kind="SINGLE", period_end=models.F("period_start")),
                name="request_fixed_time_single_day",
            ),
        ]


class LearningPath(Entity):
    """Internal school-year organization, not a legally recognized qualification."""

    title = models.CharField(max_length=140)
    kind = models.CharField(
        max_length=20,
        choices=[
            ("HOME_EDUCATION", "Programma scolastico completo"),
            ("TUTORING", "Ripetizioni"),
        ],
    )
    academic_year = models.CharField(max_length=30)
    level = models.CharField(max_length=80)
    period_start = models.DateField()
    period_end = models.DateField()
    required_subjects = models.ManyToManyField(Subject, related_name="learning_paths")
    curriculum_version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="path_valid_period",
            )
        ]

    def __str__(self):
        return self.title


class PathEnrollment(Entity):
    path = models.ForeignKey(
        LearningPath, on_delete=models.PROTECT, related_name="enrollments"
    )
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="path_enrollments"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path", "student"], name="path_student_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="enrollment_valid_period",
            ),
        ]


class TeachingGroup(Entity):
    path = models.ForeignKey(
        LearningPath, on_delete=models.PROTECT, related_name="groups"
    )
    name = models.CharField(max_length=100)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    online_capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    approved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(online_capacity__isnull=True)
                | models.Q(online_capacity__gte=2),
                name="group_online_capacity",
            )
        ]

    def __str__(self):
        return self.name


class GroupMembership(Entity):
    group = models.ForeignKey(
        TeachingGroup, on_delete=models.PROTECT, related_name="memberships"
    )
    student = models.ForeignKey(Student, on_delete=models.PROTECT)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "student"], name="group_student_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="membership_valid_period",
            ),
        ]


class CurriculumBlock(Entity):
    path = models.ForeignKey(
        LearningPath, on_delete=models.PROTECT, related_name="blocks"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    objective = models.CharField(max_length=300)
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, null=True, blank=True
    )
    group = models.ForeignKey(
        TeachingGroup, on_delete=models.PROTECT, null=True, blank=True
    )
    period_start = models.DateField()
    period_end = models.DateField()
    minutes_per_week = models.PositiveIntegerField()
    duration_minutes = models.PositiveSmallIntegerField(
        choices=[(60, "60"), (90, "90"), (120, "120")]
    )
    sessions_per_week = models.PositiveSmallIntegerField()
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    # These choices must be explicitly supplied; no implicit priority or mandatory policy.
    priority = models.CharField(
        max_length=2, choices=[("P0", "P0"), ("P1", "P1"), ("P2", "P2")]
    )
    mandatory = models.BooleanField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(student__isnull=False, group__isnull=True)
                    | models.Q(student__isnull=True, group__isnull=False)
                ),
                name="curriculum_target_xor",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="curriculum_valid_period",
            ),
            models.CheckConstraint(
                condition=models.Q(sessions_per_week__gte=1),
                name="curriculum_positive_sessions",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    minutes_per_week=models.F("duration_minutes")
                    * models.F("sessions_per_week")
                ),
                name="curriculum_minutes_match",
            ),
        ]


class RequestParticipant(models.Model):
    objects = TrackedQuerySet.as_manager()

    def save(self, *args, **kwargs):
        from django.db import transaction
        from apps.scheduling.revision import lock_revision, bump_revision

        with transaction.atomic():
            lock_revision()
            result = super().save(*args, **kwargs)
            bump_revision()
            return result

    def delete(self, *args, **kwargs):
        return type(self).objects.filter(pk=self.pk).delete()

    request = models.ForeignKey(
        TeachingRequest, on_delete=models.PROTECT, related_name="participants"
    )
    student = models.ForeignKey(Student, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "student"], name="request_participant_unique"
            )
        ]
