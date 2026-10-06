"""API P3: prese visione e controproposte dei tutor sugli orari pubblicati."""

from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.calendar import acknowledgements as service
from apps.calendar.models import TutorAcknowledgement
from apps.identity.policies import is_center
from config import features

from apps.education.path_services import DomainError

from ._privacy_common import handle_errors as _handle, integer, payload, text


def handle_errors(view):
    """Come i comandi del calendario: NOT_FOUND → 404, FORBIDDEN → 403."""
    inner = _handle(view)

    def wrapper(*args, **kwargs):
        try:
            return inner(*args, **kwargs)
        except DomainError as error:
            code = error.detail.get("code") if isinstance(error.detail, dict) else None
            if code == "NOT_FOUND":
                return Response(error.detail, status=404)
            if code == "FORBIDDEN":
                return Response(error.detail, status=403)
            raise

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _gate():
    return features.calendar_enabled()


def _disabled():
    return Response({"code": features.DISABLED_CODE}, status=503)


@api_view(["GET"])
@handle_errors
def collection(request):
    if not _gate():
        return _disabled()
    rows = TutorAcknowledgement.objects.select_related("tutor", "publication")
    if is_center(request.user):
        service.ensure_missing()
    else:
        tutor = service.own_tutor(request.user)
        if tutor is None:
            raise PermissionDenied()
        service.ensure_missing(tutor)
        rows = rows.filter(tutor=tutor)
    state = request.query_params.get("state")
    if state:
        states = [s for s in state.split(",") if s in TutorAcknowledgement.STATES]
        rows = rows.filter(state__in=states)
    rows = rows.order_by("-publication__created_at", "tutor__display_name")[:100]
    return Response({"results": [service.ack_json(a) for a in rows], "next": None})


@api_view(["POST"])
@handle_errors
def acknowledge(request, pk):
    if not _gate():
        return _disabled()
    data = payload(request, required=("expected_version",))
    ack = service.acknowledge(request.user, pk, integer(data, "expected_version"))
    return Response(service.ack_json(ack))


@api_view(["POST"])
@handle_errors
def counter(request, pk):
    if not _gate():
        return _disabled()
    data = payload(request, required=("expected_version", "items"), optional=("note",))
    items = data.get("items")
    if not isinstance(items, list):
        items = None
    ack = service.counter(
        request.user,
        pk,
        integer(data, "expected_version"),
        text(data, "note", 500, required=False),
        items,
    )
    return Response(service.ack_json(ack))


@api_view(["POST"])
@handle_errors
def decide(request, pk):
    if not is_center(request.user):
        raise PermissionDenied()
    if not _gate():
        return _disabled()
    data = payload(request, required=("expected_version", "decision", "reason"))
    ack, created = service.decide(
        request.user,
        pk,
        integer(data, "expected_version"),
        text(data, "decision", 14),
        text(data, "reason", 200),
    )
    return Response({**service.ack_json(ack), "change_requests": created})
