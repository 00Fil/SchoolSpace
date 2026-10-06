"""API del pianificatore mensile (v0.9.7): orari e chiusure del centro, impegni di
studenti e tutor, calendario mensile proposto, pubblicazione e conferme."""

from datetime import date, datetime, time as dtime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.education.models import Resource, Student, TeachingRequest, Tutor
from apps.education.path_services import Conflict, DomainError
from apps.identity.policies import (
    active_roles,
    can_manage_student_availability,
    is_center,
    visible_students,
)
from apps.scheduling import autoplan, autoplan_publish
from apps.scheduling.autoplan import ROME, at, month_end
from apps.scheduling.models import (
    AutoPlan,
    AutoPlanConfirmation,
    AutoPlanLesson,
    Closure,
    Commitment,
    OpeningHours,
    PlanningAudit,
    StudyPeriod,
)

from ._privacy_common import BadPayload, center_only, handle_errors, integer, payload, text


domain_errors = handle_errors  # DomainError/Conflict sono APIException gestite da DRF


def hm(value):
    return f"{value.hour:02d}:{value.minute:02d}"


def parse_time(data, key, required=True):
    value = data.get(key)
    if value in (None, "") and not required:
        return None
    try:
        parsed = dtime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BadPayload(f"{key}: orario HH:MM richiesto") from exc
    if parsed.minute % 5:
        raise BadPayload(f"{key}: orario a multipli di 5 minuti")
    return parsed.replace(second=0, microsecond=0)


def parse_day(data, key, required=True):
    value = data.get(key)
    if value in (None, ""):
        if required:
            raise BadPayload(f"{key}: data obbligatoria")
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BadPayload(f"{key}: data ISO richiesta") from exc


def parse_month(value):
    try:
        y, m = (int(x) for x in (value or "").split("-")[:2])
        return date(y, m, 1)
    except (TypeError, ValueError) as exc:
        raise BadPayload("month: formato AAAA-MM") from exc


# --- orari di apertura e chiusure ------------------------------------------------------


def closure_json(c, linked):
    a, b = c.start_at.astimezone(ROME), c.end_at.astimezone(ROME)
    whole = a.time() == dtime(0) and b.time() == dtime(0)
    return {
        "id": str(c.id),
        "start_date": a.date().isoformat(),
        "end_date": (b - timedelta(days=1)).date().isoformat() if whole else b.date().isoformat(),
        "start_time": None if whole else hm(a),
        "end_time": None if whole else hm(b),
        "all_day": whole,
        "mode": c.mode,
        "reason": c.reason,
        "source": "SCHOOL_YEAR" if c.id in linked else "MANUAL",
    }


def setup_json():
    linked = set(StudyPeriod.objects.exclude(closure=None).values_list("closure_id", flat=True))
    today = timezone.now().astimezone(ROME).date()
    rows = Closure.objects.filter(resource__isnull=True, end_at__gte=at(today - timedelta(days=31), 0)).order_by("start_at")
    return {
        "opening_hours": [
            {"weekday": o.weekday, "start": hm(o.start_time), "end": "24:00" if hm(o.end_time) == "23:59" else hm(o.end_time)}
            for o in OpeningHours.objects.all()
        ],
        "closures": [closure_json(c, linked) for c in rows],
        "tolerance_minutes": autoplan.tolerance(),
    }


@api_view(["GET"])
@domain_errors
def setup(request):
    center_only(request)
    return Response(setup_json())


