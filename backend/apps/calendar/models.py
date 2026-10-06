import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class CalendarResource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(
        max_length=10,
        choices=[
            ("TUTOR", "Tutor"),
            ("STUDENT", "Studente"),
            ("RESOURCE", "Spazio/video"),
        ],
    )
    tutor = models.OneToOneField("education.Tutor", on_delete=models.PROTECT, null=True)
    student = models.OneToOneField(
        "education.Student", on_delete=models.PROTECT, null=True
    )
    resource = models.OneToOneField(
        "education.Resource", on_delete=models.PROTECT, null=True
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="TUTOR",
                        tutor__isnull=False,
                        student__isnull=True,
                        resource__isnull=True,
                    )
                    | models.Q(
                        kind="STUDENT",
                        student__isnull=False,
                        tutor__isnull=True,
                        resource__isnull=True,
                    )
                    | models.Q(
                        kind="RESOURCE",
                        resource__isnull=False,
                        tutor__isnull=True,
                        student__isnull=True,
                    )
                ),
                name="calendar_resource_exact_subject",
            )
        ]


class Publication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.OneToOneField(
        "scheduling.SchedulePlan", on_delete=models.PROTECT, related_name="publication"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revision_after = models.PositiveBigIntegerField()
    accepted_unassigned = models.JSONField(default=list)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LessonOccurrence(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    demand = models.ForeignKey("scheduling.DemandUnit", on_delete=models.PROTECT)
    publication = models.ForeignKey(Publication, on_delete=models.PROTECT)
    tutor = models.ForeignKey("education.Tutor", on_delete=models.PROTECT)
    subject = models.ForeignKey("education.Subject", on_delete=models.PROTECT)
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    location = models.CharField(
        max_length=8, choices=[("ON_SITE", "Sede"), ("REMOTE", "Remoto")]
    )
    space = models.ForeignKey(
        "education.Resource",
        on_delete=models.PROTECT,
        null=True,
        related_name="space_lessons",
    )
    video = models.ForeignKey(
        "education.Resource",
        on_delete=models.PROTECT,
        null=True,
        related_name="video_lessons",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    tutor_occupied_until = models.DateTimeField()
    space_occupied_until = models.DateTimeField(null=True)
    video_occupied_until = models.DateTimeField(null=True)
    state = models.CharField(
        max_length=9,
        default="PUBLISHED",
        choices=[
            ("PUBLISHED", "Pubblicata sperimentale"),
            ("CANCELLED", "Cancellata"),
            ("COMPLETED", "Conclusa"),
        ],
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # --- s2-calendario: serie, chiave stabile dell'occorrenza, recupero ---
    series = models.ForeignKey(
        "LessonSeries",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lessons",
    )
    recurrence_key = models.CharField(max_length=120, null=True, blank=True)
    recovery = models.ForeignKey(
        "RecoveryObligation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="makeup_lessons",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["PUBLISHED", "CANCELLED", "COMPLETED"],
                    mode__in=["IN_PERSON", "ONLINE"],
                    location__in=["ON_SITE", "REMOTE"],
                ),
                name="calendar_lesson_enum",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    end_at__gt=models.F("start_at"),
                    tutor_occupied_until__gte=models.F("end_at"),
                ),
                name="lesson_positive_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(mode="ONLINE")
                | models.Q(mode="IN_PERSON", location="ON_SITE", space__isnull=False),
                name="lesson_presence_space",
            ),
            models.UniqueConstraint(
                fields=["demand"],
                condition=models.Q(state="PUBLISHED"),
                name="one_active_lesson_per_demand",
            ),
            models.UniqueConstraint(
                fields=["recurrence_key"],
                condition=models.Q(recurrence_key__isnull=False),
                name="unique_lesson_recurrence_key",
            ),
            models.UniqueConstraint(
                fields=["recovery"],
                condition=models.Q(
                    recovery__isnull=False, state__in=["PUBLISHED", "COMPLETED"]
                ),
                name="one_active_makeup_per_obligation",
            ),
            models.CheckConstraint(
                condition=models.Q(state="COMPLETED", completed_at__isnull=False)
                | (~models.Q(state="COMPLETED") & models.Q(completed_at__isnull=True)),
                name="lesson_completed_at_state",
            ),
        ]


class LessonParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        LessonOccurrence, on_delete=models.PROTECT, related_name="participants"
    )
    student = models.ForeignKey("education.Student", on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "student"], name="unique_lesson_student"
            )
        ]


