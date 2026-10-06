"""Development-only atomic commands. PostgreSQL protection required outside test settings."""

import hashlib, json
from zoneinfo import ZoneInfo
from datetime import timedelta, datetime, timezone as dt_timezone
from django.conf import settings
from config import features
from django.db import transaction, connection, IntegrityError
from django.db.models import Q
from django.utils import timezone
from apps.identity.models import Account
from apps.identity.policies import is_center
from apps.education.path_services import Conflict, DomainError
from apps.education.models import Tutor, Student, Resource, Subject
from apps.governance.models import CommandReceipt
from apps.scheduling.models import SchedulePlan, DemandUnit, TutorOperatingPolicy
from apps.scheduling.revision import lock_revision, bump_revision
from apps.scheduling.contracts import input_hash, utc_epoch
from apps.scheduling.source import compile_source, DataNotReady
from apps.scheduling.validator import validate_assignments
from apps.scheduling.environment import runtime_environment
from .models import (
    CalendarResource,
    Publication,
    LessonOccurrence,
    LessonParticipant,
    ResourceBooking,
    CalendarAudit,
    CalendarEvent,
)
from .context import (
    active_week,
    assignment,
    unit_key,
    operations_compile,
    series_candidates,
    request_id_of,
    OCCUPYING,
    week_of,
)

# s3-comunicazioni: outbox nello stesso commit (GAP-F01); vedi docs/communications.md.
from apps.communications.calendar_hooks import notify_lesson
from apps.reasons import reason_or_default
from apps.scheduling.autoplan import is_monthly_lesson, move_codes as autoplan_move_codes, move_options as autoplan_move_options


def supported():
    return connection.vendor == "postgresql" or settings.CALENDAR_ALLOW_SQLITE_TESTS


def authorize(actor):
    if not is_center(actor):
        raise DomainError("FORBIDDEN", "Operazione riservata al centro")
    if not features.calendar_enabled():
        raise DomainError(features.DISABLED_CODE, "Calendario disattivato (FEATURE_CALENDAR)")
    if not supported():
        raise DomainError(
            "POSTGRES_REQUIRED",
            "Pubblicazione disabilitata: PostgreSQL reale necessario",
        )
    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SHOW server_encoding")
            if c.fetchone()[0] != "UTF8":
                raise DomainError(
                    "DATABASE_ENCODING_REQUIRED", "Database UTF8 necessario"
                )
            c.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='calendar_booking_no_overlap' AND contype='x'), (SELECT count(*) FROM pg_trigger WHERE tgname IN ('calendar_verify_lesson','calendar_verify_booking','calendar_verify_participant') AND tgenabled IN ('O','A')), (SELECT count(*) FROM pg_trigger WHERE tgname IN ('calendar_completed_immutable','calendar_audit_append_only','calendar_attendance_revision_append_only') AND tgenabled IN ('O','A'))"
            )
            exclusion, triggers, guards = c.fetchone()
            if not exclusion or triggers != 3 or guards != 3:
                raise DomainError(
                    "DATABASE_PROTECTION_MISSING",
                    "Vincoli/trigger del calendario non installati o disabilitati",
                )


def receipt(actor, operation, key, body):
    if not key or len(key) > 255 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Chiave idempotente obbligatoria")
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()
    previous = CommandReceipt.objects.filter(
        actor=actor, operation=operation, key=key
    ).first()
    if previous and previous.body_hash != digest:
        raise Conflict(
            "IDEMPOTENCY_CONFLICT", "Chiave riutilizzata con comando differente"
        )
    return digest, previous


def record(actor, operation, key, digest, response):
    CommandReceipt.objects.create(
        actor=actor, operation=operation, key=key, body_hash=digest, response=response
    )
    return response


def current_dto(policy, week, mode, unlocked_ids=()):
    try:
        return compile_source(policy, week, mode, unlocked_ids)[0]
    except DataNotReady as error:
        raise DomainError(error.code, error.message) from error


def validate(data, assignments, coverage=True):
    result = validate_assignments(data, assignments, require_coverage=coverage)
    if result["status"] != "PASSED":
        raise DomainError(
            "CALENDAR_VALIDATION_FAILED",
            "Assegnazioni incompatibili con disponibilità, domanda o vincoli correnti",
        )


