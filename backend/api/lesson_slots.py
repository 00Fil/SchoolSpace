"""Nuova lezione dal gestionale e orari suggeriti dal motore (v0.9.8).

- ``POST /lessons/options/``: orari possibili per una lezione (studente, materia, modalità,
  durata, tutor facoltativo) in un intervallo di giorni; con ``start_at`` verifica anche
  quell'orario preciso (trascinamento in agenda).
- ``POST /lessons/``: crea subito la lezione, come se la famiglia l'avesse chiesta e il
  centro l'avesse approvata e piazzata: richiesta singola APPROVATA a orario fisso +
  lezione pubblicata (notifica a famiglia e tutor). Il pianificatore mensile la considera
  già coperta.
- ``GET /recovery-obligations/<id>/options/``: orari suggeriti per un recupero.
"""

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.education.path_services import DomainError
from apps.identity.policies import is_center
from apps.scheduling.autoplan import ROME
from apps.scheduling.slots import Finder, competent, explain

from .planning_data import OffsetDateTime

MAX_DAYS = 31


def _center(request):
    if not is_center(request.user):
        raise PermissionDenied()


class OptionsCmd(serializers.Serializer):
    student_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    mode = serializers.ChoiceField(["IN_PERSON", "ONLINE"])
    duration_minutes = serializers.IntegerField(min_value=30, max_value=240)
    tutor_id = serializers.UUIDField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    start_at = OffsetDateTime(required=False, allow_null=True)


class CreateCmd(serializers.Serializer):
    student_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    mode = serializers.ChoiceField(["IN_PERSON", "ONLINE"])
    duration_minutes = serializers.ChoiceField([60, 90, 120])
    tutor_id = serializers.UUIDField()
    start_at = OffsetDateTime()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


def _range(data):
    today = timezone.now().astimezone(ROME).date()
    first = max(data.get("date_from") or today, today)
    last = data.get("date_to") or first + timedelta(days=13)
    last = min(max(last, first), first + timedelta(days=MAX_DAYS))
    return first, last


def _tutors(data, first, last):
    if data.get("tutor_id"):
        return [data["tutor_id"]]
    return competent(data["subject_id"], data["mode"], first, last)


def _check(finder, tutor_id, start):
    res = finder.check(tutor_id, start)
    return {
        "tutor_id": str(tutor_id),
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=finder.length)).isoformat(),
        "ok": not res["codes"],
        "codes": res["codes"],
        "reasons": explain(res["codes"]),
        "space_id": str(res["space_id"]) if res["space_id"] else None,
    }


@api_view(["POST"])
def lesson_options(request):
    _center(request)
    cmd = OptionsCmd(data=request.data)
    cmd.is_valid(raise_exception=True)
    data = cmd.validated_data
    first, last = _range(data)
    start = data.get("start_at")
    if start:
        day = start.astimezone(ROME).date()
        first, last = min(first, day), max(last, day)
    tutors = _tutors(data, first, last)
    if not tutors:
        return Response({"options": [], "check": None, "tutors": 0, "message": "Nessun tutor ha la competenza approvata per questa materia e modalità."})
    finder = Finder([data["student_id"]], tutors, data["mode"], data["duration_minutes"], first, last)
    check = _check(finder, data.get("tutor_id") or tutors[0], start) if start else None
    prefer = None
    if start:
        local = start.astimezone(ROME)
        prefer = local.hour * 60 + local.minute
    options = finder.suggest(first, last, prefer_tutor=data.get("tutor_id"), prefer_minute=prefer, limit=15)
    return Response({"options": options, "check": check, "tutors": len(tutors), "date_from": first.isoformat(), "date_to": last.isoformat()})


@api_view(["POST"])
def lesson_create(request):
    _center(request)
    cmd = CreateCmd(data=request.data)
    cmd.is_valid(raise_exception=True)
    data = cmd.validated_data
    try:
        lesson = create_lesson(request.user, data)
    except IntegrityError:
        return Response({"code": "BOOKING_CONFLICT", "message": "Orario appena occupato da un’altra lezione: scegline un altro."}, status=409)
    from apps.calendar.services import summary

    return Response({"lesson": summary(lesson)}, status=201)