@api_view(["GET", "PUT"])
@domain_errors
def opening_hours(request):
    if request.method == "GET":  # visibile a tutti gli utenti: serve per inserire gli impegni
        if not request.user.is_authenticated:
            raise PermissionDenied()
        info = setup_json()
        return Response({"opening_hours": info["opening_hours"], "tolerance_minutes": info["tolerance_minutes"]})
    center_only(request)
    data = payload(request, required=("slots",))
    slots = data["slots"]
    if not isinstance(slots, list) or len(slots) > 70:
        raise BadPayload("slots: elenco (max 70)")
    parsed = []
    for s in slots:
        if not isinstance(s, dict) or set(s) != {"weekday", "start", "end"}:
            raise BadPayload("slot: weekday, start, end (minuti)")
        wd, a, b = s["weekday"], s["start"], s["end"]
        if not all(type(v) is int for v in (wd, a, b)) or not (0 <= wd <= 6 and 0 <= a < b <= 1440) or a % 15 or b % 15:
            raise BadPayload("Fascia non valida: giorno 0–6, minuti a passi di 15")
        parsed.append((wd, a, b))
    parsed.sort()
    for (w1, a1, b1), (w2, a2, b2) in zip(parsed, parsed[1:]):
        if w1 == w2 and a2 < b1:
            raise BadPayload("Fasce sovrapposte nello stesso giorno")
    with transaction.atomic():
        OpeningHours.objects.all().delete()
        for wd, a, b in parsed:
            OpeningHours.objects.create(
                weekday=wd,
                start_time=dtime(a // 60, a % 60),
                end_time=dtime(23, 59) if b == 1440 else dtime(b // 60, b % 60),
            )
    return Response(setup_json())


@api_view(["POST"])
@domain_errors
def closures(request):
    center_only(request)
    data = payload(request, required=("start_date",), optional=("end_date", "start_time", "end_time", "reason"), reason_default="Chiusura")
    first = parse_day(data, "start_date")
    last = parse_day(data, "end_date", required=False) or first
    if last < first:
        raise BadPayload("La fine deve essere uguale o successiva all’inizio")
    if (last - first).days > 366:
        raise BadPayload("Chiusura troppo lunga (max un anno)")
    a, b = parse_time(data, "start_time", False), parse_time(data, "end_time", False)
    if (a is None) != (b is None):
        raise BadPayload("Indica entrambe le ore oppure nessuna (tutto il giorno)")
    if a is not None:
        start_at = datetime.combine(first, a, tzinfo=ROME)
        end_at = datetime.combine(last, b, tzinfo=ROME)
    else:
        start_at = at(first, 0)
        end_at = at(last + timedelta(days=1), 0)
    if end_at <= start_at:
        raise BadPayload("La fine deve essere dopo l’inizio")
    c = Closure.objects.create(start_at=start_at, end_at=end_at, mode="ALL", resource=None, reason=text(data, "reason", 160))
    PlanningAudit.objects.create(actor=request.user, operation="closure:create", object_id=c.pk, reason=c.reason)
    return Response(closure_json(c, set()), status=201)


@api_view(["DELETE"])
@domain_errors
def closure_detail(request, pk):
    center_only(request)
    c = Closure.objects.get(pk=pk, resource__isnull=True)
    if StudyPeriod.objects.filter(closure=c).exists():
        return Response({"code": "SCHOOL_YEAR_CLOSURE", "message": "Pausa dell’anno scolastico: si modifica dall’anno scolastico"}, status=409)
    PlanningAudit.objects.create(actor=request.user, operation="closure:delete", object_id=c.pk, reason=c.reason)
    c.delete()
    return Response(status=204)


# --- impegni ------------------------------------------------------------------------------


def commitment_json(c):
    return {
        "id": str(c.id),
        "student": str(c.student_id) if c.student_id else None,
        "tutor": str(c.tutor_id) if c.tutor_id else None,
        "label": c.label,
        "kind": c.kind,
        "weekday": c.weekday,
        "date": c.date.isoformat() if c.date else None,
        "start_time": hm(c.start_time),
        "end_time": "24:00" if hm(c.end_time) == "23:59" else hm(c.end_time),
        "valid_from": c.valid_from.isoformat() if c.valid_from else None,
        "valid_until": c.valid_until.isoformat() if c.valid_until else None,
        "version": c.version,
    }


def own_tutor(user):
    return Tutor.objects.filter(account=user).first() if user.is_authenticated else None


def can_edit_owner(user, student=None, tutor=None):
    if is_center(user):
        return True
    if tutor is not None:
        return tutor.account_id == user.id and "TUTOR" in active_roles(user)
    if student.account_id and student.account_id == user.id:
        return True
    return can_manage_student_availability(user, student)


def visible_commitments(user):
    if is_center(user):
        return Commitment.objects.all()
    tutor = own_tutor(user)
    scope = Q(student__in=visible_students(user))
    if tutor and "TUTOR" in active_roles(user):
        scope |= Q(tutor=tutor)
    return Commitment.objects.filter(scope)


def commitment_fields(data, current=None):
    kind = data.get("kind", current.kind if current else "WEEKLY")
    if kind not in ("WEEKLY", "ONE_OFF"):
        raise BadPayload("kind: WEEKLY o ONE_OFF")
    out = {"kind": kind, "label": text(data, "label", 80, required=False).strip() if "label" in data or not current else current.label}
    a = parse_time(data, "start_time") if "start_time" in data or not current else current.start_time
    b_raw = data.get("end_time") if "end_time" in data or not current else None
    b = dtime(23, 59) if b_raw == "24:00" else (parse_time(data, "end_time") if b_raw is not None else current.end_time)
    if b <= a:
        raise BadPayload("La fine deve essere dopo l’inizio")
    out.update(start_time=a, end_time=b)
    if kind == "WEEKLY":
        wd = integer(data, "weekday") if "weekday" in data or not current or current.weekday is None else current.weekday
        if not 0 <= wd <= 6:
            raise BadPayload("weekday: 0 (lunedì) – 6 (domenica)")
        vf = parse_day(data, "valid_from", False) if "valid_from" in data else (current.valid_from if current else None)
        vu = parse_day(data, "valid_until", False) if "valid_until" in data else (current.valid_until if current else None)
        if vf and vu and vu < vf:
            raise BadPayload("Validità: la fine deve seguire l’inizio")
        out.update(weekday=wd, date=None, valid_from=vf, valid_until=vu)
    else:
        day = parse_day(data, "date") if "date" in data or not current or current.date is None else current.date
        out.update(date=day, weekday=None, valid_from=None, valid_until=None)
    return out


FIELDS = ("label", "kind", "weekday", "date", "start_time", "end_time", "valid_from", "valid_until")


def assert_no_overlap(fields, student, tutor, exclude=None):
    """Due impegni della stessa persona non possono sovrapporsi: settimanali nello stesso giorno
    (con periodi di validità che si intersecano) oppure occasionali nella stessa data."""
    rows = Commitment.objects.filter(
        student=student, tutor=tutor, kind=fields["kind"],
        start_time__lt=fields["end_time"], end_time__gt=fields["start_time"],
    )
    if exclude is not None:
        rows = rows.exclude(pk=exclude)
    if fields["kind"] == "WEEKLY":
        rows = rows.filter(weekday=fields["weekday"])
        if fields.get("valid_until"):
            rows = rows.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=fields["valid_until"]))
        if fields.get("valid_from"):
            rows = rows.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=fields["valid_from"]))
    else:
        rows = rows.filter(date=fields["date"])
    other = rows.order_by("start_time").first()
    if other:
        end = "24:00" if other.end_time >= dtime(23, 59) else other.end_time.strftime("%H:%M")
        raise Conflict(
            "COMMITMENT_OVERLAP",
            f"Si sovrappone a un altro impegno ({other.label or 'Impegno'} {other.start_time.strftime('%H:%M')}–{end})",
            commitment=str(other.id),
        )


