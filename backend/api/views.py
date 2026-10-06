import json
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.views.decorators.http import require_GET, require_POST
from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from apps.identity.policies import is_center, visible_students, active_roles, granted_roles
from apps.education.models import Tutor, Resource, TeachingRequest
from apps.availability.models import AvailabilityRule
from apps.governance.models import Decision
from .serializers import (
    StudentSerializer,
    TutorSerializer,
    ResourceSerializer,
    RequestSerializer,
    AvailabilitySerializer,
    DecisionSerializer,
)
from apps.reasons import reason_or_default


@require_GET
def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "release": settings.BUILD_VERSION,
            "production_ready": bool(settings.G1_APPROVED and not settings.DEBUG),
        }
    )


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"detail": "CSRF cookie initialized"})


@require_POST
@csrf_protect
def login_view(request):
    # Single-process development throttle only; distributed enforcement and MFA are release blockers.
    if not settings.DEBUG:
        return JsonResponse(
            {
                "code": "DEVELOPMENT_ONLY",
                "message": "Login provvisorio disabilitato fuori sviluppo",
            },
            status=503,
        )
    key = "login:" + request.META.get("REMOTE_ADDR", "unknown")
    count = cache.get(key, 0)
    if count >= 10:
        response = JsonResponse({"code": "RATE_LIMITED"}, status=429)
        response["Retry-After"] = "60"
        return response
    cache.set(key, count + 1, 60)
    try:
        data = json.loads(request.body)
        if (
            not isinstance(data, dict)
            or set(data) != {"username", "password"}
            or not all(isinstance(x, str) for x in data.values())
        ):
            raise ValueError()
    except (ValueError, TypeError):
        return JsonResponse({"code": "INVALID_PAYLOAD"}, status=400)
    user = authenticate(request, username=data["username"], password=data["password"])
    if user is None:
        return JsonResponse(
            {"code": "INVALID_CREDENTIALS", "message": "Credenziali non valide"},
            status=401,
        )
    login(request, user)
    cache.delete(key)
    return JsonResponse({"detail": "Accesso eseguito"})


@require_POST
@csrf_protect
def logout_view(request):
    logout(request)
    return JsonResponse({"detail": "Sessione terminata"})


@api_view(["GET"])
def me(request):
    roles = active_roles(request.user)
    if is_center(request.user):
        roles.add("CENTER")
    tutor = Tutor.objects.filter(account=request.user).first()
    return Response(
        {
            "id": str(request.user.id),
            "name": request.user.get_full_name() or request.user.username,
            "roles": sorted(roles),
            "tutor_id": str(tutor.id) if tutor and "TUTOR" in roles else None,
            # Il gestore può essere anche tutor: la scheda tutor resta nota anche nel contesto centro.
            "own_tutor_id": (
                str(tutor.id)
                if tutor and "TUTOR" in granted_roles(request.user)
                else None
            ),
            "experimental": True,
            "notice_pending": _notice_pending(request.user, roles),
        }
    )


def _notice_pending(user, roles):
    """C04: chi usa i portali deve aver preso visione dell'informativa corrente."""
    if "CENTER" in roles or not roles:
        return False
    from api.my_data import notice_acknowledged

    return not notice_acknowledged(user)


class StudentsView(viewsets.ReadOnlyModelViewSet):
    serializer_class = StudentSerializer

    def get_queryset(self):
        return visible_students(self.request.user).order_by("id")


class TutorsView(viewsets.ReadOnlyModelViewSet):
    serializer_class = TutorSerializer

    def get_queryset(self):
        if is_center(self.request.user):
            return Tutor.objects.all().order_by("id")
        return (
            Tutor.objects.filter(account=self.request.user).order_by("id")
            if "TUTOR" in active_roles(self.request.user)
            else Tutor.objects.none()
        )


