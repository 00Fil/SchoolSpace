import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.education.models import (
    Entity,
    Tutor,
    Student,
    Subject,
    Resource,
    TeachingRequest,
)


class PlanningRevision(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    revision = models.PositiveBigIntegerField(default=0)


class TutorSkill(Entity):
    tutor = models.ForeignKey(Tutor, on_delete=models.PROTECT)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    level = models.CharField(max_length=80)
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    valid_from = models.DateField()
    valid_until = models.DateField()
    approved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_until__gte=models.F("valid_from")),
                name="skill_dates",
            )
        ]


class TutorOperatingPolicy(Entity):
    tutor = models.OneToOneField(Tutor, on_delete=models.PROTECT)
    daily_limit_minutes = models.PositiveIntegerField()
    weekly_limit_minutes = models.PositiveIntegerField()
    pause_minutes = models.PositiveSmallIntegerField()
    site_to_remote_minutes = models.PositiveSmallIntegerField()
    remote_to_site_minutes = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    daily_limit_minutes__gt=0, weekly_limit_minutes__gt=0
                ),
                name="tutor_positive_work_limits",
            )
        ]


class ResourceTiming(Entity):
    resource = models.OneToOneField(Resource, on_delete=models.PROTECT)
    buffer_minutes = models.PositiveSmallIntegerField()
    inherit_service_windows = models.BooleanField()


class ServiceWindow(Entity):
    mode = models.CharField(
        max_length=9, choices=[("IN_PERSON", "Presenza"), ("ONLINE", "Online")]
    )
    location = models.CharField(
        max_length=8, choices=[("ON_SITE", "Sede"), ("REMOTE", "Remoto")]
    )
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    period_start = models.DateField()
    period_end = models.DateField()
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    weekday__lte=6,
                    end_time__gt=models.F("start_time"),
                    period_end__gte=models.F("period_start"),
                ),
                name="service_interval",
            ),
            models.CheckConstraint(
                condition=models.Q(mode="ONLINE")
                | models.Q(mode="IN_PERSON", location="ON_SITE"),
                name="service_location",
            ),
        ]


class Closure(Entity):
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    mode = models.CharField(
        max_length=9,
        choices=[("ALL", "Tutte"), ("IN_PERSON", "Presenza"), ("ONLINE", "Online")],
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, null=True, blank=True
    )
    reason = models.CharField(max_length=160)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="closure_positive",
            )
        ]


class PlanningPolicy(Entity):
    name = models.CharField(max_length=120)
    budget_seconds = models.FloatField()
    online_onsite_requires_space = models.BooleanField()
    video_channels_required = models.BooleanField()
    partial_week_rule = models.CharField(
        max_length=30,
        choices=[
            ("BLOCK", "Blocca settimana parziale"),
            ("INCLUDE_ACTIVE_DATES", "Quantità piena entro date attive"),
        ],
    )
    unsupported_constraints = models.JSONField()
    approved_for_exploration = models.BooleanField()
    # --- s8: v0.5 planning options; defaults reproduce the v0.4 behaviour. ---
    # Open business choices (D03) stay "da approvare" (see policies.py).
    horizon_weeks = models.PositiveSmallIntegerField(default=1)
    objective_order = models.JSONField(default=list, blank=True)
    fairness_policy_id = models.CharField(max_length=80, default="fairness-default")
    fairness_policy_version = models.PositiveIntegerField(default=1)
    recurring_stability = models.CharField(
        max_length=10,
        default="NONE",
        choices=[
            ("NONE", "Nessuna serie implicita"),
            ("PREFERRED", "Slot ricorrente preferito"),
        ],
    )
    student_buffer_minutes = models.PositiveSmallIntegerField(default=0)
    allow_cross_local_midnight = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(budget_seconds__gte=0.1, budget_seconds__lte=30),
                name="planning_budget_range_v05",
            ),
            models.CheckConstraint(
                condition=models.Q(horizon_weeks__gte=1, horizon_weeks__lte=6),
                name="planning_horizon_weeks",
            ),
            models.CheckConstraint(
                condition=models.Q(student_buffer_minutes__lte=120),
                name="planning_student_buffer",
            ),
        ]