def resource_for(kind, obj_id):
    field = {"TUTOR": "tutor_id", "STUDENT": "student_id", "RESOURCE": "resource_id"}[
        kind
    ]
    return CalendarResource.objects.get_or_create(kind=kind, **{field: obj_id})[0]


def expected_bookings(lesson):
    rows = [(resource_for("TUTOR", lesson.tutor_id), lesson.tutor_occupied_until)]
    rows += [
        (resource_for("STUDENT", p.student_id), lesson.end_at)
        for p in lesson.participants.all()
    ]
    if lesson.space_id:
        rows.append(
            (resource_for("RESOURCE", lesson.space_id), lesson.space_occupied_until)
        )
    if lesson.video_id:
        rows.append(
            (resource_for("RESOURCE", lesson.video_id), lesson.video_occupied_until)
        )
    return rows


def save_bookings(lesson):
    for resource, end in expected_bookings(lesson):
        if ResourceBooking.objects.filter(
            resource=resource, start_at__lt=end, end_at__gt=lesson.start_at
        ).exists():
            raise Conflict("BOOKING_CONFLICT", "Tutor, studente o risorsa già occupati")
        ResourceBooking.objects.create(
            lesson=lesson, resource=resource, start_at=lesson.start_at, end_at=end
        )


def assert_complete(lesson):
    actual = {(b.resource_id, b.start_at, b.end_at) for b in lesson.bookings.all()}
    expected = (
        {(r.id, lesson.start_at, end) for r, end in expected_bookings(lesson)}
        if lesson.state in OCCUPYING
        else set()
    )
    if actual != expected:
        raise DomainError("BOOKING_INCOMPLETE", "Prenotazioni incomplete: rollback")


def force_constraints():
    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")


def cross_week_transitions(tutor_ids):
    for tutor_id in tutor_ids:
        policy = TutorOperatingPolicy.objects.filter(tutor_id=tutor_id).first()
        if policy is None:  # tutor senza politica operativa (es. pianificatore mensile): nessuna pausa extra
            policy = TutorOperatingPolicy(site_to_remote_minutes=0, remote_to_site_minutes=0, pause_minutes=0)
        rows = list(
            LessonOccurrence.objects.filter(
                tutor_id=tutor_id, state__in=OCCUPYING
            ).order_by("start_at")
        )
        for first, last in zip(rows, rows[1:]):
            transition = (
                0
                if first.location == last.location
                else (
                    policy.site_to_remote_minutes
                    if first.location == "ON_SITE"
                    else policy.remote_to_site_minutes
                )
            )
            if last.start_at < first.end_at + timedelta(
                minutes=max(policy.pause_minutes, transition)
            ):
                raise DomainError(
                    "TRANSITION_CONFLICT",
                    "Pausa o transizione tutor incompatibile anche al confine della settimana",
                )


def summary(lesson):
    return {
        "id": str(lesson.id),
        "version": lesson.version,
        "state": lesson.state,
        "start_at": lesson.start_at.isoformat(),
        "end_at": lesson.end_at.isoformat(),
    }


def now():
    return timezone.now()


