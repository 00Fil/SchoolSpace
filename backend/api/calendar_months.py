"""Calendario pubblico del mese e rettifiche in bozza (v0.9.11).

- ``GET  /planner/calendar-months/<AAAA-MM>``          stato del mese e rettifiche in bozza
- ``POST /planner/calendar-months/<AAAA-MM>/publish``  pubblica le rettifiche del mese
- ``POST /planner/corrections``                        nuova rettifica (o ``publish_now``)
- ``POST /planner/corrections/<id>/discard``           scarta una rettifica in bozza
- ``POST /planner/corrections/<id>/publish``           pubblica subito una sola rettifica

Solo il gestore del centro: famiglie e tutor vedono sempre il calendario pubblicato.
"""

from django.db import IntegrityError
from django.urls import path
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.scheduling import corrections
from apps.scheduling.models import CalendarCorrection

from ._privacy_common import BadPayload, center_only, handle_errors
from .autoplanner import parse_month
from .calendar_ops import ChangesSer, Uuid
from .planning_data import OffsetDateTime


class CorrectionCmd(serializers.Serializer):
    op = serializers.ChoiceField(["reschedule", "cancel", "modify", "swap"])
    lesson_id = Uuid()
    other_id = Uuid(required=False)
    start_at = OffsetDateTime(required=False)
    end_at = OffsetDateTime(required=False)
    changes = ChangesSer(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=200)
    expected_version = serializers.IntegerField(required=False, min_value=1)
    publish_now = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        extra = set(self.initial_data) - set(self.fields)
        if extra:
            raise serializers.ValidationError({k: "Campo non ammesso" for k in extra})
        op = attrs["op"]
        if op == "reschedule" and not attrs.get("start_at"):
            raise serializers.ValidationError({"start_at": "Nuovo orario richiesto"})
        if attrs.get("end_at") and attrs.get("start_at") and attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError({"end_at": "La fine deve seguire l’inizio"})
        if op == "swap" and not attrs.get("other_id"):
            raise serializers.ValidationError({"other_id": "Seconda lezione richiesta"})
        if op == "modify" and not attrs.get("changes"):
            raise serializers.ValidationError({"changes": "Indica cosa cambiare"})
        return attrs


def _month(value):
    return parse_month(value)


@api_view(["GET"])
@handle_errors
def month_detail(request, month):
    center_only(request)
    return Response(corrections.month_json(_month(month)))


@api_view(["POST"])
@handle_errors
def month_publish(request, month):
    center_only(request)
    first = _month(month)
    try:
        result = corrections.publish_month(request.user, first)
    except IntegrityError:
        return Response({"code": "BOOKING_CONFLICT", "message": "Vincoli del calendario non rispettati"}, status=409)
    return Response({**corrections.month_json(first), "result": result})


@api_view(["POST"])
@handle_errors
def correction_create(request):
    center_only(request)
    if not isinstance(request.data, dict):
        raise BadPayload("Oggetto JSON richiesto")
    parsed = CorrectionCmd(data=request.data)
    parsed.is_valid(raise_exception=True)
    data = dict(parsed.validated_data)
    op, now_ = data.pop("op"), data.pop("publish_now", False)
    row = corrections.propose(request.user, op, data, publish_now=now_)
    return Response(
        {"correction": corrections.correction_json(row), "published": row.state == "APPLIED",
         "month": corrections.month_json(row.month)},
        status=201,
    )


@api_view(["POST"])
@handle_errors
def correction_discard(request, pk):
    center_only(request)
    row = corrections.discard(pk)
    return Response(corrections.month_json(row.month))


@api_view(["POST"])
@handle_errors
def correction_publish(request, pk):
    center_only(request)
    try:
        row = corrections.publish_one(request.user, pk)
    except CalendarCorrection.DoesNotExist:
        return Response({"code": "NOT_FOUND", "message": "Rettifica non trovata"}, status=404)
    return Response({"correction": corrections.correction_json(row), "month": corrections.month_json(row.month)})


def urlpatterns():
    return [
        path("api/v1/planner/calendar-months/<str:month>", month_detail),
        path("api/v1/planner/calendar-months/<str:month>/publish", month_publish),
        path("api/v1/planner/corrections", correction_create),
        path("api/v1/planner/corrections/<uuid:pk>/discard", correction_discard),
        path("api/v1/planner/corrections/<uuid:pk>/publish", correction_publish),
    ]


__all__ = ["urlpatterns", "CalendarCorrection"]