class ResourceBooking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        LessonOccurrence, on_delete=models.PROTECT, related_name="bookings"
    )
    resource = models.ForeignKey(CalendarResource, on_delete=models.PROTECT)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="booking_positive_interval",
            ),
            models.UniqueConstraint(
                fields=["lesson", "resource"], name="unique_lesson_booking"
            ),
        ]
        indexes = [models.Index(fields=["resource", "start_at", "end_at"])]


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Registro append-only")

    def delete(self):
        raise ValidationError("Registro append-only")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Registro append-only")


class AppendOnly(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Registro append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registro append-only")

    class Meta:
        abstract = True


class CalendarAudit(AppendOnly):
    """Append-only: su PostgreSQL un trigger respinge UPDATE/DELETE (migrazione 0005)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    # Valorizzato solo per job di sistema (es. rilevazione conflitti), senza attore umano.
    system_actor = models.CharField(max_length=40, blank=True, default="")
    operation = models.CharField(max_length=30)
    object_type = models.CharField(max_length=30, blank=True, default="")
    object_id = models.UUIDField(null=True, blank=True)
    lesson = models.ForeignKey(LessonOccurrence, on_delete=models.PROTECT, null=True)
    publication = models.ForeignKey(Publication, on_delete=models.PROTECT, null=True)
    reason = models.CharField(max_length=200)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(actor__isnull=False) | ~models.Q(system_actor=""),
                name="calendar_audit_actor_required",
            )
        ]


class CalendarEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_key = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=30)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    # No recipient/email delivery in this increment; minimal domain event registry only.


# --- s2-calendario (GAP-E01..E07) -------------------------------------------------

LESSON_MODES = [("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
LESSON_LOCATIONS = [("ON_SITE", "Sede"), ("REMOTE", "Remoto")]


class LessonSeries(models.Model):
    """Segmento di una serie settimanale (sottoinsieme RRULE: WEEKLY, INTERVAL, BYDAY, UNTIL).

    Una modifica "questa e successive" chiude il segmento (``until_date``) e crea un
    nuovo segmento con lo stesso ``root``: le chiavi ``<root>/<data nominale>`` delle
    occorrenze restano stabili.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    root = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    request = models.ForeignKey(
        "education.TeachingRequest",
        on_delete=models.PROTECT,
        related_name="calendar_series",
    )
    timezone = models.CharField(max_length=64, default="Europe/Rome")
    start_date = models.DateField(help_text="DTSTART locale (data)")
    start_time = models.TimeField(help_text="DTSTART locale (ora)")
    duration_minutes = models.PositiveSmallIntegerField()
    rrule = models.CharField(max_length=200)
    until_date = models.DateField(help_text="Ultima data locale inclusa")
    exdates = models.JSONField(default=list)
    overrides = models.JSONField(default=dict)
    # Date nominali di questo segmento già rappresentate da lezioni portate dal
    # segmento precedente ("questa e successive"): non vanno proiettate di nuovo.
    carried = models.JSONField(default=dict)
    tutor = models.ForeignKey("education.Tutor", on_delete=models.PROTECT)
    mode = models.CharField(max_length=9, choices=LESSON_MODES)
    location = models.CharField(max_length=8, choices=LESSON_LOCATIONS)
    space = models.ForeignKey(
        "education.Resource",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    video = models.ForeignKey(
        "education.Resource",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    state = models.CharField(
        max_length=10,
        default="ACTIVE",
        choices=[("ACTIVE", "Attiva"), ("CLOSED", "Chiusa/segmentata")],
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(until_date__gte=models.F("start_date")),
                name="series_period_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(timezone="Europe/Rome"),
                name="series_timezone_supported",
            ),
            models.CheckConstraint(
                condition=models.Q(mode="ONLINE")
                | models.Q(mode="IN_PERSON", location="ON_SITE", space__isnull=False),
                name="series_presence_space",
            ),
        ]

    @property
    def root_id_value(self):
        return self.root_id or self.id


class RecoveryObligation(models.Model):
    """Obbligo di recupero con identità canonica derivata dalla lezione d'origine."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canonical_key = models.CharField(max_length=120, unique=True)
    origin_lesson = models.OneToOneField(
        LessonOccurrence, on_delete=models.PROTECT, related_name="recovery_obligation"
    )
    demand = models.ForeignKey("scheduling.DemandUnit", on_delete=models.PROTECT)
    participants = models.JSONField(default=list)
    minutes_remaining = models.PositiveSmallIntegerField()
    cause = models.CharField(
        max_length=20,
        choices=[
            ("CENTER_CANCELLATION", "Cancellazione del centro"),
            ("FAMILY_REQUEST", "Richiesta della famiglia"),
            ("TUTOR_ABSENCE", "Assenza del tutor"),
            ("STUDENT_ABSENCE", "Assenza dello studente"),
            ("CLOSURE", "Chiusura"),
        ],
    )
    state = models.CharField(
        max_length=10,
        default="OPEN",
        choices=[
            ("OPEN", "Da recuperare"),
            ("SCHEDULED", "Recupero pubblicato"),
            ("FULFILLED", "Recuperato"),
            ("WAIVED", "Rinunciato"),
        ],
    )
    reason = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minutes_remaining__gt=0),
                name="recovery_minutes_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["OPEN", "SCHEDULED", "FULFILLED", "WAIVED"]
                ),
                name="recovery_state_enum",
            ),
        ]


ATTENDANCE_STATES = [
    ("PRESENT", "Presente"),
    ("ABSENT", "Assente"),
    ("JUSTIFIED", "Assente giustificato"),
    ("NOT_RECORDED", "Non rilevato"),
]


class Attendance(models.Model):
    """Presenza per singolo partecipante, distinta dallo stato della lezione (FR21)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.OneToOneField(
        LessonParticipant, on_delete=models.PROTECT, related_name="attendance"
    )
    lesson = models.ForeignKey(
        LessonOccurrence, on_delete=models.PROTECT, related_name="attendances"
    )
    status = models.CharField(max_length=12, choices=ATTENDANCE_STATES)
    minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["PRESENT", "ABSENT", "JUSTIFIED", "NOT_RECORDED"]
                ),
                name="attendance_status_enum",
            ),
            models.CheckConstraint(
                condition=models.Q(minutes__isnull=True)
                | models.Q(status="PRESENT", minutes__gt=0),
                name="attendance_minutes_present_only",
            ),
        ]


