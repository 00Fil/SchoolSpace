"""Verifica delle lezioni di una richiesta (v0.9.9): dopo l'inserimento o l'approvazione
il motore colloca subito le lezioni; qui il centro vede l'elenco, gestisce le
incongruenze e completa la richiesta.

- ``GET  /teaching-requests/<id>/planning``            elenco + incongruenze
- ``POST /teaching-requests/<id>/planning/rerun``      ricalcola il motore
- ``POST /teaching-requests/<id>/planning/options``    orari liberi (aggiunta o spostamento)
- ``POST /teaching-requests/<id>/planning/lessons``    aggiunge una lezione a mano
- ``POST /teaching-requests/<id>/planning/complete``   conferma: pubblica e completa
- ``POST /planner/request-lessons/<id>/move``           sposta una lezione proposta
- ``POST /planner/request-lessons/<id>/remove``         toglie una lezione proposta
"""

from datetime import date, datetime

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.education.models import TeachingRequest
from apps.scheduling import request_review
from apps.scheduling.models import AutoPlanLesson

from ._privacy_common import BadPayload, center_only, handle_errors, payload


def _instant(data, key):
    value = data.get(key)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BadPayload(f"{key}: istante ISO con offset richiesto") from exc
    if (
        parsed.utcoffset() is None
        or parsed.second
        or parsed.microsecond
        or parsed.minute % 5
    ):
        raise BadPayload(f"{key}: istante ISO con offset, a multipli di 5 minuti")
    return parsed


def _day(data, key):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BadPayload(f"{key}: data ISO richiesta") from exc


def _req(pk):
    return (
        TeachingRequest.objects.select_related("subject", "student")
        .prefetch_related("preferred_tutors", "participants")
        .get(pk=pk)
    )


def _out(req, status=200, **extra):
    req.refresh_from_db(fields=["planning_state", "completed_at", "status"])
    return Response(
        {**request_review.review_json(req, request_review.current_plan(req)), **extra},
        status=status,
    )


@api_view(["GET"])
@handle_errors
def planning(request, pk):
    center_only(request)
    return _out(_req(pk))


@api_view(["POST"])
@handle_errors
def rerun(request, pk):
    center_only(request)
    data = payload(request, optional=("month",))
    month = data.get("month")
    if month not in (None, ""):
        try:
            month = date.fromisoformat(f"{str(month)[:7]}-01")
        except (TypeError, ValueError) as exc:
            raise BadPayload("month: mese AAAA-MM richiesto") from exc
    else:
        month = None
    req = _req(pk)
    request_review.run(req, request.user, month=month)
    return _out(req)


@api_view(["POST"])
@handle_errors
def options(request, pk):
    center_only(request)
    data = payload(request, optional=("date_from", "date_to", "lesson_id"))
    req = _req(pk)
    lesson = None
    if data.get("lesson_id"):
        lesson = AutoPlanLesson.objects.get(pk=data["lesson_id"], request=req)
    return Response(
        request_review.options(
            req, _day(data, "date_from"), _day(data, "date_to"), lesson
        )
    )


@api_view(["POST"])
@handle_errors
def add(request, pk):
    center_only(request)
    data = payload(request, required=("start_at", "tutor_id"))
    req = _req(pk)
    request_review.add_lesson(req, _instant(data, "start_at"), data["tutor_id"])
    return _out(req, status=201)


@api_view(["POST"])
@handle_errors
def complete(request, pk):
    center_only(request)
    data = payload(request, optional=("accept_missing", "publish_now"))
    accept = data.get("accept_missing", False)
    now_ = data.get("publish_now", False)
    if not isinstance(accept, bool) or not isinstance(now_, bool):
        raise BadPayload("accept_missing, publish_now: booleani")
    req = _req(pk)
    result = request_review.complete(req, request.user, accept_missing=accept, publish_now=now_)
    return _out(req, result=result)


@api_view(["POST"])
@handle_errors
def move(request, pk):
    center_only(request)
    data = payload(request, required=("start_at",), optional=("tutor_id",))
    lesson = AutoPlanLesson.objects.select_related("plan__request").get(pk=pk)
    request_review.move_lesson(
        lesson, _instant(data, "start_at"), data.get("tutor_id") or None
    )
    return _out(_req(lesson.request_id))


@api_view(["POST"])
@handle_errors
def remove(request, pk):
    center_only(request)
    lesson = AutoPlanLesson.objects.select_related("plan__request").get(pk=pk)
    req_id = lesson.request_id
    request_review.remove_lesson(lesson)
    return _out(_req(req_id))


def urlpatterns():
    from django.urls import path

    return [
        path("api/v1/teaching-requests/<uuid:pk>/planning", planning),
        path("api/v1/teaching-requests/<uuid:pk>/planning/rerun", rerun),
        path("api/v1/teaching-requests/<uuid:pk>/planning/options", options),
        path("api/v1/teaching-requests/<uuid:pk>/planning/lessons", add),
        path("api/v1/teaching-requests/<uuid:pk>/planning/complete", complete),
        path("api/v1/planner/request-lessons/<uuid:pk>/move", move),
        path("api/v1/planner/request-lessons/<uuid:pk>/remove", remove),
    ]