@api_view(["GET", "POST"])
@domain_errors
def commitments(request):
    if request.method == "GET":
        rows = visible_commitments(request.user)
        if request.query_params.get("student"):
            rows = rows.filter(student_id=request.query_params["student"])
        if request.query_params.get("tutor"):
            rows = rows.filter(tutor_id=request.query_params["tutor"])
        if request.query_params.get("owner") == "tutor":  # Agenda: impegni di tutti i tutor
            rows = rows.filter(tutor__isnull=False)
        return Response([commitment_json(c) for c in rows[:1000]])
    data = payload(request, required=("start_time", "end_time"), optional=("student", "tutor", "weekdays", *FIELDS))
    student = tutor = None
    if bool(data.get("student")) == bool(data.get("tutor")):
        raise BadPayload("Indica uno studente oppure un tutor")
    if data.get("student"):
        student = visible_students(request.user).get(pk=data["student"]) if not is_center(request.user) else Student.objects.get(pk=data["student"])
    else:
        tutor = Tutor.objects.get(pk=data["tutor"])
    if not can_edit_owner(request.user, student, tutor):
        raise PermissionDenied("Non puoi modificare gli impegni di questa persona")
    days = data.get("weekdays")
    created = []
    with transaction.atomic():
        if days is not None:  # più giorni con lo stesso orario
            if not isinstance(days, list) or not days or len(days) > 7:
                raise BadPayload("weekdays: elenco di giorni 0–6")
            for wd in sorted(set(days)):
                fields = commitment_fields({**data, "kind": "WEEKLY", "weekday": wd})
                assert_no_overlap(fields, student, tutor)
                created.append(Commitment.objects.create(student=student, tutor=tutor, author=request.user, **fields))
        else:
            fields = commitment_fields(data)
            assert_no_overlap(fields, student, tutor)
            created.append(Commitment.objects.create(student=student, tutor=tutor, author=request.user, **fields))
    return Response([commitment_json(c) for c in created], status=201)


