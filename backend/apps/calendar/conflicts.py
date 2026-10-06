"""ConflictCase e ChangeRequest (GAP-E05, FR18, T41).

La rilevazione salva il dato e apre pratiche: non cancella, non sposta e non libera
prenotazioni. Il calendario precedente resta visibile con avviso finché il centro
risolve (cancellazione, spostamento, conferma dopo correzione del dato).
"""

import logging
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from apps.identity.policies import can_request_student_changes, is_center
from apps.scheduling.contracts import utc_epoch
from apps.scheduling.source import compile_source, DataNotReady
from apps.scheduling.validator import validate_assignments
from apps.scheduling.revision import bump_revision
from .models import LessonOccurrence, ConflictCase, ChangeRequest
from .context import operations_compile, active_week, assignment, unit_key, week_of
from .commands import (
    Command,
    audit,
    event,
    require_reason,
    check_version,
    now,
    DomainError,
)
from .operations import (
    lock_lessons,
    change_lessons,
    cancel_lesson,
    require_future_active,
    ensure_obligation,
    validate_changes,
    target_of,
)
from .scope import authorize_any, lesson_relation
from . import notifications
from .services import current_dto

log = logging.getLogger(__name__)
SYSTEM = "system:conflict-detector"


def case_summary(case):
    return {
        "id": str(case.id),
        "lesson_id": str(case.lesson_id) if case.lesson_id else None,
        "week_start": case.week_start.isoformat(),
        "kind": case.kind,
        "codes": case.codes,
        "state": case.state,
        "resolution": case.resolution,
        "resolution_note": case.resolution_note,
        "version": case.version,
        "source": case.source,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


@transaction.atomic
def open_case(actor, *, kind, week, codes, dedupe_key, lesson=None, source=None):
    """Apre (o aggiorna) una sola pratica aperta per chiave: nessun duplicato."""
    case = (
        ConflictCase.objects.select_for_update()
        .filter(dedupe_key=dedupe_key, state="OPEN")
        .first()
    )
    codes = sorted(set(codes))
    if case:
        if case.codes != codes:
            before = case_summary(case)
            case.codes = codes
            case.version += 1
            case.save()
            audit(
                actor,
                "CONFLICT_UPDATED",
                "Codici aggiornati",
                lesson=lesson,
                obj=case,
                before=before,
                after=case_summary(case),
            )
        return case, False
    case = ConflictCase.objects.create(
        lesson=lesson,
        week_start=week,
        kind=kind,
        codes=codes,
        dedupe_key=dedupe_key,
        source=source or {},
    )
    audit(
        actor,
        "CONFLICT_OPENED",
        "Pratica aperta, calendario invariato",
        lesson=lesson,
        obj=case,
        after=case_summary(case),
    )
    event(
        "CONFLICT_OPENED",
        f"conflict:{case.id}:v1",
        {"conflict_id": str(case.id), "lesson_id": str(lesson.id) if lesson else None},
    )
    notifications.conflict_opened(case)
    return case, True


def week_violations(week, lessons):
    """Violazioni correnti delle lezioni future di una settimana, senza sbloccare nulla."""
    snapshot = lessons[0].publication.plan.run.snapshot
    everything = list(active_week(week))
    with operations_compile():
        data = compile_source(
            snapshot.policy, week, snapshot.data["mode"], [l.id for l in everything]
        )[0]
    epoch = utc_epoch(data)
    rows = [assignment(l, epoch) for l in everything]
    result = validate_assignments(data, rows, require_coverage=False)
    by_key = {}
    for v in result["violations"]:
        by_key.setdefault(v["demand_key"], set()).add(v["code"])
    out = {}
    for lesson in lessons:
        codes = set(by_key.get(unit_key(lesson), set()))
        codes |= by_key.get(str(lesson.tutor_id), set())  # DAILY/WEEKLY_LOAD
        if codes:
            out[lesson] = codes
    return out


def detect_conflicts(actor=SYSTEM, tutor_ids=None, student_ids=None, weeks=None):
    """Apre pratiche per lezioni future pubblicate non più valide sui dati correnti."""
    lessons = LessonOccurrence.objects.filter(
        state="PUBLISHED", start_at__gt=now()
    ).select_related("publication__plan__run__snapshot__policy", "demand", "recovery")
    if tutor_ids is not None or student_ids is not None:
        lessons = lessons.filter(
            Q(tutor_id__in=list(tutor_ids or []))
            | Q(participants__student_id__in=list(student_ids or []))
        ).distinct()
    grouped = {}
    for lesson in lessons:
        week = week_of(lesson.start_at)
        if weeks is None or week in weeks:
            grouped.setdefault(week, []).append(lesson)
    opened = []
    for week in sorted(grouped):
        items = grouped[week]
        try:
            with transaction.atomic():
                found = week_violations(week, items)
        except DataNotReady as error:
            case, created = open_case(
                actor,
                kind="DATA_NOT_READY",
                week=week,
                codes=[error.code],
                dedupe_key=f"week:{week}:DATA_NOT_READY",
                source={"message": error.message},
            )
            opened += [case] if created else []
            continue
        for lesson, codes in found.items():
            case, created = open_case(
                actor,
                kind="VALIDATION",
                week=week,
                codes=codes,
                dedupe_key=f"lesson:{lesson.id}:VALIDATION",
                lesson=lesson,
                source={"detected_at": now().isoformat()},
            )
            opened += [case] if created else []
    return opened


def on_data_change(tutor_ids=(), student_ids=(), everyone=False):
    """Hook post-commit: errori registrati, mai propagati al salvataggio del dato."""
    try:
        if not LessonOccurrence.objects.filter(
            state="PUBLISHED", start_at__gt=now()
        ).exists():
            return []
        with transaction.atomic():
            if everyone:
                return detect_conflicts()
            return detect_conflicts(tutor_ids=tutor_ids, student_ids=student_ids)
    except Exception:  # pragma: no cover - difensivo, il job periodico ritenta
        log.exception("Rilevazione conflitti calendario fallita")
        return []


@transaction.atomic
def run_detection(actor, command, key):
    cmd = Command(actor, "calendar-detect-conflicts", key, command)
    if cmd.replay:
        return cmd.replay
    opened = detect_conflicts(cmd.actor)
    return cmd.done(
        {
            "opened": [case_summary(c) for c in opened],
            "open_total": ConflictCase.objects.filter(state="OPEN").count(),
            "calendar_changed": False,
            "experimental": True,
        }
    )


def lock_case(case_id, expected_version):
    case = ConflictCase.objects.select_for_update().filter(pk=case_id).first()
    if not case:
        raise DomainError("NOT_FOUND", "Pratica inesistente")
    check_version(case, expected_version)
    if case.state != "OPEN":
        raise DomainError("CONFLICT_NOT_OPEN", "Pratica già risolta")
    return case


def confirm_valid(lesson):
    """Conferma ammessa solo se la lezione è di nuovo valida sui dati correnti."""
    target = target_of(lesson, {})
    duration = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
    validate_changes([(lesson, target, duration)])


def close_case(actor, case, resolution, reason):
    before = case_summary(case)
    case.state = "RESOLVED"
    case.resolution = resolution
    case.resolution_note = reason
    case.resolved_by = actor
    case.resolved_at = now()
    case.version += 1
    case.save()
    audit(
        actor,
        "CONFLICT_RESOLVED",
        reason,
        lesson=case.lesson,
        obj=case,
        before=before,
        after=case_summary(case),
    )
    event(
        "CONFLICT_RESOLVED",
        f"conflict:{case.id}:v{case.version}",
        {"conflict_id": str(case.id)},
    )


@transaction.atomic
def resolve_conflict(actor, case_id, command, key):
    """Risoluzione riservata al centro (authorize richiede il ruolo CENTER)."""
    cmd = Command(
        actor, "calendar-conflict-resolve", key, {"case_id": str(case_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    case = lock_case(case_id, command["expected_version"])
    reason = require_reason(command)
    resolution = command["resolution"]
    lesson = None
    recovery = None
    if case.lesson_id:
        (lesson,) = lock_lessons([case.lesson_id])
    if resolution in ("CANCEL", "RESCHEDULE"):
        if lesson is None:
            raise DomainError(
                "CONFLICT_WITHOUT_LESSON", "Pratica di settimana: solo CONFIRM"
            )
        require_future_active(lesson)
    if resolution == "CANCEL":
        cancel_lesson(cmd.actor, lesson, reason, "CONFLICT_CANCEL")
        if command.get("recovery_cause"):
            obligation, _ = ensure_obligation(
                cmd.actor,
                lesson,
                {
                    "participant_ids": [
                        p.student_id for p in lesson.participants.all()
                    ],
                    "cause": command["recovery_cause"],
                    "grant_late_notice": command.get("grant_late_notice", False),
                },
                reason,
            )
            recovery = str(obligation.id)
    elif resolution == "RESCHEDULE":
        if not command.get("start_at"):
            raise DomainError("START_REQUIRED", "Nuovo inizio obbligatorio")
        change_lessons(
            cmd.actor,
            [(lesson, {"start_at": command["start_at"]})],
            "CONFLICT_RESCHEDULE",
            reason,
        )
    elif resolution == "CONFIRM":
        if lesson is not None:
            if lesson.state == "PUBLISHED" and lesson.start_at > now():
                confirm_valid(lesson)
        else:
            week_lessons = list(active_week(case.week_start))
            if week_lessons:
                snap = week_lessons[0].publication.plan.run.snapshot
                with operations_compile():
                    current_dto(
                        snap.policy,
                        case.week_start,
                        snap.data["mode"],
                        [l.id for l in week_lessons],
                    )
    else:
        raise DomainError("UNSUPPORTED_RESOLUTION", "Risoluzione non supportata")
    close_case(cmd.actor, case, resolution, reason)
    if lesson is not None and resolution in ("CANCEL", "RESCHEDULE"):
        for other in (
            ConflictCase.objects.select_for_update()
            .filter(lesson=lesson, state="OPEN")
            .exclude(pk=case.pk)
        ):
            close_case(cmd.actor, other, resolution, reason)
    if resolution in ("CANCEL", "RESCHEDULE"):
        bump_revision()
    lesson_state = None
    if lesson is not None:
        lesson.refresh_from_db()
        lesson_state = {
            "id": str(lesson.id),
            "state": lesson.state,
            "version": lesson.version,
            "start_at": lesson.start_at.isoformat(),
        }
    case.refresh_from_db()
    return cmd.done(
        {
            **case_summary(case),
            "lesson": lesson_state,
            "recovery_id": recovery,
            "experimental": True,
        }
    )


# --- ChangeRequest ----------------------------------------------------------------


def request_summary(row):
    return {
        "id": str(row.id),
        "lesson_id": str(row.lesson_id),
        "kind": row.kind,
        "proposal": row.proposal,
        "origin": row.origin,
        "student_id": str(row.student_id) if row.student_id else None,
        "reason": row.reason,
        "state": row.state,
        "resolution_note": row.resolution_note,
        "version": row.version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "awaiting": awaiting(row),
        "lesson_start_at": row.lesson.start_at.isoformat() if row.lesson_id else None,
        "tutor_id": str(row.lesson.tutor_id) if row.lesson_id else None,
    }


def may_request_changes(actor, relation, student):
    """Permesso di chiedere cambi/assenze (paper §4.2 ``can_request_changes``).

    Centro e tutor della lezione sì; il tutore legale solo con delega attiva che
    include il permesso (default negato); lo studente solo se la decisione D07
    (``PORTAL_STUDENT_CAN_REQUEST_CHANGES``, default False, da approvare) lo abilita.
    """
    if relation in ("CENTER", "TUTOR"):
        return True
    if relation == "GUARDIAN":
        return bool(student) and can_request_student_changes(actor, student)
    if relation == "STUDENT":
        return bool(getattr(settings, "PORTAL_STUDENT_CAN_REQUEST_CHANGES", False))
    return False


@transaction.atomic
def submit_change_request(actor, command, key):
    cmd = Command(
        actor,
        "calendar-change-request",
        key,
        {**command, "lesson_id": str(command["lesson_id"])},
        authorizer=authorize_any,
    )
    if cmd.replay:
        return cmd.replay
    reason = require_reason(command)
    rows = lock_lessons([command["lesson_id"]])
    lesson = rows[0]
    relation, visible = lesson_relation(cmd.actor, lesson)
    if relation is None:
        raise DomainError("NOT_FOUND", "Lezione inesistente")
    require_future_active(lesson)
    kind = command["kind"]
    student = command.get("student_id")
    if relation in ("GUARDIAN", "STUDENT"):
        if not student or str(student) not in {str(s) for s in visible}:
            raise DomainError(
                "STUDENT_REQUIRED", "Indicare uno studente visibile della lezione"
            )
    elif student and str(student) not in {
        str(s) for s in lesson.participants.values_list("student_id", flat=True)
    }:
        raise DomainError("STUDENT_REQUIRED", "Studente non partecipante")
    if not may_request_changes(cmd.actor, relation, student):
        raise DomainError("FORBIDDEN", "La delega non consente richieste di modifica")
    proposal = dict(command.get("proposal") or {})
    if kind == "RESCHEDULE":
        try:
            moment = datetime.fromisoformat(
                str(proposal.get("start_at", "")).replace("Z", "+00:00")
            )
            if moment.utcoffset() is None:
                raise ValueError
        except ValueError as error:
            raise DomainError(
                "PROPOSAL_INVALID", "start_at ISO con offset richiesto"
            ) from error
        proposal = {"start_at": moment.isoformat()}
    elif proposal:
        raise DomainError("PROPOSAL_INVALID", "Proposta ammessa solo per RESCHEDULE")
    row = ChangeRequest.objects.create(
        lesson=lesson,
        kind=kind,
        proposal=proposal,
        origin=relation,
        requested_by=cmd.actor,
        student_id=student,
        reason=reason,
    )
    audit(
        cmd.actor,
        "CHANGE_REQUESTED",
        reason,
        lesson=lesson,
        obj=row,
        after=request_summary(row),
    )
    event("CHANGE_REQUESTED", f"change:{row.id}:v1", {"change_request_id": str(row.id)})
    notifications.change_request_event(row, "change_request.submitted")
    case = None
    if kind == "ABSENCE":
        subject = f"student:{student}" if student else f"tutor:{lesson.tutor_id}"
        case, _ = open_case(
            cmd.actor,
            kind="TUTOR_ABSENCE"
            if relation == "TUTOR" and not student
            else "STUDENT_ABSENCE",
            week=week_of(lesson.start_at),
            codes=["ABSENCE_REPORTED"],
            dedupe_key=f"lesson:{lesson.id}:ABSENCE:{subject}",
            lesson=lesson,
            source={"change_request_id": str(row.id), "origin": relation},
        )
    return cmd.done(
        {
            **request_summary(row),
            "conflict_case_id": str(case.id) if case else None,
            "calendar_changed": False,
            "experimental": True,
        }
    )


def lock_request(request_id, expected_version):
    row = ChangeRequest.objects.select_for_update().filter(pk=request_id).first()
    if not row:
        raise DomainError("NOT_FOUND", "Richiesta inesistente")
    check_version(row, expected_version)
    if row.state != "SUBMITTED":
        raise DomainError("CHANGE_REQUEST_CLOSED", "Richiesta già decisa o ritirata")
    return row


@transaction.atomic
def decide_change_request(actor, request_id, command, key):
    """Decisione del centro; con apply=true esegue il comando nella stessa transazione."""
    cmd = Command(
        actor, "calendar-change-decide", key, {"request_id": str(request_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    row = lock_request(request_id, command["expected_version"])
    reason = require_reason(command)
    if command["decision"] == "ACCEPT" and awaiting(row) == "GUARDIANS":
        raise DomainError("CHANGE_AWAITING_GUARDIANS", "Prima serve la conferma dei genitori")
    if (
        command["decision"] == "ACCEPT"
        and needs_tutor_confirmation(row)
        and not (row.proposal or {}).get("tutor_confirmed")
    ):
        return cmd.done(center_accept_pending(cmd.actor, row, reason, bool(command.get("apply"))))
    applied = None
    if command["decision"] == "ACCEPT" and command.get("apply"):
        applied = apply_request(cmd.actor, row, reason)
    before = request_summary(row)
    row.state = "ACCEPTED" if command["decision"] == "ACCEPT" else "REJECTED"
    row.resolver = cmd.actor
    row.resolution_note = reason
    row.resolved_at = now()
    row.version += 1
    row.save()
    audit(
        cmd.actor,
        "CHANGE_" + row.state,
        reason,
        lesson=row.lesson,
        obj=row,
        before=before,
        after=request_summary(row),
    )
    event(
        "CHANGE_DECIDED",
        f"change:{row.id}:v{row.version}",
        {"change_request_id": str(row.id), "state": row.state},
    )
    notifications.change_request_event(row, "change_request.decided")
    return cmd.done({**request_summary(row), "applied": applied, "experimental": True})


@transaction.atomic
def withdraw_change_request(actor, request_id, command, key):
    cmd = Command(
        actor,
        "calendar-change-withdraw",
        key,
        {"request_id": str(request_id), **command},
        authorizer=authorize_any,
    )
    if cmd.replay:
        return cmd.replay
    row = lock_request(request_id, command["expected_version"])
    if row.requested_by_id != cmd.actor.id:
        raise DomainError("NOT_FOUND", "Richiesta inesistente")
    reason = require_reason(command)
    before = request_summary(row)
    row.state = "WITHDRAWN"
    row.resolution_note = reason
    row.version += 1
    row.save()
    audit(
        cmd.actor,
        "CHANGE_WITHDRAWN",
        reason,
        lesson=row.lesson,
        obj=row,
        before=before,
        after=request_summary(row),
    )
    return cmd.done({**request_summary(row), "experimental": True})


def visible_change_requests(actor):
    rows = ChangeRequest.objects.order_by("-created_at")
    if is_center(actor):
        return rows
    return rows.filter(requested_by=actor)


def apply_request(actor, row, reason):
    """Esegue la richiesta accolta (cancellazione o spostamento) nella transazione corrente."""
    (lesson,) = lock_lessons([row.lesson_id])
    require_future_active(lesson)
    if row.kind == "CANCEL":
        applied = cancel_lesson(actor, lesson, reason, "CHANGE_CANCEL")
    elif row.kind == "RESCHEDULE":
        start = datetime.fromisoformat(row.proposal["start_at"])
        (applied,) = change_lessons(
            actor, [(lesson, {"start_at": start})], "CHANGE_RESCHEDULE", reason
        )
    else:
        raise DomainError("APPLY_UNSUPPORTED", "Solo CANCEL e RESCHEDULE sono applicabili")
    bump_revision()
    return applied


FAMILY_ORIGINS = ("GUARDIAN", "STUDENT")


def needs_tutor_confirmation(row):
    """DC-APPROVAZIONI: le richieste delle famiglie le confermano centro e tutor."""
    return (
        bool(getattr(settings, "CHANGE_REQUEST_TUTOR_CONFIRMATION", True))
        and row.origin in FAMILY_ORIGINS
        and row.kind in ("CANCEL", "RESCHEDULE")
    )


def awaiting(row):
    if row.state != "SUBMITTED":
        return None
    proposal = row.proposal or {}
    if proposal.get("guardians_confirmation_required") and not proposal.get("guardians_confirmed"):
        return "GUARDIANS"
    if proposal.get("center_accepted") and not proposal.get("tutor_confirmed"):
        return "TUTOR"
    return "CENTER"


def center_accept_pending(actor, row, reason, apply):
    before = request_summary(row)
    row.proposal = {
        **(row.proposal or {}),
        "center_accepted": True,
        "center_apply": apply,
        "center_reason": reason,
        "center_by": str(actor.id),
    }
    row.version += 1
    row.save()
    audit(actor, "CHANGE_CENTER_ACCEPTED", reason, lesson=row.lesson, obj=row, before=before, after=request_summary(row))
    event("CHANGE_AWAITING_TUTOR", f"change:{row.id}:v{row.version}", {"change_request_id": str(row.id)})
    notifications.change_request_event(row, "change_request.awaiting_tutor")
    return {**request_summary(row), "applied": None, "experimental": True}


@transaction.atomic
def tutor_confirm_change_request(actor, request_id, command, key):
    """Il tutor della lezione conferma (e la richiesta si applica) o rifiuta."""
    from .scope import is_lesson_tutor

    cmd = Command(
        actor,
        "calendar-change-tutor-confirm",
        key,
        {"request_id": str(request_id), **command},
        authorizer=authorize_any,
    )
    if cmd.replay:
        return cmd.replay
    row = lock_request(request_id, command["expected_version"])
    if not is_lesson_tutor(cmd.actor, row.lesson):
        raise DomainError("NOT_FOUND", "Richiesta inesistente")
    if awaiting(row) != "TUTOR":
        raise DomainError("CHANGE_NOT_AWAITING_TUTOR", "La richiesta non attende la conferma del tutor")
    reason = require_reason(command)
    before = request_summary(row)
    applied = None
    if command["decision"] == "CONFIRM":
        row.proposal = {**row.proposal, "tutor_confirmed": True}
        if row.proposal.get("center_apply"):
            applied = apply_request(cmd.actor, row, row.proposal.get("center_reason") or reason)
        row.state = "ACCEPTED"
    else:
        row.state = "REJECTED"
    row.resolver = cmd.actor
    row.resolution_note = reason
    row.resolved_at = now()
    row.version += 1
    row.save()
    audit(cmd.actor, "CHANGE_TUTOR_" + command["decision"], reason, lesson=row.lesson, obj=row, before=before, after=request_summary(row))
    event("CHANGE_DECIDED", f"change:{row.id}:v{row.version}", {"change_request_id": str(row.id), "state": row.state})
    notifications.change_request_event(row, "change_request.decided")
    return cmd.done({**request_summary(row), "applied": applied, "experimental": True})


def guardian_confirm_change_request(actor, request_id, command, key):
    """P5 · DC-CONFERMA-GENITORI: un genitore conferma o rifiuta la modifica proposta dal tutor.

    Confermata: torna al centro, che la applica dalla scheda lezione e chiude la richiesta.
    Rifiutata: la richiesta si chiude e il tutor viene avvisato.
    """
    from apps.identity.policies import active_roles, visible_students

    cmd = Command(
        actor,
        "calendar-change-guardian-confirm",
        key,
        {"request_id": str(request_id), **command},
        authorizer=authorize_any,
    )
    if cmd.replay:
        return cmd.replay
    row = lock_request(request_id, command["expected_version"])
    if not (
        "GUARDIAN" in active_roles(cmd.actor)
        and row.student_id
        and visible_students(cmd.actor).filter(pk=row.student_id).exists()
    ):
        raise DomainError("NOT_FOUND", "Richiesta inesistente")
    if awaiting(row) != "GUARDIANS":
        raise DomainError("CHANGE_NOT_AWAITING_GUARDIANS", "La richiesta non attende la conferma dei genitori")
    reason = require_reason(command)
    before = request_summary(row)
    if command["decision"] == "CONFIRM":
        row.proposal = {
            **row.proposal,
            "guardians_confirmed": True,
            "guardians_by": str(cmd.actor.id),
            "guardians_reason": reason,
        }
    else:
        row.state = "REJECTED"
        row.resolver = cmd.actor
        row.resolution_note = reason
        row.resolved_at = now()
    row.version += 1
    row.save()
    audit(cmd.actor, "CHANGE_GUARDIANS_" + command["decision"], reason, lesson=row.lesson, obj=row, before=before, after=request_summary(row))
    event("CHANGE_GUARDIANS_ANSWERED", f"change:{row.id}:v{row.version}", {"change_request_id": str(row.id), "state": row.state})
    notifications.change_request_event(row, "change_request.decided")
    if command["decision"] == "CONFIRM":
        notifications.change_request_event(row, "change_request.submitted")
    return cmd.done({**request_summary(row), "experimental": True})