class AttendanceRevision(AppendOnly):
    """Storia append-only delle registrazioni e correzioni di presenza."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance = models.ForeignKey(
        Attendance, on_delete=models.PROTECT, related_name="revisions"
    )
    sequence = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=ATTENDANCE_STATES)
    minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    command = models.CharField(max_length=30)
    reason = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attendance", "sequence"], name="attendance_revision_sequence"
            )
        ]


class ConflictCase(models.Model):
    """Pratica di conflitto post-pubblicazione: non modifica mai le prenotazioni da sola."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        LessonOccurrence,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conflict_cases",
    )
    week_start = models.DateField()
    kind = models.CharField(
        max_length=24,
        choices=[
            ("VALIDATION", "Lezione non più valida sui dati correnti"),
            ("DATA_NOT_READY", "Dati della settimana non compilabili"),
            ("STUDENT_ABSENCE", "Assenza segnalata"),
            ("TUTOR_ABSENCE", "Assenza tutor segnalata"),
        ],
    )
    codes = models.JSONField(default=list)
    dedupe_key = models.CharField(max_length=200)
    source = models.JSONField(default=dict)
    state = models.CharField(
        max_length=10,
        default="OPEN",
        choices=[("OPEN", "Aperta"), ("RESOLVED", "Risolta")],
    )
    resolution = models.CharField(
        max_length=12,
        blank=True,
        default="",
        choices=[
            ("CANCEL", "Lezione cancellata"),
            ("RESCHEDULE", "Lezione spostata"),
            ("CONFIRM", "Confermata dopo correzione del dato"),
        ],
    )
    resolution_note = models.CharField(max_length=200, blank=True, default="")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=models.Q(state="OPEN"),
                name="one_open_conflict_per_key",
            ),
            models.CheckConstraint(
                condition=models.Q(state="OPEN", resolution="")
                | models.Q(state="RESOLVED", resolved_by__isnull=False)
                & ~models.Q(resolution=""),
                name="conflict_resolution_consistent",
            ),
        ]