@api_view(["PATCH", "DELETE"])
@domain_errors
def commitment_detail(request, pk):
    c = visible_commitments(request.user).get(pk=pk)
    if not can_edit_owner(request.user, c.student, c.tutor):
        raise PermissionDenied("Non puoi modificare gli impegni di questa persona")
    if request.method == "DELETE":
        c.delete()
        return Response(status=204)
    data = payload(request, optional=FIELDS)
    fields = commitment_fields(data, c)
    assert_no_overlap(fields, c.student, c.tutor, exclude=c.pk)
    for key, value in fields.items():
        setattr(c, key, value)
    c.author = request.user
    c.save()
    return Response(commitment_json(c))


# --- calendario mensile -----------------------------------------------------------------


def lesson_json(l, names, tutors, rooms):
    return {
        "id": str(l.id),
        "request_id": str(l.request_id),
        "kind": l.request.kind,
        "subject": l.subject.name,
        "tutor": {"id": str(l.tutor_id), "name": tutors.get(l.tutor_id, "")},
        "students": [{"id": s, "name": names.get(s, "")} for s in l.participants],
        "start_at": l.start_at.isoformat(),
        "end_at": l.end_at.isoformat(),
        "mode": l.mode,
        "room": rooms.get(l.space_id),
        "overflow_minutes": l.overflow_minutes,
        "state": l.state,
        "occurrence_id": str(l.occurrence_id) if l.occurrence_id else None,
        "confirmations": [
            {
                "id": str(c.id),
                "party": c.party,
                "who": tutors.get(c.tutor_id, "") if c.party == "TUTOR" else names.get(str(c.student_id), ""),
                "minutes": c.minutes,
                "labels": c.labels,
                "status": c.status,
                "note": c.note,
            }
            for c in l.confirmations.all()
        ],
    }


def lookups():
    return (
        {str(s.id): s.display_name for s in Student.objects.all()},
        {t.id: t.display_name for t in Tutor.objects.all()},
        {r.id: r.name for r in Resource.objects.all()},
    )


def plan_json(plan, full=True):
    out = {
        "id": str(plan.id),
        "month": plan.month.isoformat()[:7],
        "state": plan.state,
        "created_at": plan.created_at.isoformat(),
        "published_at": plan.published_at.isoformat() if plan.published_at else None,
        "solver_status": plan.solver_status,
        "stats": plan.stats,
        "unplaced": plan.unplaced,
    }
    if full:
        names, tutors, rooms = lookups()
        lessons = plan.lessons.select_related("request", "subject").prefetch_related("confirmations")
        out["lessons"] = [lesson_json(l, names, tutors, rooms) for l in lessons]
    return out


def existing_json(first, last):
    from apps.calendar.models import LessonOccurrence

    rows = (
        LessonOccurrence.objects.filter(
            state__in=("PUBLISHED", "COMPLETED"), start_at__gte=at(first, 0), start_at__lt=at(last + timedelta(days=1), 0)
        )
        .select_related("subject", "tutor")
        .prefetch_related("participants__student")
        .order_by("start_at")
    )
    return [
        {
            "id": str(l.id),
            "subject": l.subject.name,
            "tutor": l.tutor.display_name,
            "students": [p.student.display_name for p in l.participants.all()],
            "start_at": l.start_at.isoformat(),
            "end_at": l.end_at.isoformat(),
            "mode": l.mode,
        }
        for l in rows[:2000]
    ]


