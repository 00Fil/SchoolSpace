"""Development-only synthetic simulations; not the production job/publish API."""

from threading import BoundedSemaphore
from django.conf import settings
from config import features
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from apps.identity.policies import is_center
from apps.scheduling.fixtures import demo_input
from apps.scheduling.contracts import InputError
from apps.scheduling.solver import simulate

RUN_SLOT = BoundedSemaphore(1)


def ensure_center(request):
    if not is_center(request.user):
        raise PermissionDenied()


@api_view(["GET"])
def example(request):
    ensure_center(request)
    if not features.lab_enabled():
        return Response({"code": features.DISABLED_CODE}, status=503)
    return Response(demo_input())


@api_view(["POST"])
def simulation(request):
    ensure_center(request)
    if not features.lab_enabled():
        return Response(
            {
                "code": features.DISABLED_CODE,
                "message": "Laboratorio di simulazione disattivato (FEATURE_PLANNING_LAB)",
            },
            status=503,
        )
    if not RUN_SLOT.acquire(blocking=False):
        return Response(
            {"code": "SIMULATION_BUSY", "message": "Simulazione in corso: attendere"},
            status=429,
            headers={"Retry-After": "3"},
        )
    try:
        try:
            result = simulate(request.data)
        except InputError as error:
            return Response(
                {"code": error.code, "message": error.message, "fields": error.fields},
                status=400,
            )
        return Response(result)
    finally:
        RUN_SLOT.release()
