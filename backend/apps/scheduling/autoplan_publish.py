"""Pubblicazione del calendario mensile e conferme degli sforamenti (v0.9.7).

- Le lezioni senza sforamenti diventano subito ``LessonOccurrence`` (con prenotazioni,
  audit e notifica «lezione pubblicata», come il percorso storico).
- Le lezioni che sforano un impegno (≤ tolleranza) restano «in attesa di conferma»:
  occupano lo slot, e a ogni interessato (famiglia/studente o tutor) arriva una email e
  una notifica nell'area personale. Quando tutti accettano la lezione è pubblicata;
  se qualcuno rifiuta lo slot si libera e il centro può ripianificare.
"""

import hashlib
import json
import logging
from datetime import timedelta

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.education.path_services import Conflict, DomainError

from .autoplan import ROME
from .models import (
    AutoPlan,
    AutoPlanConfirmation,
    AutoPlanLesson,
    DemandUnit,
    PlanningPolicy,
    PlanningSnapshot,
    SchedulePlan,
    ScheduleRun,
)
from .revision import bump_revision, lock_revision

log = logging.getLogger(__name__)


def _policy():
    policy = PlanningPolicy.objects.order_by("created_at").first()
    if policy is None:
        policy = PlanningPolicy.objects.create(
            name="Pianificatore mensile",
            budget_seconds=5,
            online_onsite_requires_space=False,
            video_channels_required=False,
            partial_week_rule="INCLUDE_ACTIVE_DATES",
            unsupported_constraints=[],
            approved_for_exploration=False,
        )
    return policy


def _serial(request_id, week_start):
    used = set(
        DemandUnit.objects.filter(request_id=request_id, week_start=week_start).values_list(
            "serial", flat=True
        )
    )
    serial = 100
    while serial in used:
        serial += 1
    return serial


