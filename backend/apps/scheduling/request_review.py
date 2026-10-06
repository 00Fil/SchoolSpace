"""Verifica delle lezioni di una richiesta (v0.9.9).

Flusso: richiesta inserita dal centro (o approvata) → il motore viene ricalcolato
automaticamente per quella richiesta → bozza dedicata con le lezioni collocate →
il centro vede l'elenco e le incongruenze (lezioni non collocate, conflitti nati nel
frattempo, sforamenti da confermare), le risolve (sposta, aggiungi, togli, ricalcola)
e conferma: le lezioni vanno in calendario e la richiesta diventa «completata».
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.education.path_services import Conflict, DomainError

from . import autoplan
from .autoplan import ROME, REASONS
from .models import AutoPlan, AutoPlanLesson
from .slots import Finder, _hits, explain

log = logging.getLogger(__name__)

# Codici di conflitto che rendono una lezione proposta non più valida.
AVAILABILITY = {"TUTOR_AVAILABILITY", "STUDENT_AVAILABILITY"}


def current_plan(req):
    return (
        AutoPlan.objects.filter(request=req, state="DRAFT")
        .order_by("-created_at")
        .first()
    )


def plannable(req):
    return req.status == "APPROVED" and not req.curriculum_block_id


def run(req, actor, now=None, month=None):
    """Ricalcola il motore per la richiesta (bozza dedicata, stato «da verificare»)."""
    if not plannable(req):
        raise Conflict(
            "NOT_PLANNABLE", "Solo le richieste approvate del centro si ricalcolano qui"
        )
    return autoplan.plan_request(req, actor, now=now, month=month)


def auto_run(req, actor):
    """Ricalcolo automatico dopo inserimento/approvazione: non blocca mai il salvataggio
    della richiesta. Se il motore fallisce la richiesta resta da verificare senza bozza."""
    if not plannable(req):
        return None
    try:
        return run(req, actor)
    except Exception:
        log.exception("autoplan.request_failed", extra={"request_id": str(req.id)})
        type(req).objects.filter(pk=req.pk).update(
            planning_state="REVIEW", completed_at=None
        )
        req.planning_state = "REVIEW"
        return None


def cancel(req):
    """Richiesta rifiutata o ritirata: le lezioni proposte si liberano."""
    from .corrections import discard_for_plans

    with transaction.atomic():
        discard_for_plans(AutoPlan.objects.filter(request=req, state="DRAFT").values_list("id", flat=True))
        for plan in AutoPlan.objects.filter(request=req, state="DRAFT"):
            plan.state = "DISCARDED"
            plan.save(update_fields=["state", "updated_at"])
            plan.lessons.filter(state="PROPOSED").update(state="DISCARDED")
        if req.planning_state == "REVIEW":
            type(req).objects.filter(pk=req.pk).update(planning_state="")
            req.planning_state = ""


# --- incongruenze ---------------------------------------------------------------------


def _minutes(lesson):
    return int((lesson.end_at - lesson.start_at).total_seconds() // 60)


def lesson_issues(plan, now=None):
    """{lesson_id: [codici]} per le lezioni proposte che non sono più valide: orario passato,
    centro chiuso, impegni (oltre allo sforamento già previsto), altre lezioni o aula occupata."""
    lessons = list(
        plan.lessons.filter(state="PROPOSED").prefetch_related("confirmations")
    )
    if not lessons:
        return {}
    from apps.education.models import Resource

    out = {}
    groups = {}
    rooms = {
        r.id: r
        for r in Resource.objects.filter(
            pk__in={l.space_id for l in lessons if l.space_id}, kind="SPACE", active=True
        )
    }
    for l in lessons:
        key = (tuple(sorted(l.participants)), l.mode, _minutes(l))
        groups.setdefault(key, []).append(l)
    ids = [l.id for l in lessons]
    for (students, mode, length), rows in groups.items():
        days = [l.start_at.astimezone(ROME).date() for l in rows]
        finder = Finder(
            students,
            sorted({str(l.tutor_id) for l in rows}),
            mode,
            length,
            min(days),
            max(days),
            ignore_auto=ids,
        )
        for l in rows:
            codes = [
                c
                for c in finder.check(l.tutor_id, l.start_at, now)["codes"]
                if c != "NO_ROOM"
            ]
            if (
                l.confirmations.all()
            ):  # sforamento entro la tolleranza: si chiede conferma
                codes = [c for c in codes if c not in AVAILABILITY]
            room = rooms.get(l.space_id) if l.space_id else None
            if l.space_id and _hits(
                finder.busy_r.get(str(l.space_id), []), l.start_at, l.end_at
            ):
                codes.append("NO_ROOM")
            elif l.mode == "IN_PERSON" and (
                room is None or (room.student_capacity or 0) < len(l.participants)
            ):
                codes.append("NO_ROOM")  # in presenza serve un'aula attiva abbastanza grande
            if not l.participants:
                codes.append("NO_STUDENTS")
            if codes:
                out[l.id] = codes
    return out


def review_json(req, plan, now=None):
    """Elenco delle lezioni proposte e incongruenze da gestire prima del completamento."""
    from api.autoplanner import lesson_json, lookups

    base = {
        "request_id": str(req.id),
        "planning_state": req.planning_state,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }
    now_ = now or timezone.now()
    months = [m.isoformat()[:7] for m in autoplan.request_months(req, now_)]
    if req.kind == "SINGLE":
        months = months[:1]
    base["months"] = months
    base["month"] = (
        plan.month.isoformat()[:7] if plan is not None and plan.month else (months[0] if months else None)
    )
    if plan is None:
        return {
            **base,
            "plan": None,
            "lessons": [],
            "issues": [],
            "missing": 0,
            "conflicts": 0,
            "confirmations": 0,
            "can_complete": False,
        }
    names, tutors, rooms = lookups()
    bad = lesson_issues(plan, now)
    lessons = []
    for l in (
        plan.lessons.filter(state="PROPOSED")
        .select_related("request", "subject")
        .prefetch_related("confirmations")
    ):
        row = lesson_json(l, names, tutors, rooms)
        codes = bad.get(l.id, [])
        row["conflicts"] = explain(codes)
        row["conflict_codes"] = codes
        lessons.append(row)
    issues = []
    for row in lessons:
        if row["conflicts"]:
            issues.append(
                {
                    "kind": "CONFLICT",
                    "blocking": True,
                    "lesson_id": row["id"],
                    "start_at": row["start_at"],
                    "message": "Non più valida: " + "; ".join(row["conflicts"]) + ".",
                }
            )
    for u in plan.unplaced:
        issues.append(
            {
                "kind": "MISSING",
                "blocking": False,
                "reason": u.get("reason"),
                "missing": u.get("missing", 0),
                "weeks": u.get("weeks", []),
                "message": u.get("message") or REASONS.get(u.get("reason"), ""),
            }
        )
    for row in lessons:
        if row["confirmations"] and not row["conflicts"]:
            who = ", ".join(
                f"{c['who']} ({c['minutes']} min)" for c in row["confirmations"]
            )
            issues.append(
                {
                    "kind": "CONFIRM",
                    "blocking": False,
                    "lesson_id": row["id"],
                    "start_at": row["start_at"],
                    "message": f"Sfora un impegno di {who}: alla conferma parte la richiesta di consenso.",
                }
            )
    missing = sum(u.get("missing", 0) for u in plan.unplaced)
    conflicts = sum(1 for r in lessons if r["conflicts"])
    from api.autoplanner import plan_json

    return {
        **base,
        "plan": plan_json(plan, full=False),
        "lessons": lessons,
        "issues": issues,
        "missing": missing,
        "conflicts": conflicts,
        "confirmations": sum(1 for r in lessons if r["confirmations"]),
        "can_complete": conflicts == 0,
    }


# --- correzioni manuali -----------------------------------------------------------------


def allowed_tutors(req, plan=None):
    """Tutor ammessi: quello scelto (ricorrente / obbligatorio), altrimenti i competenti,
    con prima il preferito e quello già usato nella bozza (un tutor per richiesta)."""
    today = timezone.now().astimezone(ROME).date()
    chosen = [t.id for t in req.preferred_tutors.all() if t.active]
    if req.kind == "SERIES" or req.tutor_choice == "REQUIRED":
        return [str(t) for t in chosen[:1]]
    competent = [
        t.id
        for t in autoplan.competent_tutors(
            req, max(req.period_start, today), req.period_end
        )
    ]
    used = []
    if plan is not None:
        used = list(
            dict.fromkeys(
                plan.lessons.filter(state="PROPOSED").values_list("tutor_id", flat=True)
            )
        )
    return [str(t) for t in dict.fromkeys([*used, *chosen, *competent])]


def _participants(req):
    first, last = req.period_start, req.period_end
    return [str(s) for s in autoplan.participants_of(req, first, last)]


def _mode(req):
    return req.mode or "IN_PERSON"


def plan_bounds(req, plan):
    """Giorni su cui lavora la bozza: il mese calcolato (le richieste singole: il loro periodo)."""
    if plan is None or req.kind == "SINGLE" or not plan.month:
        return req.period_start, req.period_end
    return (
        max(req.period_start, autoplan.month_start(plan.month)),
        min(req.period_end, autoplan.month_end(plan.month)),
    )


def _window(req, date_from=None, date_to=None, plan=None):
    today = timezone.now().astimezone(ROME).date()
    lo, hi = plan_bounds(req, plan)
    first = max(date_from or lo, lo, today)
    last = min(
        date_to or first + timedelta(days=13),
        hi,
        first + timedelta(days=31),
    )
    return first, max(first, last)


def options(req, date_from=None, date_to=None, lesson=None, limit=15):
    plan = current_plan(req)
    first, last = _window(req, date_from, date_to, plan)
    tutors = (
        [str(lesson.tutor_id)]
        if lesson is not None
        and (req.kind == "SERIES" or req.tutor_choice == "REQUIRED")
        else allowed_tutors(req, plan)
    )
    if not tutors:
        return {
            "options": [],
            "date_from": first.isoformat(),
            "date_to": last.isoformat(),
            "message": "Nessun tutor disponibile per questa richiesta: sceglilo nella richiesta o aggiungi la competenza.",
        }
    ignore = [lesson.id] if lesson is not None else []
    finder = Finder(
        _participants(req),
        tutors,
        _mode(req),
        req.duration_minutes,
        first,
        last,
        ignore_auto=ignore,
    )
    prefer = None
    if lesson is not None:
        local = lesson.start_at.astimezone(ROME)
        prefer = local.hour * 60 + local.minute
    found = finder.suggest(
        first, last, prefer_tutor=tutors[0], prefer_minute=prefer, limit=limit * 2
    )
    # al massimo una lezione al giorno per richiesta (come nel motore)
    taken = _taken_days(req, plan, skip=lesson)
    found = [o for o in found if o["date"] not in taken][:limit]
    return {
        "options": found,
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
    }


def _taken_days(req, plan, skip=None):
    """Giorni in cui la richiesta ha già una lezione (proposta o in calendario)."""
    from apps.calendar.models import LessonOccurrence

    days = set()
    if plan is not None:
        rows = plan.lessons.filter(state="PROPOSED")
        if skip is not None:
            rows = rows.exclude(pk=skip.pk)
        days |= {
            s.astimezone(ROME).date().isoformat()
            for s in rows.values_list("start_at", flat=True)
        }
    published = LessonOccurrence.objects.filter(
        demand__request=req, state__in=("PUBLISHED", "COMPLETED")
    ).values_list("start_at", flat=True)
    days |= {s.astimezone(ROME).date().isoformat() for s in published}
    return days


def _validate(req, tutor_id, start_at, ignore=()):
    tutors = allowed_tutors(req, current_plan(req))
    if str(tutor_id) not in tutors:
        raise DomainError("TUTOR_NOT_ALLOWED", "Tutor non ammesso per questa richiesta")
    local = start_at.astimezone(ROME).date()
    if not (req.period_start <= local <= req.period_end):
        raise DomainError(
            "OUT_OF_PERIOD", "L’orario è fuori dal periodo della richiesta"
        )
    lo, hi = plan_bounds(req, current_plan(req))
    if not (lo <= local <= hi):
        raise DomainError(
            "OUT_OF_MONTH",
            "L’orario è fuori dal mese in verifica: gli altri mesi si pianificano dal calendario mensile",
        )
    finder = Finder(
        _participants(req),
        [tutor_id],
        _mode(req),
        req.duration_minutes,
        local,
        local,
        ignore_auto=list(ignore),
    )
    res = finder.check(tutor_id, start_at)
    if res["codes"]:
        raise Conflict(
            "SLOT_NOT_FREE",
            "Orario non disponibile: " + "; ".join(explain(res["codes"])),
            codes=res["codes"],
        )
    return res["space_id"]


def _draft(req):
    plan = current_plan(req)
    if plan is None:
        raise Conflict("NO_DRAFT", "Nessuna bozza da verificare: ricalcola le lezioni")
    return plan


def _week(day):
    return (day - timedelta(days=day.weekday())).isoformat()


@transaction.atomic
def add_lesson(req, start_at, tutor_id):
    plan = _draft(req)
    space = _validate(req, tutor_id, start_at)
    lesson = AutoPlanLesson.objects.create(
        plan=plan,
        request=req,
        tutor_id=tutor_id,
        subject_id=req.subject_id,
        mode=_mode(req),
        space_id=space,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=req.duration_minutes),
        participants=_participants(req),
    )
    week = _week(start_at.astimezone(ROME).date())
    rows = [dict(u) for u in plan.unplaced]
    target = next(
        (u for u in rows if week in (u.get("weeks") or [])), rows[0] if rows else None
    )
    if target is not None:
        target["missing"] = max(0, target.get("missing", 0) - 1)
        if week in (target.get("weeks") or []):
            target["weeks"] = [w for w in target["weeks"] if w != week]
    plan.unplaced = [u for u in rows if u.get("missing", 0) > 0]
    plan.stats = {
        **plan.stats,
        "placed": plan.stats.get("placed", 0) + 1,
        "manual": plan.stats.get("manual", 0) + 1,
    }
    plan.save(update_fields=["unplaced", "stats", "updated_at"])
    return lesson


@transaction.atomic
def move_lesson(lesson, start_at, tutor_id=None):
    plan = lesson.plan
    if plan.state != "DRAFT" or lesson.state != "PROPOSED" or not plan.request_id:
        raise Conflict(
            "PLAN_NOT_DRAFT", "Si possono spostare solo lezioni da verificare"
        )
    req = plan.request
    tutor_id = tutor_id or lesson.tutor_id
    space = _validate(req, tutor_id, start_at, ignore=[lesson.id])
    lesson.confirmations.all().delete()  # il nuovo orario non sfora alcun impegno
    lesson.tutor_id = tutor_id
    lesson.start_at = start_at
    lesson.end_at = start_at + timedelta(minutes=req.duration_minutes)
    lesson.space_id = space if lesson.mode == "IN_PERSON" else None
    lesson.overflow_minutes = 0
    lesson.save()
    return lesson


@transaction.atomic
def remove_lesson(lesson):
    plan = lesson.plan
    if plan.state != "DRAFT" or lesson.state != "PROPOSED" or not plan.request_id:
        raise Conflict(
            "PLAN_NOT_DRAFT", "Si possono togliere solo lezioni da verificare"
        )
    week = _week(lesson.start_at.astimezone(ROME).date())
    lesson.delete()
    rows = [dict(u) for u in plan.unplaced]
    mine = next((u for u in rows if u.get("reason") == "REMOVED"), None)
    if mine is None:
        req = plan.request
        mine = {
            "request_id": str(req.id),
            "subject": req.subject.name,
            "who": autoplan.request_who(req),
            "kind": req.kind,
            "missing": 0,
            "reason": "REMOVED",
            "message": REASONS["REMOVED"],
            "weeks": [],
        }
        rows.append(mine)
    mine["missing"] += 1
    mine["weeks"] = sorted(set(mine["weeks"]) | {week})
    plan.unplaced = rows
    plan.stats = {
        **plan.stats,
        "placed": max(0, plan.stats.get("placed", 1) - 1),
        "removed": plan.stats.get("removed", 0) + 1,
    }
    plan.save(update_fields=["unplaced", "stats", "updated_at"])


def complete(req, actor, accept_missing=False, now=None, publish_now=False):
    """Conferma della verifica: le lezioni entrano nella bozza del calendario del mese
    (rettifica da pubblicare) oppure, se il gestore lo sceglie, sono pubblicate subito
    (quelle con sforamento attendono il consenso degli interessati). La richiesta diventa
    completata."""
    from . import corrections

    if req.planning_state == "DONE":
        raise Conflict("ALREADY_DONE", "Richiesta già completata")
    plan = _draft(req)
    bad = lesson_issues(plan, now)
    if bad:
        raise Conflict(
            "UNRESOLVED_CONFLICTS",
            f"{len(bad)} lezioni non sono più valide: spostale o toglile prima di confermare",
            conflicts=len(bad),
        )
    missing = sum(u.get("missing", 0) for u in plan.unplaced)
    if missing and not accept_missing:
        raise Conflict(
            "MISSING_LESSONS",
            f"{missing} lezioni non sono state collocate: aggiungile a mano oppure conferma senza",
            missing=missing,
        )
    with transaction.atomic():
        row, result = corrections.propose_plan(actor, plan, publish_now=publish_now)
        result = {**result, "draft": row is not None, "correction_id": str(row.id) if row else None}
        stamp = timezone.now()
        type(req).objects.filter(pk=req.pk).update(
            planning_state="DONE", completed_at=stamp
        )
        req.planning_state, req.completed_at = "DONE", stamp
    return {**result, "missing": missing}