class _Draft:
    """Lezione «al volo» con l'interfaccia minima che ``materialize`` si aspetta."""

    def __init__(self, **kw):
        import uuid

        self.id = uuid.uuid4()
        self.occurrence = None
        self.state = "PROPOSED"
        self.__dict__.update(kw)

    def save(self, **kwargs):
        return None


@transaction.atomic
def create_lesson(actor, data):
    from apps.education.models import Student, Subject, TeachingRequest, Tutor
    from apps.scheduling.autoplan_publish import materialize

    start = data["start_at"]
    minutes = int(data["duration_minutes"])
    if start.second or start.microsecond:
        raise DomainError("MINUTE_PRECISION", "Precisione al minuto richiesta")
    student = Student.objects.filter(pk=data["student_id"]).first()
    subject = Subject.objects.filter(pk=data["subject_id"], active=True).first()
    tutor = Tutor.objects.filter(pk=data["tutor_id"], active=True).first()
    if not (student and subject and tutor):
        raise DomainError("NOT_FOUND", "Studente, materia o tutor non trovati")
    local = start.astimezone(ROME)
    day = local.date()
    if tutor.id not in competent(subject.id, data["mode"], day, day):
        raise DomainError("UNQUALIFIED_TUTOR", f"{tutor.display_name} non ha la competenza approvata per {subject.name} in questa modalità")
    finder = Finder([student.id], [tutor.id], data["mode"], minutes, day, day)
    res = finder.check(tutor.id, start)
    if res["codes"]:
        raise DomainError(
            "CALENDAR_VALIDATION_FAILED",
            "Orario non disponibile: " + "; ".join(explain(res["codes"])),
            violations=res["codes"],
        )
    req = TeachingRequest.objects.create(
        student=student,
        subject=subject,
        mode=data["mode"],
        duration_minutes=minutes,
        sessions_per_week=1,
        period_start=day,
        period_end=day,
        status="APPROVED",
        origin="CENTER",
        requested_by=actor,
        tutor_choice="REQUIRED",
        kind="SINGLE",
        fixed_time=local.time().replace(second=0, microsecond=0),
        notes=(data.get("notes") or "Lezione creata dal centro")[:500],
        reviewed_at=timezone.now(),
    )
    req.preferred_tutors.set([tutor])
    draft = _Draft(
        request_id=req.id,
        subject_id=subject.id,
        tutor_id=tutor.id,
        mode=data["mode"],
        space_id=res["space_id"],
        start_at=start,
        end_at=start + timedelta(minutes=minutes),
        participants=[str(student.id)],
    )
    (lesson,) = materialize([draft], actor, "Lezione creata dal centro")
    return lesson


@api_view(["GET"])
def recovery_options(request, pk):
    _center(request)
    from apps.calendar.models import RecoveryObligation
    from apps.calendar import recovery_policy

    ob = RecoveryObligation.objects.select_related("origin_lesson").filter(pk=pk).first()
    if not ob:
        raise DomainError("NOT_FOUND", "Recupero inesistente")
    origin = ob.origin_lesson
    mode = request.query_params.get("mode") or origin.mode
    today = timezone.now().astimezone(ROME).date()
    first = today
    try:
        if request.query_params.get("from"):
            first = max(today, date.fromisoformat(request.query_params["from"]))
    except ValueError:
        pass
    due = recovery_policy.due_by(origin.start_at)
    last = first + timedelta(days=20)
    if due:
        last = min(last, due)
    if last < first:
        return Response({"options": [], "due_by": due.isoformat() if due else None, "message": "Il termine per il recupero è già passato."})
    tutor_param = request.query_params.get("tutor_id")
    tutors = [tutor_param] if tutor_param else [origin.tutor_id, *competent(origin.subject_id, mode, first, last)]
    finder = Finder(ob.participants, tutors, mode, ob.minutes_remaining, first, last)
    local = origin.start_at.astimezone(ROME)
    options = finder.suggest(first, last, prefer_tutor=origin.tutor_id, prefer_minute=local.hour * 60 + local.minute, limit=15)
    return Response({
        "options": options,
        "mode": mode,
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
        "due_by": due.isoformat() if due else None,
        "minutes": ob.minutes_remaining,
    })