@transaction.atomic
def publish_plan(actor, plan_id, command, key):
    authorize(actor)
    revision = lock_revision()
    actor = Account.objects.select_for_update().get(pk=actor.id)
    authorize(actor)
    digest, previous = receipt(
        actor, "calendar-publish", key, {"plan_id": str(plan_id), **command}
    )
    if previous:
        return previous.response
    plan = (
        SchedulePlan.objects.select_for_update(of=("self",))
        .select_related("run__snapshot__policy")
        .get(pk=plan_id)
    )
    if command["expected_version"] != 1:
        raise Conflict("VERSION_CONFLICT", "La proposta immutabile ha versione 1")
    if Publication.objects.filter(plan=plan).exists():
        raise Conflict("ALREADY_PUBLISHED", "Proposta già pubblicata")
    if revision.revision != command["expected_revision"]:
        raise Conflict("STALE_INPUT", "Input cambiati: nuova generazione necessaria")
    checked = verify_plan(plan, revision.revision)
    snapshot, data, missing = checked["snapshot"], checked["data"], checked["missing"]
    existing, new = checked["existing"], checked["new"]
    accepted = command["accept_unassigned_demand_keys"]
    if len(set(accepted)) != len(accepted) or set(accepted) != missing:
        raise DomainError(
            "PARTIAL_ACCEPTANCE_REQUIRED",
            "Accettare esattamente le unità non soddisfatte, senza duplicati",
        )
    reason = reason_or_default(
        command.get("reason"), "Pubblicazione parziale accettata dal centro" if missing else "Pubblicazione"
    )
    review = plan_review_for_publication(plan, revision.revision)
    candidates = series_candidates(data, snapshot.horizon_start)
    publication = Publication.objects.create(
        plan=plan,
        actor=actor,
        revision_after=revision.revision + 1,
        accepted_unassigned=accepted,
        reason=reason,
    )
    units = {u["demand_key"]: u for u in data["units"]}
    tutors = {t["id"]: t for t in data["tutors"]}
    resources = {v["id"]: v for v in data["resources"]}
    created = []
    epoch = utc_epoch(data)
    for a in new:
        unit = units[a["demand_key"]]
        start = epoch + timedelta(minutes=a["start"])
        end = epoch + timedelta(minutes=a["end"])
        series, recurrence_key = series_link(candidates, a, start)
        lesson = LessonOccurrence.objects.create(
            series=series,
            recurrence_key=recurrence_key,
            demand=DemandUnit.objects.get(demand_key=a["demand_key"]),
            publication=publication,
            tutor_id=a["tutor_id"],
            subject_id=unit["subject"],
            mode=a["mode"],
            location=a["location"],
            space_id=a["space_id"],
            video_id=a["video_id"],
            start_at=start,
            end_at=end,
            tutor_occupied_until=end
            + timedelta(minutes=tutors[a["tutor_id"]]["pause_minutes"]),
            space_occupied_until=end
            + timedelta(minutes=resources[a["space_id"]]["buffer_minutes"])
            if a["space_id"]
            else None,
            video_occupied_until=end
            + timedelta(minutes=resources[a["video_id"]]["buffer_minutes"])
            if a["video_id"]
            else None,
        )
        for student in unit["participants"]:
            LessonParticipant.objects.create(lesson=lesson, student_id=student)
        save_bookings(lesson)
        assert_complete(lesson)
        created.append(str(lesson.id))
        CalendarAudit.objects.create(
            actor=actor,
            operation="PUBLISH",
            lesson=lesson,
            publication=publication,
            reason=reason,
            after=summary(lesson),
        )
        CalendarEvent.objects.create(
            event_key=f"lesson:{lesson.id}:v1",
            kind="LESSON_PUBLISHED",
            payload={"lesson_id": str(lesson.id), "version": 1, "experimental": True},
        )
        notify_lesson(lesson, "LESSON_PUBLISHED")
    cross_week_transitions({a["tutor_id"] for a in new})
    force_constraints()
    review.state = "PUBLISHED"
    review.version += 1
    review.updated_by = actor
    review.save()
    bump_revision()
    return record(
        actor,
        "calendar-publish",
        key,
        digest,
        {
            "publication_id": str(publication.id),
            "created_lesson_ids": created,
            "kept_lesson_ids": [str(l.id) for l in existing.values()],
            "revision": revision.revision + 1,
            "experimental": True,
            "notifications_sent": False,
        },
    )