class ChangeRequest(models.Model):
    """Richiesta di modifica su una lezione: proposta da chiunque nello scope, decisa dal centro."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        LessonOccurrence, on_delete=models.PROTECT, related_name="change_requests"
    )
    kind = models.CharField(
        max_length=12,
        choices=[
            ("CANCEL", "Cancellazione"),
            ("RESCHEDULE", "Spostamento"),
            ("ABSENCE", "Assenza"),
            ("OTHER", "Altro"),
        ],
    )
    proposal = models.JSONField(default=dict)
    origin = models.CharField(
        max_length=10,
        choices=[
            ("CENTER", "Centro"),
            ("TUTOR", "Tutor"),
            ("GUARDIAN", "Tutore legale"),
            ("STUDENT", "Studente"),
        ],
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    student = models.ForeignKey(
        "education.Student", on_delete=models.PROTECT, null=True, blank=True
    )
    reason = models.CharField(max_length=200)
    state = models.CharField(
        max_length=10,
        default="SUBMITTED",
        choices=[
            ("SUBMITTED", "Inviata"),
            ("ACCEPTED", "Accettata"),
            ("REJECTED", "Respinta"),
            ("WITHDRAWN", "Ritirata"),
        ],
    )
    resolver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    resolution_note = models.CharField(max_length=200, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class PlanReview(models.Model):
    """Macchina a stati del piano, esterna a SchedulePlan (immutabile in apps.scheduling).

    DRAFT → VALIDATED → PUBLISHED; DRAFT/VALIDATED → STALE | REJECTED.
    """

    STATES = ["DRAFT", "VALIDATED", "PUBLISHED", "STALE", "REJECTED"]
    TRANSITIONS = {
        "DRAFT": {"VALIDATED", "STALE", "REJECTED"},
        "VALIDATED": {"PUBLISHED", "STALE", "REJECTED"},
        "PUBLISHED": set(),
        "STALE": set(),
        "REJECTED": set(),
    }
    plan = models.OneToOneField(
        "scheduling.SchedulePlan", on_delete=models.PROTECT, related_name="review"
    )
    state = models.CharField(
        max_length=10, default="DRAFT", choices=[(s, s) for s in STATES]
    )
    validated_revision = models.PositiveBigIntegerField(null=True, blank=True)
    report = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["DRAFT", "VALIDATED", "PUBLISHED", "STALE", "REJECTED"]
                ),
                name="plan_review_state_enum",
            )
        ]


class HorizonProposal(models.Model):
    """Proposta periodica di estensione dell'orizzonte: crea solo run/bozze, mai pubblica."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    week_start = models.DateField()
    revision = models.PositiveBigIntegerField()
    state = models.CharField(
        max_length=10,
        choices=[
            ("PROPOSED", "Run di bozza creato"),
            ("BLOCKED", "Bloccata da conflitti/dati"),
            ("COVERED", "Nessuna domanda scoperta"),
        ],
    )
    run = models.ForeignKey(
        "scheduling.ScheduleRun", on_delete=models.PROTECT, null=True, blank=True
    )
    blocking = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["week_start", "revision"], name="one_horizon_proposal_per_rev"
            )
        ]