def materialize(lessons, actor, reason):
    """Crea le lezioni del calendario per ``lessons`` (AutoPlanLesson) in un'unica catena
    snapshot → run → proposta → pubblicazione, coerente con i vincoli del database."""
    from apps.calendar.models import (
        CalendarAudit,
        CalendarEvent,
        LessonOccurrence,
        LessonParticipant,
        Publication,
    )
    from apps.calendar.services import assert_complete, force_constraints, save_bookings, summary
    from apps.communications.calendar_hooks import notify_lesson

    if not lessons:
        return []
    from django.db import connection

    if connection.vendor == "postgresql":  # vincoli differiti fino a force_constraints()
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL DEFERRED")
    revision = lock_revision()
    keys = {l.id: f"req:{l.request_id}/auto-{str(l.id)[:8]}" for l in lessons}
    data = {
        "source": "autoplan",
        "units": [
            {
                "demand_key": keys[l.id],
                "subject": str(l.subject_id),
                "duration_minutes": int((l.end_at - l.start_at).total_seconds() // 60),
                "allowed_tutors": [str(l.tutor_id)],
                "allowed_modes": [l.mode],
                "participants": sorted(l.participants),
            }
            for l in lessons
        ],
        "tutors": [{"id": str(t), "pause_minutes": 0} for t in sorted({str(l.tutor_id) for l in lessons})],
        "resources": [
            {"id": str(s), "kind": "SPACE", "buffer_minutes": 0}
            for s in sorted({str(l.space_id) for l in lessons if l.space_id})
        ],
        "online_onsite_requires_space": False,
        "video_channels_required": False,
    }
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    days = sorted(l.start_at.astimezone(ROME).date() for l in lessons)
    snapshot = PlanningSnapshot.objects.create(
        revision=revision.revision,
        schema_version="auto-1",
        horizon_start=days[0],
        horizon_end=days[-1],
        policy=_policy(),
        policy_version=1,
        actor=actor,
        data=data,
        input_hash=digest,
        environment={},
    )
    now = timezone.now()
    run = ScheduleRun.objects.create(
        snapshot=snapshot,
        actor=actor,
        status="SUCCEEDED",
        phase="DONE",
        started_at=now,
        finished_at=now,
        result={"source": "autoplan", "lessons": [str(l.id) for l in lessons]},
    )
    assignments = [{"demand_key": keys[l.id], "lesson": str(l.id)} for l in lessons]
    plan = SchedulePlan.objects.create(
        run=run,
        state="VALIDATED",
        assignments=assignments,
        result_hash=hashlib.sha256(json.dumps(assignments, sort_keys=True).encode()).hexdigest(),
    )
    publication = Publication.objects.create(
        plan=plan, actor=actor, revision_after=revision.revision + 1, reason=reason[:200]
    )
    created = []
    for l in lessons:
        local = l.start_at.astimezone(ROME).date()
        week = local - timedelta(days=local.weekday())
        demand = DemandUnit.objects.create(
            request_id=l.request_id,
            week_start=week,
            serial=_serial(l.request_id, week),
            demand_key=keys[l.id],
        )
        occ = LessonOccurrence.objects.create(
            demand=demand,
            publication=publication,
            tutor_id=l.tutor_id,
            subject_id=l.subject_id,
            mode=l.mode,
            location="ON_SITE" if l.mode == "IN_PERSON" else "REMOTE",
            space_id=l.space_id,
            start_at=l.start_at,
            end_at=l.end_at,
            tutor_occupied_until=l.end_at,
            space_occupied_until=l.end_at if l.space_id else None,
        )
        for sid in l.participants:
            LessonParticipant.objects.create(lesson=occ, student_id=sid)
        save_bookings(occ)
        assert_complete(occ)
        CalendarAudit.objects.create(
            actor=actor, operation="PUBLISH", lesson=occ, publication=publication,
            reason=reason[:200], after=summary(occ),
        )
        CalendarEvent.objects.create(
            event_key=f"lesson:{occ.id}:v1",
            kind="LESSON_PUBLISHED",
            payload={"lesson_id": str(occ.id), "version": 1, "source": "autoplan"},
        )
        notify_lesson(occ, "LESSON_PUBLISHED")
        l.occurrence = occ
        l.state = "PUBLISHED"
        l.save(update_fields=["occurrence", "state", "updated_at"])
        created.append(occ)
    force_constraints()
    bump_revision()
    return created


def ensure_anchor(lesson, actor=None):
    """Una lezione del pianificatore mensile è legata a uno snapshot che ne fissa tutor,
    modalità, durata, partecipanti e aula ammessi (controllati dal database). Dopo una
    modifica (durata, sostituto, modalità, aula) che esce da quei limiti la lezione viene
    ri-agganciata a una nuova catena snapshot → run → proposta → pubblicazione di una sola
    lezione. Da chiamare dopo aver impostato i nuovi campi e prima del salvataggio."""
    from apps.calendar.models import Publication

    pub = lesson.publication
    try:
        data = pub.plan.run.snapshot.data or {}
    except AttributeError:
        data = {}
    key = lesson.demand.demand_key if lesson.demand_id else None
    unit = next((u for u in data.get("units", []) if u.get("demand_key") == key), None)
    minutes = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
    students = sorted(str(s) for s in lesson.participants.values_list("student_id", flat=True))
    tutors = {t.get("id"): t for t in data.get("tutors", [])}
    resources = {r.get("id") for r in data.get("resources", [])}
    ok = (
        unit is not None
        and unit.get("subject") == str(lesson.subject_id)
        and unit.get("duration_minutes") == minutes
        and str(lesson.tutor_id) in (unit.get("allowed_tutors") or [])
        and lesson.mode in (unit.get("allowed_modes") or [])
        and sorted(unit.get("participants") or []) == students
        and str(lesson.tutor_id) in tutors
        and lesson.tutor_occupied_until == lesson.end_at + timedelta(minutes=int(tutors[str(lesson.tutor_id)].get("pause_minutes") or 0))
        and (not lesson.space_id or str(lesson.space_id) in resources)
        and not data.get("online_onsite_requires_space")
        and not data.get("video_channels_required")
    )
    if ok or key is None:
        return False
    revision = lock_revision()
    lesson.tutor_occupied_until = lesson.end_at
    lesson.space_occupied_until = lesson.end_at if lesson.space_id else None
    lesson.video_id, lesson.video_occupied_until = None, None
    snap = {
        "source": "autoplan",
        "units": [{
            "demand_key": key, "subject": str(lesson.subject_id), "duration_minutes": minutes,
            "allowed_tutors": [str(lesson.tutor_id)], "allowed_modes": [lesson.mode], "participants": students,
        }],
        "tutors": [{"id": str(lesson.tutor_id), "pause_minutes": 0}],
        "resources": [{"id": str(lesson.space_id), "kind": "SPACE", "buffer_minutes": 0}] if lesson.space_id else [],
        "online_onsite_requires_space": False,
        "video_channels_required": False,
    }
    digest = hashlib.sha256(json.dumps(snap, sort_keys=True).encode()).hexdigest()
    day = lesson.start_at.astimezone(ROME).date()
    snapshot = PlanningSnapshot.objects.create(
        revision=revision.revision, schema_version="auto-1", horizon_start=day, horizon_end=day,
        policy=_policy(), policy_version=1, actor=actor, data=snap, input_hash=digest, environment={},
    )
    stamp = timezone.now()
    run = ScheduleRun.objects.create(
        snapshot=snapshot, actor=actor, status="SUCCEEDED", phase="DONE", started_at=stamp, finished_at=stamp,
        result={"source": "autoplan", "lessons": [str(lesson.id)], "reanchor": True},
    )
    assignments = [{"demand_key": key, "lesson": str(lesson.id)}]
    plan = SchedulePlan.objects.create(
        run=run, state="VALIDATED", assignments=assignments,
        result_hash=hashlib.sha256(json.dumps(assignments, sort_keys=True).encode()).hexdigest(),
    )
    lesson.publication = Publication.objects.create(
        plan=plan, actor=actor, revision_after=revision.revision + 1, reason="Rettifica della lezione"
    )
    return True


def _check_calendar(actor=None):
    from config import features
    from apps.calendar.services import authorize, supported

    if actor is not None:
        authorize(actor)
        return
    if not features.calendar_enabled():
        raise DomainError(features.DISABLED_CODE, "Calendario disattivato (FEATURE_CALENDAR)")
    if not supported():
        raise DomainError("POSTGRES_REQUIRED", "Pubblicazione disabilitata: PostgreSQL reale necessario")


@transaction.atomic
def publish(plan_id, actor):
    _check_calendar(actor)
    plan = AutoPlan.objects.select_for_update().get(pk=plan_id)
    if plan.state != "DRAFT":
        raise Conflict("PLAN_NOT_DRAFT", "Il calendario è già stato pubblicato o scartato")
    lessons = list(plan.lessons.filter(state="PROPOSED").prefetch_related("confirmations"))
    reason = (
        f"Richiesta {plan.request.subject.name}: lezioni verificate dal centro"
        if plan.request_id
        else f"Calendario mensile {plan.month:%m/%Y}"
    )
    direct = [l for l in lessons if not l.confirmations.all()]
    waiting = [l for l in lessons if l.confirmations.all()]
    try:
        with transaction.atomic():
            created = materialize(direct, actor, reason)
    except Conflict as error:
        raise Conflict(
            "PLAN_STALE",
            "Nel frattempo il calendario è cambiato: ricalcola le lezioni"
            if plan.request_id
            else "Nel frattempo il calendario è cambiato: genera di nuovo il mese",
        ) from error
    except (DomainError, DatabaseError) as error:
        # vincoli del database (aule, prenotazioni, coerenza): mai un errore 500
        log.exception("autoplan.publish_rejected", extra={"plan_id": str(plan.id)})
        raise Conflict(
            "PLAN_INVALID",
            "Alcune lezioni non rispettano i vincoli del calendario (aula, posti o "
            "sovrapposizioni): "
            + ("ricalcola le lezioni o correggile a mano" if plan.request_id else "genera di nuovo il mese"),
            detail=str(error)[:300],
        ) from error
    sent = 0
    for l in waiting:
        l.state = "AWAITING"
        l.save(update_fields=["state", "updated_at"])
        for c in l.confirmations.all():
            c.status = "PENDING"
            c.save(update_fields=["status", "updated_at"])
            notify_confirmation(c)
            sent += 1
    others = AutoPlan.objects.filter(state="DRAFT").exclude(pk=plan.pk)
    if plan.request_id:  # bozza di una richiesta: si chiudono solo le sue bozze precedenti
        others = others.filter(request_id=plan.request_id)
    else:
        others = others.filter(month=plan.month, request__isnull=True)
    others.update(state="DISCARDED")
    plan.state = "PUBLISHED"
    plan.published_at = timezone.now()
    plan.save(update_fields=["state", "published_at", "updated_at"])
    merge_public(plan, actor)
    return {"published": len(created), "awaiting": len(waiting), "confirmations_sent": sent}


def public_plan(month, actor=None, create=False):
    """L'unico calendario pubblico del mese (bozza mensile pubblicata), se esiste."""
    plan = (
        AutoPlan.objects.filter(month=month, state="PUBLISHED", request__isnull=True)
        .order_by("published_at", "created_at")
        .first()
    )
    if plan is None and create:
        plan = AutoPlan.objects.create(
            month=month, state="PUBLISHED", actor=actor, solver_status="MERGED",
            stats={"container": True}, unplaced=[], published_at=timezone.now(),
        )
    return plan


def merge_public(plan, actor):
    """Un solo calendario pubblico per mese: le lezioni appena pubblicate confluiscono nel
    calendario del loro mese; la bozza di partenza resta come «unita» (MERGED)."""
    from .autoplan import month_start

    lessons = list(plan.lessons.exclude(state__in=("PROPOSED", "DISCARDED")))
    months = {month_start(l.start_at.astimezone(ROME).date()) for l in lessons}
    if plan.request_id is None:
        months.add(plan.month)
    keep = False
    for m in sorted(months):
        target = public_plan(m) or public_plan(m, actor, create=True)
        if target.pk == plan.pk:
            keep = True  # è il calendario pubblico del mese
            continue
        mine = [l.pk for l in lessons if month_start(l.start_at.astimezone(ROME).date()) == m]
        if mine:
            AutoPlanLesson.objects.filter(pk__in=mine).update(plan=target)
            target.stats = {**target.stats, "merged": target.stats.get("merged", 0) + len(mine)}
            target.save(update_fields=["stats", "updated_at"])
    if not keep:
        plan.state = "MERGED"
        plan.stats = {**plan.stats, "merged": True}
        plan.save(update_fields=["state", "stats", "updated_at"])


@transaction.atomic
def discard(plan_id):
    plan = AutoPlan.objects.select_for_update().get(pk=plan_id)
    if plan.state != "DRAFT":
        raise Conflict("PLAN_NOT_DRAFT", "Solo una bozza può essere scartata")
    plan.state = "DISCARDED"
    plan.save(update_fields=["state", "updated_at"])
    plan.lessons.update(state="DISCARDED")


# --- conferme -----------------------------------------------------------------------


def confirmation_recipients(conf):
    """Chi riceve la richiesta: il tutor, oppure le famiglie (e lo studente con account)."""
    from apps.communications.calendar_hooks import _active_role
    from apps.communications.services import Recipient
    from apps.identity.policies import notification_guardian_links

    now = timezone.now()
    if conf.party == "TUTOR":
        account = conf.tutor.account
        return [Recipient(account, {"role": "tutor"})] if account and account.is_active else []
    student = conf.student
    out = []
    links = list(notification_guardian_links([student.id], now).select_related("account"))
    guardians = _active_role([l.account_id for l in links], "GUARDIAN", now)
    for link in links:
        if link.account.is_active and link.account_id in guardians:
            out.append(Recipient(link.account, {"role": "guardian", "student_names": [student.display_name]}))
    if student.account_id and student.account.is_active:
        if student.account_id in _active_role([student.account_id], "STUDENT", now):
            out.append(Recipient(student.account, {"role": "student", "student_names": [student.display_name]}))
    return out


def notify_confirmation(conf):
    from apps.communications.services import emit

    lesson = conf.lesson
    return emit(
        "autoplan.confirmation_requested",
        {
            "confirmation_id": str(conf.id),
            "subject_name": lesson.subject.name,
            "mode": lesson.mode,
            "start_at": lesson.start_at.isoformat(),
            "end_at": lesson.end_at.isoformat(),
            "overflow_minutes": conf.minutes,
            "commitment_labels": ", ".join(conf.labels)[:120],
            "party": conf.party,
        },
        confirmation_recipients(conf),
        idempotency_key=f"autoplan:confirm:{conf.id}",
        subject_ref=f"autoplan-confirmation:{conf.id}",
    )


def can_answer(user, conf):
    from apps.identity.policies import is_center, visible_students

    if is_center(user):
        return True
    if conf.party == "TUTOR":
        return bool(conf.tutor.account_id) and conf.tutor.account_id == user.id
    return visible_students(user).filter(pk=conf.student_id).exists()


@transaction.atomic
def answer(conf_id, actor, accept, note=""):
    conf = (
        AutoPlanConfirmation.objects.select_for_update(of=("self",))
        .select_related("lesson", "tutor", "student")
        .get(pk=conf_id)
    )
    if not can_answer(actor, conf):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Questa conferma non ti riguarda")
    if conf.status != "PENDING" or conf.lesson.state != "AWAITING":
        raise Conflict("ALREADY_ANSWERED", "Questa proposta è già stata gestita")
    conf.status = "ACCEPTED" if accept else "REJECTED"
    conf.decided_by = actor
    conf.decided_at = timezone.now()
    conf.note = (note or "")[:300]
    conf.save()
    lesson = conf.lesson
    if not accept:
        lesson.state = "REJECTED"
        lesson.save(update_fields=["state", "updated_at"])
        lesson.confirmations.filter(status="PENDING").update(status="REJECTED", note="Annullata: un altro interessato ha rifiutato")
        return {"lesson_state": "REJECTED"}
    if lesson.confirmations.exclude(status="ACCEPTED").exists():
        return {"lesson_state": "AWAITING"}
    _check_calendar()
    try:
        with transaction.atomic():
            materialize([lesson], actor, "Sforamento confermato dagli interessati")
    except Conflict:
        lesson.state = "REJECTED"
        lesson.save(update_fields=["state", "updated_at"])
        return {"lesson_state": "REJECTED", "message": "Lo slot non è più libero: il centro ripianificherà"}
    return {"lesson_state": "PUBLISHED"}