def readiness(first):
    from config import features
    from apps.calendar.services import supported

    last = month_end(first)
    hours = OpeningHours.objects.count()
    rooms = Resource.objects.filter(kind="SPACE", active=True).count()
    reqs = TeachingRequest.objects.filter(period_start__lte=last, period_end__gte=first, subject__active=True)
    approved = list(reqs.filter(status="APPROVED").select_related("student").prefetch_related("preferred_tutors", "group__memberships"))
    pending = reqs.filter(status="PENDING").count()
    no_tutor = [r for r in approved if r.kind == "SERIES" and not r.preferred_tutors.exists()]
    students = {s for r in approved for s in autoplan.participants_of(r, first, last)}
    with_commit = set(Commitment.objects.filter(student_id__in=students).values_list("student_id", flat=True))
    tutor_ids = set(Tutor.objects.filter(active=True).values_list("id", flat=True))
    tutors_commit = set(Commitment.objects.filter(tutor_id__in=tutor_ids).values_list("tutor_id", flat=True))
    shut = Closure.objects.filter(resource__isnull=True, start_at__lt=at(last + timedelta(days=1), 0), end_at__gt=at(first, 0)).count()
    publish_ok = features.calendar_enabled() and supported()
    items = [
        {"key": "hours", "ok": hours > 0, "blocking": True, "title": "Orari di apertura",
         "text": f"{hours} fasce settimanali" if hours else "Imposta quando il centro è aperto: è un vincolo rigido.", "go": "orari"},
        {"key": "closures", "ok": True, "blocking": False, "title": "Ferie e chiusure",
         "text": f"{shut} nel mese" if shut else "Nessuna chiusura nel mese", "go": "orari"},
        {"key": "requests", "ok": bool(approved) and not pending, "blocking": not approved, "title": "Richieste approvate",
         "text": (f"{len(approved)} attive nel mese" if approved else "Nessuna richiesta approvata nel mese") + (f" · {pending} da approvare" if pending else ""), "go": "richieste"},
        {"key": "tutors", "ok": not no_tutor, "blocking": False, "title": "Tutor delle serie",
         "text": f"{len(no_tutor)} serie senza tutor: non verranno collocate" if no_tutor else "Tutte le serie hanno il tutor", "go": "richieste"},
        {"key": "rooms", "ok": rooms > 0, "blocking": False, "title": "Aule",
         "text": f"{rooms} aule attive" if rooms else "Nessuna aula: solo lezioni online", "go": "aule"},
        {"key": "student_commitments", "ok": len(with_commit) == len(students), "blocking": False, "title": "Impegni degli studenti",
         "text": f"{len(with_commit)} di {len(students)} studenti hanno inserito gli impegni" if students else "Nessuno studente coinvolto", "go": "impegni"},
        {"key": "tutor_commitments", "ok": len(tutors_commit) == len(tutor_ids), "blocking": False, "title": "Impegni dei tutor",
         "text": f"{len(tutors_commit)} di {len(tutor_ids)} tutor hanno inserito gli impegni", "go": "impegni"},
    ]
    return {
        "month": first.isoformat()[:7],
        "items": items,
        "can_generate": all(i["ok"] or not i["blocking"] for i in items),
        "can_publish": publish_ok,
        "publish_hint": "" if publish_ok else "Pubblicazione non disponibile in questo ambiente (calendario disattivato o database non protetto).",
        "tolerance_minutes": autoplan.tolerance(),
    }


@api_view(["GET", "POST"])
@domain_errors
def plans(request):
    center_only(request)
    if request.method == "POST":
        data = payload(request, required=("month",))
        first = parse_month(data["month"])
        info = readiness(first)
        if not info["can_generate"]:
            return Response({"code": "NOT_READY", "message": "Completa prima i dati obbligatori", "readiness": info}, status=409)
        plan = autoplan.plan_month(first, request.user)
        return Response(plan_json(plan), status=201)
    first = parse_month(request.query_params.get("month") or timezone.now().astimezone(ROME).strftime("%Y-%m"))
    # solo il calendario del mese (le bozze delle singole richieste vivono nella loro verifica)
    rows = AutoPlan.objects.filter(month=first, request__isnull=True).exclude(state__in=("DISCARDED", "MERGED"))
    draft = rows.filter(state="DRAFT").first()
    published = rows.filter(state="PUBLISHED").order_by("published_at")[:1]
    names, tutors, rooms = lookups()
    pending = (
        AutoPlanLesson.objects.filter(plan__month=first, state__in=("AWAITING", "REJECTED"), plan__state="PUBLISHED")
        .select_related("request", "subject").prefetch_related("confirmations")
    )
    return Response({
        "month": first.isoformat()[:7],
        "readiness": readiness(first),
        "draft": plan_json(draft) if draft else None,
        "published": [plan_json(p, full=False) for p in published],
        "follow_up": [lesson_json(l, names, tutors, rooms) for l in pending],
        "existing": existing_json(first, month_end(first)),
        "closed_days": {
            day.isoformat(): spans["ALL"][0][2]
            for day, spans in autoplan.closures(first, month_end(first)).items()
            if spans.get("ALL")
        },
    })