class ResourcesView(viewsets.ModelViewSet):
    """Aule e canali video: lettura, creazione e modifica solo per il centro.

    Fino alla v0.9.11 la vista era in sola lettura e «Nuova aula o canale» riceveva
    405 Method Not Allowed. Nessuna eliminazione: le risorse usate restano nello
    storico delle lezioni; si disattivano con ``active=false``.
    """

    serializer_class = ResourceSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        return Resource.objects.all().order_by("id")

    def create(self, request, *args, **kwargs):
        from django.db import IntegrityError, transaction

        if not is_center(request.user):
            raise PermissionDenied()
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {
                    "code": "DATA_CONFLICT",
                    "message": "Esiste già un'aula o un canale con questo nome",
                },
                status=409,
            )

    def partial_update(self, request, *args, **kwargs):
        from django.db import IntegrityError, transaction

        resource = self.get_object()
        expected = request.data.get("expected_version")
        if expected is not None and int(expected) != resource.version:
            return Response(
                {"code": "VERSION_CONFLICT", "message": "Risorsa modificata nel frattempo"},
                status=409,
            )
        body = ResourceSerializer(resource, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                body.save(version=resource.version + 1)
        except IntegrityError:
            return Response(
                {
                    "code": "DATA_CONFLICT",
                    "message": "Esiste già un'aula o un canale con questo nome",
                },
                status=409,
            )
        return Response(ResourceSerializer(resource).data)


class RequestsView(viewsets.ReadOnlyModelViewSet):
    serializer_class = RequestSerializer

    def get_queryset(self):
        from django.db.models import Q

        scope = visible_students(self.request.user)
        query = (
            TeachingRequest.objects.all()
            if is_center(self.request.user)
            else TeachingRequest.objects.filter(
                Q(student__in=scope) | Q(participants__student__in=scope)
            )
        )
        return (
            query.select_related("subject")
            .prefetch_related("participants")
            .distinct()
            .order_by("id")
        )


class AvailabilityView(viewsets.ModelViewSet):
    serializer_class = AvailabilitySerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        from django.db.models import Q

        if is_center(self.request.user):
            return AvailabilityRule.objects.all().order_by("id")
        scope = Q(student__in=visible_students(self.request.user))
        if "TUTOR" in active_roles(self.request.user):
            scope |= Q(tutor__account=self.request.user)
        return AvailabilityRule.objects.filter(scope).order_by("id")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, status="DRAFT")

    def review(self, request, pk, status):
        from django.conf import settings
        from django.db import transaction
        from apps.scheduling.revision import lock_revision
        from apps.scheduling.models import PlanningAudit

        if not is_center(request.user):
            raise PermissionDenied()
        from config import features

        if not features.planning_enabled():
            return Response({"code": features.DISABLED_CODE}, status=503)
        data = request.data
        if (
            not isinstance(data, dict)
            or "expected_version" not in data
            or not set(data) <= {"expected_version", "reason"}
            or type(data["expected_version"]) is not int
            or not isinstance(data.get("reason", ""), (str, type(None)))
        ):
            return Response({"code": "INVALID_PAYLOAD"}, status=400)
        with transaction.atomic():
            lock_revision()
            from django.shortcuts import get_object_or_404

            obj = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if obj.version != data["expected_version"]:
                return Response({"code": "VERSION_CONFLICT"}, status=409)
            obj.status = status
            obj.approved_by = request.user
            obj.save()
            PlanningAudit.objects.create(
                actor=request.user,
                operation="availability:" + status,
                object_id=obj.id,
                reason=reason_or_default(data.get("reason")),
            )
            return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.review(request, pk, "APPROVED")

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        return self.review(request, pk, "REVOKED")


class DecisionsView(viewsets.ReadOnlyModelViewSet):
    serializer_class = DecisionSerializer

    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        return Decision.objects.all()


@api_view(["GET"])
def readiness(request):
    if not is_center(request.user):
        raise PermissionDenied()
    decisions = {d.code: d for d in Decision.objects.all()}
    blockers = []
    for code in [f"D{i:02d}" for i in range(1, 7)]:
        d = decisions.get(code)
        if (
            not d
            or d.status != "APPROVED"
            or not d.outcome.strip()
            or not d.owner.strip()
            or not d.approved_at
        ):
            blockers.append(
                {"code": code, "reason": "Decisione non approvata o evidenze mancanti"}
            )
    from apps.governance.approval import g1_approved

    if not g1_approved():
        blockers.append(
            {
                "code": "G1",
                "reason": "Contratto di dominio, fixture e policy non ancora formalmente approvati",
            }
        )
    return Response(
        {
            "ready": not blockers,
            "gate": "G1",
            "blockers": blockers,
            "release": settings.BUILD_VERSION,
        }
    )