def verify_plan(plan, current_revision):
    """Controlli indipendenti di una proposta sui dati correnti, senza scritture.

    Usato dalla pubblicazione e dall'endpoint esplicito di validazione (GAP-E07)."""
    snapshot = plan.run.snapshot
    if snapshot.revision != current_revision:
        raise Conflict("STALE_INPUT", "Input cambiati: nuova generazione necessaria")
    if plan.state != "VALIDATED" or plan.run.status != "SUCCEEDED":
        raise DomainError("PLAN_NOT_VALIDATED", "Proposta non validata")
    if (
        snapshot.environment != runtime_environment()
        or input_hash(snapshot.data) != snapshot.input_hash
    ):
        raise Conflict("SNAPSHOT_CHANGED", "Snapshot o ambiente non verificabili")
    result = plan.run.result
    if (
        not result
        or plan.assignments != result.get("assignments")
        or hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        != plan.result_hash
    ):
        raise DomainError("PLAN_HASH_MISMATCH", "Artefatto della proposta alterato")
    if (
        result.get("solver_status") not in ("OPTIMAL", "FEASIBLE")
        or result.get("validation", {}).get("status") != "PASSED"
    ):
        raise DomainError(
            "PLAN_NOT_VALIDATED", "Esito solver o validazione non pubblicabili"
        )
    data = current_dto(snapshot.policy, snapshot.horizon_start, snapshot.data["mode"])
    if input_hash(data) != snapshot.input_hash:
        raise Conflict(
            "UNTRACKED_INPUT_CHANGE",
            "Input diversi dallo snapshot, anche senza revisione registrata",
        )
    validate(data, plan.assignments)
    assigned = {a["demand_key"] for a in plan.assignments}
    missing = {u["demand_key"] for u in data["units"]} - assigned
    existing = {unit_key(l): l for l in active_week(snapshot.horizon_start)}
    for demand_key, lesson in existing.items():
        if assignment(lesson, utc_epoch(data)) not in plan.assignments:
            raise DomainError(
                "KEEP_REQUIRED",
                "Ogni lezione già pubblicata deve essere mantenuta: nessuna rimozione implicita",
            )
    new = [a for a in plan.assignments if a["demand_key"] not in existing]
    if not new:
        raise DomainError("NO_NEW_ASSIGNMENTS", "Nessuna nuova lezione da pubblicare")
    if any(utc_epoch(data) + timedelta(minutes=a["start"]) <= now() for a in new):
        raise DomainError("PAST_LESSON", "Non pubblicare lezioni nel passato")
    return {
        "snapshot": snapshot,
        "data": data,
        "missing": missing,
        "existing": existing,
        "new": new,
    }


def move_context(lesson):
    """DTO corrente e lezioni della settimana fisica esclusa quella da spostare."""
    snapshot = lesson.publication.plan.run.snapshot
    with operations_compile():
        data = current_dto(
            snapshot.policy,
            week_of(lesson.start_at),
            snapshot.data["mode"],
            [lesson.id],
        )
    current = [u["locked_assignment"] for u in data["units"] if u["locked_assignment"]]
    return data, current


def moved(lesson, data, target):
    epoch = utc_epoch(data)
    if not epoch <= target < epoch + timedelta(minutes=data["horizon_minutes"]):
        raise DomainError(
            "SAME_WEEK_REQUIRED", "Spostamento limitato alla settimana originaria"
        )
    moving = assignment(lesson, epoch)
    duration = moving["end"] - moving["start"]
    minute = (target - epoch).total_seconds() / 60
    if not minute.is_integer():
        raise DomainError("MINUTE_PRECISION", "Precisione al minuto richiesta")
    moving["start"] = int(minute)
    moving["end"] = int(minute) + duration
    return moving


def new_codes(data, current, result, baseline=None):
    """Codici di violazione introdotti dallo spostamento (esclude quelli preesistenti)."""
    if baseline is None:
        baseline = validate_assignments(data, current, require_coverage=False)[
            "violations"
        ]
    known = {(v["code"], v["demand_key"]) for v in baseline}
    return sorted(
        {
            v["code"]
            for v in result["violations"]
            if (v["code"], v["demand_key"]) not in known
        }
    )


def reschedule_options(actor, lesson_id, day):
    """Esito della validazione per ogni inizio a 15 minuti di un giorno: nessun effetto."""
    authorize(actor)
    lesson = LessonOccurrence.objects.select_related(
        "demand", "publication__plan__run__snapshot__policy"
    ).get(pk=lesson_id)
    if lesson.state != "PUBLISHED":
        raise DomainError("LESSON_NOT_ACTIVE", "Lezione non attiva")
    if lesson.start_at <= now():
        raise DomainError(
            "PAST_LESSON",
            "Correzione amministrativa separata necessaria per lezioni iniziate",
        )
    if is_monthly_lesson(lesson):
        return {
            "lesson_id": str(lesson.id),
            "version": lesson.version,
            "date": day.isoformat(),
            "current_start_at": lesson.start_at.isoformat(),
            "options": autoplan_move_options(lesson, day),
            "experimental": False,
        }
    data, current = move_context(lesson)
    epoch = utc_epoch(data)
    end = epoch + timedelta(minutes=data["horizon_minutes"])
    zone = ZoneInfo(data["timezone"])
    baseline = validate_assignments(data, current, require_coverage=False)["violations"]
    options = []
    local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    while local.date() == day:
        start = local.astimezone(dt_timezone.utc)
        if start <= now():
            codes = ["PAST_LESSON"]
        elif not epoch <= start < end:
            codes = ["SAME_WEEK_REQUIRED"]
        else:
            moving = moved(lesson, data, start)
            result = validate_assignments(
                data, [*current, moving], require_coverage=False
            )
            codes = (
                []
                if result["status"] == "PASSED"
                else new_codes(data, current, result, baseline)
                or ["CALENDAR_VALIDATION_FAILED"]
            )
        options.append({"start_at": start.isoformat(), "ok": not codes, "codes": codes})
        local = (start + timedelta(minutes=15)).astimezone(zone)
    return {
        "lesson_id": str(lesson.id),
        "version": lesson.version,
        "date": day.isoformat(),
        "current_start_at": lesson.start_at.isoformat(),
        "options": options,
        "experimental": True,
    }