class LessonSeries(Entity):
    """Recurring weekly slot of a request serial (GAP-D03).

    PREFERRED: deviations are penalised by the R term; REQUIRED: the family
    requires the slot, an incompatible week is reported, never moved silently.
    """

    # Preferenza di stabilità per il solver (D03): distinta dalla serie operativa
    # lesson_calendar.LessonSeries (E01), che ne è la materializzazione nel calendario.
    request = models.ForeignKey(
        TeachingRequest, on_delete=models.PROTECT, related_name="planning_slot_series"
    )
    serial = models.PositiveSmallIntegerField()
    weekday = models.PositiveSmallIntegerField()
    local_start_time = models.TimeField()
    stability = models.CharField(
        max_length=10,
        choices=[("PREFERRED", "Preferito"), ("REQUIRED", "Obbligatorio")],
    )
    source = models.CharField(
        max_length=14,
        choices=[
            ("PREVIOUS_PLAN", "Proposta precedente"),
            ("DECLARED", "Dichiarato dal centro"),
        ],
    )
    source_plan = models.ForeignKey(
        "SchedulePlan", on_delete=models.PROTECT, null=True, blank=True
    )
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "serial"], name="lesson_series_request_serial"
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__lte=6, serial__gte=1),
                name="lesson_series_slot",
            ),
        ]


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Artefatto immutabile")

    def bulk_create(self, *args, **kwargs):
        raise ValidationError(
            "Creazione massiva di artefatti immutabili non consentita"
        )

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Artefatto immutabile")

    def delete(self):
        raise ValidationError("Artefatto immutabile")


class PlanningSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.PositiveBigIntegerField()
    schema_version = models.CharField(max_length=8)
    horizon_start = models.DateField()
    horizon_end = models.DateField()
    policy = models.ForeignKey(PlanningPolicy, on_delete=models.PROTECT)
    policy_version = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField()
    input_hash = models.CharField(max_length=64)
    environment = models.JSONField(default=dict)
    objects = ImmutableQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if not self._state.adding or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Snapshot immutabile")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Snapshot immutabile")


class DemandUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(TeachingRequest, on_delete=models.PROTECT)
    week_start = models.DateField()
    serial = models.PositiveSmallIntegerField()
    demand_key = models.CharField(max_length=80, unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "week_start", "serial"],
                name="canonical_request_week_serial",
            )
        ]


class ScheduleRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    snapshot = models.OneToOneField(PlanningSnapshot, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=10,
        default="QUEUED",
        choices=[
            (s, s) for s in ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")
        ],
    )
    phase = models.CharField(max_length=20, default="QUEUED")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    cancel_requested = models.BooleanField(default=False)
    error_code = models.CharField(max_length=60, blank=True)
    result = models.JSONField(null=True, blank=True)


class RunDispatch(models.Model):
    run = models.OneToOneField(
        ScheduleRun, on_delete=models.PROTECT, primary_key=True, related_name="dispatch"
    )
    status = models.CharField(max_length=10, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)


class SchedulePlan(models.Model):
    objects = ImmutableQuerySet.as_manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.OneToOneField(
        ScheduleRun, on_delete=models.PROTECT, related_name="plan"
    )
    state = models.CharField(
        max_length=12,
        choices=[("VALIDATED", "Validata sullo snapshot"), ("STALE", "Obsoleta")],
    )
    assignments = models.JSONField()
    result_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding or type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Proposta immutabile; stato derivato dalla revisione corrente"
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Proposta immutabile")


class PlanningAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    operation = models.CharField(max_length=60)
    object_id = models.UUIDField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# --- P2 (guida v3.1): struttura dell'anno scolastico, decisione DC-ANNO ---------