class TutorAcknowledgement(models.Model):
    """P3 (DC-APPROVAZIONI): presa visione del tutor sugli orari pubblicati.

    PENDING → ACKNOWLEDGED | COUNTER; COUNTER → RESOLVED (accolta o girata alle
    famiglie) oppure di nuovo PENDING se il centro la respinge. Decide solo il centro.
    """

    STATES = ["PENDING", "ACKNOWLEDGED", "COUNTER", "RESOLVED"]
    DECISIONS = ["ACCEPTED", "REJECTED", "ASK_GUARDIANS"]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    publication = models.ForeignKey(
        Publication, on_delete=models.PROTECT, related_name="acknowledgements"
    )
    tutor = models.ForeignKey("education.Tutor", on_delete=models.PROTECT)
    state = models.CharField(
        max_length=12, default="PENDING", choices=[(s, s) for s in STATES]
    )
    note = models.CharField(max_length=500, blank=True, default="")
    items = models.JSONField(default=list)
    decision = models.CharField(max_length=14, blank=True, default="")
    decision_note = models.CharField(max_length=200, blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "tutor"], name="unique_ack_publication_tutor"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    state__in=["PENDING", "ACKNOWLEDGED", "COUNTER", "RESOLVED"]
                ),
                name="tutor_ack_state_enum",
            ),
        ]


class LessonChange(models.Model):
    """Modifica di orario/durata proposta dal centro (drag & drop in Agenda).

    Resta PENDING finché tutor e famiglie (o studenti) dei partecipanti non accettano;
    a quel punto si applica. Il centro può confermarla subito senza attendere (override).
    """

    STATES = ["PENDING", "APPLIED", "REJECTED", "CANCELLED", "FAILED"]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        LessonOccurrence, on_delete=models.PROTECT, related_name="time_changes"
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    previous_start_at = models.DateTimeField()
    previous_end_at = models.DateTimeField()
    lesson_version = models.PositiveIntegerField()
    state = models.CharField(
        max_length=9, default="PENDING", choices=[(s, s) for s in STATES]
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=200, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lesson"],
                condition=models.Q(state="PENDING"),
                name="one_pending_change_per_lesson",
            ),
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="lesson_change_positive_interval",
            ),
        ]


class LessonChangeAnswer(models.Model):
    """Risposta di un diretto interessato: il tutor oppure (per ogni studente) famiglia/studente."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    change = models.ForeignKey(
        LessonChange, on_delete=models.CASCADE, related_name="answers"
    )
    party = models.CharField(
        max_length=7, choices=[("TUTOR", "Tutor"), ("STUDENT", "Studente")]
    )
    tutor = models.ForeignKey(
        "education.Tutor", on_delete=models.PROTECT, null=True, blank=True
    )
    student = models.ForeignKey(
        "education.Student", on_delete=models.PROTECT, null=True, blank=True
    )
    status = models.CharField(
        max_length=8,
        default="PENDING",
        choices=[("PENDING", "In attesa"), ("ACCEPTED", "Accettata"), ("REJECTED", "Rifiutata")],
    )
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(party="TUTOR", tutor__isnull=False, student__isnull=True)
                | models.Q(party="STUDENT", student__isnull=False, tutor__isnull=True),
                name="lesson_change_answer_party",
            ),
        ]