MIN_LESSON_MINUTES = 15
MAX_LESSON_MINUTES = 8 * 60


def new_duration(lesson, start, end=None):
    """Durata della lezione dopo lo spostamento: invariata, oppure ``end - start`` (drag sul bordo)."""
    if end is None:
        return lesson.end_at - lesson.start_at
    minutes = (end - start).total_seconds() / 60
    if minutes < MIN_LESSON_MINUTES or minutes > MAX_LESSON_MINUTES or minutes % 5:
        raise DomainError(
            "DURATION_INVALID",
            f"Durata non valida: tra {MIN_LESSON_MINUTES} minuti e {MAX_LESSON_MINUTES // 60} ore, a passi di 5 minuti",
        )
    return end - start


def check_reschedule(lesson, target, end=None):
    """Verifica (senza effetti) che ``lesson`` possa occupare [target, end). Solleva DomainError."""
    if target <= now():
        raise DomainError("PAST_LESSON", "Il nuovo inizio deve essere futuro")
    duration = new_duration(lesson, target, end)
    if is_monthly_lesson(lesson):
        # Lezioni del pianificatore mensile: stessi vincoli del motore (orari, chiusure,
        # impegni, lezioni già fissate), non quelli del motore settimanale storico.
        codes = autoplan_move_codes(lesson, target, duration=duration)
        if codes:
            raise DomainError(
                "CALENDAR_VALIDATION_FAILED",
                "Orario incompatibile con apertura, impegni o lezioni già fissate",
                violations=codes,
            )
        return duration
    if duration != lesson.end_at - lesson.start_at:
        raise DomainError(
            "DURATION_FIXED",
            "La durata delle lezioni del motore settimanale è fissata dalla richiesta",
        )
    data, current = move_context(lesson)
    moving = moved(lesson, data, target)
    result = validate_assignments(data, [*current, moving], require_coverage=False)
    if result["status"] != "PASSED":
        raise DomainError(
            "CALENDAR_VALIDATION_FAILED",
            "Assegnazioni incompatibili con disponibilità, domanda o vincoli correnti",
            violations=new_codes(data, current, result),
        )
    return duration


def apply_times(lesson, target, duration):
    """Nuovo intervallo della lezione; pause e buffer di tutor, aula e canale restano invariati."""
    tutor_pause = lesson.tutor_occupied_until - lesson.end_at
    space_pause = lesson.space_occupied_until - lesson.end_at if lesson.space_occupied_until else None
    video_pause = lesson.video_occupied_until - lesson.end_at if lesson.video_occupied_until else None
    lesson.start_at = target
    lesson.end_at = target + duration
    lesson.tutor_occupied_until = lesson.end_at + tutor_pause
    if space_pause is not None:
        lesson.space_occupied_until = lesson.end_at + space_pause
    if video_pause is not None:
        lesson.video_occupied_until = lesson.end_at + video_pause