class SchoolYear(Entity):
    """Anno scolastico: periodo di validità di default per orari e disponibilità."""

    name = models.CharField(max_length=40, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="school_year_positive",
            )
        ]


class StudyPeriod(Entity):
    """Inizi, pause (natale, pasqua, estate, altre) e periodi per i recuperi.

    Le pause generano una chiusura che il motore rispetta; inizi e periodi di
    recupero non chiudono il centro (i recuperi sono usati in P4).
    """

    class Kind(models.TextChoices):
        START = "START", "Inizio lezioni"
        CHRISTMAS = "CHRISTMAS", "Pausa natalizia"
        EASTER = "EASTER", "Pausa pasquale"
        SUMMER = "SUMMER", "Pausa estiva"
        BREAK = "BREAK", "Altra pausa"
        RECOVERY = "RECOVERY", "Periodo per i recuperi"

    BREAKS = ("CHRISTMAS", "EASTER", "SUMMER", "BREAK")

    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="periods")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    label = models.CharField(max_length=80, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    closure = models.OneToOneField(Closure, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="study_period_positive",
            )
        ]


# --- v0.9.7: pianificatore mensile semplificato -----------------------------------
# Input: orari di apertura del centro (rigidi), chiusure (Closure, rigide), impegni di
# studenti e tutor (rispettati, tolleranza di sforamento con conferma).


class OpeningHours(Entity):
    """Fascia di apertura settimanale del centro (più fasce per giorno ammesse)."""

    weekday = models.PositiveSmallIntegerField(help_text="0=lunedì, 6=domenica")
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekday__lte=6), name="opening_weekday"
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="opening_positive",
            ),
        ]


class Commitment(Entity):
    """Impegno di uno studente (inserito dal genitore) o di un tutor.

    WEEKLY: si ripete ogni settimana (giorno, orario, validità opzionale).
    ONE_OFF: un giorno preciso (orario oppure tutto il giorno: 00:00–23:59).
    """

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, null=True, blank=True,
        related_name="commitments",
    )
    tutor = models.ForeignKey(
        Tutor, on_delete=models.CASCADE, null=True, blank=True,
        related_name="commitments",
    )
    label = models.CharField(max_length=80)
    kind = models.CharField(
        max_length=7,
        choices=[("WEEKLY", "Ogni settimana"), ("ONE_OFF", "Una volta")],
        default="WEEKLY",
    )
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ["kind", "weekday", "date", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tutor__isnull=False, student__isnull=True)
                    | models.Q(tutor__isnull=True, student__isnull=False)
                ),
                name="commitment_owner_xor",
            ),
            models.CheckConstraint(
                condition=models.Q(kind="WEEKLY", weekday__lte=6, date__isnull=True)
                | models.Q(kind="ONE_OFF", date__isnull=False, weekday__isnull=True),
                name="commitment_kind_fields",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="commitment_positive",
            ),
        ]


