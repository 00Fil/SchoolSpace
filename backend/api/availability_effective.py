"""GET /api/v1/availability/effective (GAP-C07): finestre effettive e diagnostica.

Scope: centro su chiunque; tutor solo su sé stesso; studente/tutore legale solo
sugli studenti visibili (delega verificata). Fuori scope → 404, senza enumerazione."""

from datetime import datetime
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from apps.identity.policies import is_center, visible_students
from apps.education.models import Tutor, Student
from apps.availability.effective import effective_availability


def _date(value, name):
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        raise serializers.ValidationError({name: "Data AAAA-MM-GG obbligatoria"})


@api_view(["GET"])
def effective(request):
    params = request.query_params
    if bool(params.get("tutor")) == bool(params.get("student")):
        raise serializers.ValidationError(
            {"subject": "Indicare esattamente uno tra tutor e student"}
        )
    first, last = _date(params.get("from"), "from"), _date(params.get("until"), "until")
    if not 0 < (last - first).days <= 62:
        raise serializers.ValidationError(
            {"range": "Date from/until obbligatorie, fine esclusiva, massimo 62 giorni"}
        )
    try:
        subject_id = serializers.UUIDField().run_validation(
            params.get("tutor") or params.get("student")
        )
    except serializers.ValidationError:
        return Response({"code": "NOT_FOUND"}, status=404)
    user = request.user
    if params.get("tutor"):
        kind = "tutor"
        subject = Tutor.objects.filter(pk=subject_id).first()
        allowed = subject is not None and (
            is_center(user)
            or (subject.account_id is not None and subject.account_id == user.id)
        )
    else:
        kind = "student"
        subject = visible_students(user).filter(pk=subject_id).first()
        allowed = subject is not None
        if subject is not None:
            subject = Student.objects.get(pk=subject.pk)
    if not allowed:
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response(effective_availability(kind, subject, first, last))