@transaction.atomic
def change_lesson(actor, lesson_id, operation, command, key, keep_change=None):
    authorize(actor)
    revision = lock_revision()
    actor = Account.objects.select_for_update().get(pk=actor.id)
    authorize(actor)
    digest, previous = receipt(
        actor, "calendar-" + operation, key, {"lesson_id": str(lesson_id), **command}
    )
    if previous:
        return previous.response
    lesson = (
        LessonOccurrence.objects.select_for_update(of=("self",))
        .select_related("demand", "publication__plan__run__snapshot__policy", "subject", "tutor")
        .get(pk=lesson_id)
    )
    if lesson.version != command["expected_version"]:
        raise Conflict("VERSION_CONFLICT", "Lezione cambiata: ricaricare")
    if lesson.state != "PUBLISHED":
        raise DomainError("LESSON_NOT_ACTIVE", "Lezione non attiva")
    if lesson.start_at <= now():
        raise DomainError(
            "PAST_LESSON",
            "Correzione amministrativa separata necessaria per lezioni iniziate",
        )
    reason = reason_or_default(command.get("reason"))
    before = summary(lesson)
    if operation == "cancel":
        lesson.bookings.all().delete()
        lesson.state = "CANCELLED"
        reopen_recovery(lesson, actor, reason)
    elif operation == "reschedule":
        target = command["start_at"]
        duration = check_reschedule(lesson, target, command.get("end_at"))
        apply_times(lesson, target, duration)
        if is_monthly_lesson(lesson):  # durata cambiata: nuovo aggancio allo snapshot mensile
            from apps.scheduling.autoplan_publish import ensure_anchor

            ensure_anchor(lesson, actor)
        lesson.bookings.all().delete()
        lesson.version += 1
        lesson.save()
        save_bookings(lesson)
        cross_week_transitions([lesson.tutor_id])
    else:
        raise DomainError("UNSUPPORTED_COMMAND", "Comando non supportato")
    if operation == "cancel":
        lesson.version += 1
        lesson.save()
    assert_complete(lesson)
    force_constraints()
    bump_revision()
    CalendarAudit.objects.create(
        actor=actor,
        operation=operation.upper(),
        lesson=lesson,
        publication=lesson.publication,
        reason=reason,
        before=before,
        after=summary(lesson),
    )
    CalendarEvent.objects.create(
        event_key=f"lesson:{lesson.id}:v{lesson.version}",
        kind="LESSON_" + operation.upper(),
        payload={
            "lesson_id": str(lesson.id),
            "version": lesson.version,
            "experimental": True,
        },
    )
    notify_lesson(lesson, "LESSON_" + operation.upper(), before=before)
    from .changes import supersede

    supersede(lesson, keep=keep_change)
    return record(
        actor,
        "calendar-" + operation,
        key,
        digest,
        {
            **summary(lesson),
            "revision": revision.revision + 1,
            "experimental": True,
            "notifications_sent": False,
            "recovery_created": False,
        },
    )


# --- s2-calendario --------------------------------------------------------------


def series_link(candidates, a, start):
    """Collega una nuova lezione all'occorrenza di serie che l'ha proiettata."""
    request = request_id_of(a["demand_key"])
    for index, (series, occ) in enumerate(candidates):
        if (
            str(series.request_id) == request
            and occ["start_at"] == start
            and str(series.tutor_id) == a["tutor_id"]
        ):
            candidates.pop(index)
            return series, occ["key"]
    return None, None


def plan_review_for_publication(plan, revision):
    from .models import PlanReview

    review, _ = PlanReview.objects.select_for_update().get_or_create(plan=plan)
    if getattr(settings, "CALENDAR_REQUIRE_EXPLICIT_VALIDATION", False) and (
        review.state != "VALIDATED" or review.validated_revision != revision
    ):
        raise DomainError(
            "EXPLICIT_VALIDATION_REQUIRED",
            "Validare esplicitamente la proposta sulla revisione corrente prima di pubblicare",
        )
    if review.state not in ("DRAFT", "VALIDATED"):
        raise DomainError(
            "PLAN_STATE_INVALID", f"Proposta in stato {review.state}: non pubblicabile"
        )
    return review


def reopen_recovery(lesson, actor, reason):
    """Cancellare un recupero riapre il medesimo obbligo, mai uno nuovo (T40)."""
    if not lesson.recovery_id:
        return None
    from .models import RecoveryObligation

    obligation = RecoveryObligation.objects.select_for_update().get(
        pk=lesson.recovery_id
    )
    before = {"state": obligation.state, "version": obligation.version}
    obligation.state = "OPEN"
    obligation.version += 1
    obligation.save()
    CalendarAudit.objects.create(
        actor=actor,
        operation="RECOVERY_REOPENED",
        object_type="RecoveryObligation",
        object_id=obligation.id,
        lesson=lesson,
        reason=reason,
        before=before,
        after={"state": obligation.state, "version": obligation.version},
    )
    return obligation