class AutoPlan(Entity):
    """Calendario mensile proposto dal motore, rivisto e pubblicato dal centro."""

    month = models.DateField(help_text="Primo giorno del mese")
    state = models.CharField(
        max_length=9,
        choices=[
            ("DRAFT", "Bozza"),
            ("PUBLISHED", "Pubblicato"),
            ("DISCARDED", "Scartato"),
            # v0.9.11: lezioni confluite nell'unico calendario pubblico del mese
            ("MERGED", "Unito al calendario del mese"),
        ],
        default="DRAFT",
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    solver_status = models.CharField(max_length=20, blank=True)
    stats = models.JSONField(default=dict)
    unplaced = models.JSONField(default=list)
    published_at = models.DateTimeField(null=True, blank=True)
    # v0.9.9: bozza dedicata a una sola richiesta (ricalcolo automatico dopo
    # l'approvazione). Vuoto = calendario mensile del centro.
    request = models.ForeignKey(
        TeachingRequest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="request_plans",
    )

    class Meta:
        ordering = ["-created_at"]


class AutoPlanLesson(Entity):
    plan = models.ForeignKey(AutoPlan, on_delete=models.CASCADE, related_name="lessons")
    request = models.ForeignKey(TeachingRequest, on_delete=models.PROTECT)
    tutor = models.ForeignKey(Tutor, on_delete=models.PROTECT)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    mode = models.CharField(max_length=9)
    space = models.ForeignKey(
        Resource, on_delete=models.PROTECT, null=True, blank=True
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    participants = models.JSONField(default=list)  # id studenti
    overflow_minutes = models.PositiveSmallIntegerField(default=0)
    state = models.CharField(
        max_length=9,
        choices=[
            ("PROPOSED", "Proposta"),
            ("AWAITING", "In attesa di conferma"),
            ("PUBLISHED", "Pubblicata"),
            ("REJECTED", "Rifiutata"),
            ("DISCARDED", "Scartata"),
        ],
        default="PROPOSED",
    )
    occurrence = models.OneToOneField(
        "lesson_calendar.LessonOccurrence",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="autoplan_lesson",
    )

    class Meta:
        ordering = ["start_at"]


class AutoPlanConfirmation(Entity):
    """Conferma chiesta a famiglia (per lo studente) o tutor per uno sforamento."""

    lesson = models.ForeignKey(
        AutoPlanLesson, on_delete=models.CASCADE, related_name="confirmations"
    )
    party = models.CharField(
        max_length=7, choices=[("STUDENT", "Studente/famiglia"), ("TUTOR", "Tutor")]
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True)
    tutor = models.ForeignKey(Tutor, on_delete=models.CASCADE, null=True, blank=True)
    minutes = models.PositiveSmallIntegerField()
    labels = models.JSONField(default=list)
    status = models.CharField(
        max_length=8,
        choices=[
            ("DRAFT", "Non ancora inviata"),
            ("PENDING", "In attesa"),
            ("ACCEPTED", "Accettata"),
            ("REJECTED", "Rifiutata"),
        ],
        default="DRAFT",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]


class CalendarCorrection(Entity):
    """Rettifica in bozza del calendario pubblico di un mese (v0.9.11).

    Ogni modifica del centro a un mese (spostare, cambiare durata, cancellare, scambiare,
    sostituire il tutor, aggiungere le lezioni di una richiesta verificata) resta in bozza
    finché il gestore non pubblica le rettifiche del mese, oppure la pubblica subito.
    Alla pubblicazione l'operazione viene eseguita con gli stessi servizi del calendario.
    """

    OPS = [
        ("reschedule", "Sposta o cambia durata"),
        ("cancel", "Cancella"),
        ("modify", "Modifica (tutor, modalità, aula)"),
        ("swap", "Scambia due lezioni"),
        ("plan", "Aggiungi le lezioni di una richiesta"),
    ]
    month = models.DateField(help_text="Primo giorno del mese")
    op = models.CharField(max_length=10, choices=OPS)
    lesson = models.ForeignKey(
        "lesson_calendar.LessonOccurrence",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="corrections",
    )
    other = models.ForeignKey(
        "lesson_calendar.LessonOccurrence",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    plan = models.ForeignKey(
        AutoPlan, on_delete=models.CASCADE, null=True, blank=True, related_name="corrections"
    )
    command = models.JSONField(default=dict)
    summary = models.CharField(max_length=300, blank=True)
    state = models.CharField(
        max_length=9,
        choices=[
            ("PENDING", "In bozza"),
            ("APPLIED", "Pubblicata"),
            ("FAILED", "Non applicabile"),
            ("DISCARDED", "Scartata"),
        ],
        default="PENDING",
    )
    error = models.CharField(max_length=300, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["month", "state"], name="correction_month_state")]