@api_view(["GET"])
@domain_errors
def plan_detail(request, pk):
    center_only(request)
    return Response(plan_json(AutoPlan.objects.get(pk=pk)))


@api_view(["POST"])
@domain_errors
def plan_publish(request, pk):
    center_only(request)
    result = autoplan_publish.publish(pk, request.user)
    return Response({**result, "plan": plan_json(AutoPlan.objects.get(pk=pk))})


@api_view(["POST"])
@domain_errors
def plan_discard(request, pk):
    center_only(request)
    autoplan_publish.discard(pk)
    return Response(status=204)


@api_view(["POST"])
@domain_errors
def lesson_remove(request, pk):
    """Toglie una lezione dalla bozza (il centro la pianificherà a mano o rigenerando)."""
    center_only(request)
    lesson = AutoPlanLesson.objects.select_related("plan").get(pk=pk)
    if lesson.plan.state != "DRAFT" or lesson.state != "PROPOSED":
        return Response({"code": "PLAN_NOT_DRAFT", "message": "Si possono togliere solo lezioni di una bozza"}, status=409)
    lesson.delete()
    plan = lesson.plan
    plan.stats = {**plan.stats, "placed": max(0, plan.stats.get("placed", 1) - 1), "removed": plan.stats.get("removed", 0) + 1}
    plan.save(update_fields=["stats", "updated_at"])
    return Response(plan_json(plan))


# --- conferme -----------------------------------------------------------------------------


def confirmation_json(c, names, tutors):
    l = c.lesson
    return {
        "id": str(c.id),
        "party": c.party,
        "who": tutors.get(c.tutor_id, "") if c.party == "TUTOR" else names.get(str(c.student_id), ""),
        "student_id": str(c.student_id) if c.student_id else None,
        "minutes": c.minutes,
        "labels": c.labels,
        "status": c.status,
        "note": c.note,
        "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "lesson": {
            "id": str(l.id),
            "subject": l.subject.name,
            "tutor": tutors.get(l.tutor_id, ""),
            "students": [names.get(s, "") for s in l.participants],
            "start_at": l.start_at.isoformat(),
            "end_at": l.end_at.isoformat(),
            "mode": l.mode,
            "state": l.state,
        },
    }


@api_view(["GET"])
@domain_errors
def confirmations(request):
    rows = AutoPlanConfirmation.objects.exclude(status="DRAFT").select_related("lesson__subject")
    if not is_center(request.user):
        tutor = own_tutor(request.user)
        scope = Q(party="STUDENT", student__in=visible_students(request.user))
        if tutor and "TUTOR" in active_roles(request.user):
            scope |= Q(party="TUTOR", tutor=tutor)
        rows = rows.filter(scope)
    since = timezone.now() - timedelta(days=45)
    rows = rows.filter(Q(status="PENDING") | Q(decided_at__gte=since)).order_by("lesson__start_at")
    names, tutors, _ = lookups()
    return Response([confirmation_json(c, names, tutors) for c in rows[:300]])


@api_view(["POST"])
@domain_errors
def confirmation_answer(request, pk):
    data = payload(request, required=("accept",), optional=("note",))
    if not isinstance(data["accept"], bool):
        raise BadPayload("accept: booleano")
    note = text(data, "note", 300, required=False) if data.get("note") else ""
    result = autoplan_publish.answer(pk, request.user, data["accept"], note)
    return Response(result)


def urlpatterns():
    from django.urls import path

    return [
        path("api/v1/planner/setup", setup),
        path("api/v1/planner/opening-hours", opening_hours),
        path("api/v1/planner/closures", closures),
        path("api/v1/planner/closures/<uuid:pk>", closure_detail),
        path("api/v1/planner/plans", plans),
        path("api/v1/planner/plans/<uuid:pk>", plan_detail),
        path("api/v1/planner/plans/<uuid:pk>/publish", plan_publish),
        path("api/v1/planner/plans/<uuid:pk>/discard", plan_discard),
        path("api/v1/planner/lessons/<uuid:pk>/remove", lesson_remove),
        path("api/v1/planner/confirmations", confirmations),
        path("api/v1/planner/confirmations/<uuid:pk>/answer", confirmation_answer),
        path("api/v1/commitments", commitments),
        path("api/v1/commitments/<uuid:pk>", commitment_detail),
    ]
