from datetime import datetime, time
from django.conf import settings
from config import features
from django.db import transaction, IntegrityError, connection
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from rest_framework import serializers, generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from apps.identity.policies import is_center
from apps.education.path_services import DomainError
from apps.scheduling.models import SchedulePlan
from apps.scheduling.revision import lock_revision
from apps.calendar.models import LessonOccurrence
from apps.calendar.services import (
    publish_plan,
    change_lesson,
    authorize,
    supported,
    reschedule_options,
)
from domain.intervals import local_to_utc
from .planning_data import OffsetDateTime
from apps.reasons import ReasonField, reason_or_default  # noqa: F401


def center(request):
    if not is_center(request.user):
        raise PermissionDenied()


def development(request):
    center(request)
    return (
        features.calendar_enabled()
)


class ClosedCommand(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or not (
            {n for n, f in self.fields.items() if f.required} <= set(data) <= set(self.fields)
        ):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Fornire tutti e soli i campi previsti dal comando"
                    ]
                }
            )
        if any(
            type(data.get(k)) is not int
            for k in ("expected_version", "expected_revision")
            if k in self.fields
        ):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Versione/revisione devono essere interi, non booleani"
                    ]
                }
            )
        if (
            "confirm_experimental" in self.fields
            and type(data.get("confirm_experimental")) is not bool
        ):
            raise serializers.ValidationError(
                {"confirm_experimental": "Booleano JSON richiesto"}
            )
        return super().to_internal_value(data)


class PublishCommand(ClosedCommand):
    expected_version = serializers.IntegerField(min_value=1)
    expected_revision = serializers.IntegerField(min_value=0)
    accept_unassigned_demand_keys = serializers.ListField(
        child=serializers.CharField(max_length=80), max_length=40
    )
    reason = ReasonField()
    # Compatibilità con i client v0.8: campo facoltativo e senza effetto.
    confirm_experimental = serializers.BooleanField(required=False)


class CancelCommand(ClosedCommand):
    expected_version = serializers.IntegerField(min_value=1)
    reason = ReasonField()


class MoveCommand(CancelCommand):
    start_at = OffsetDateTime()
    end_at = OffsetDateTime(required=False)  # cambio durata (facoltativo)

    def validate(self, attrs):
        if attrs.get("end_at") and attrs["end_at"] <= attrs["start_at"]:
            raise serializers.ValidationError({"end_at": "La fine deve seguire l’inizio"})
        return attrs


class ProposeCommand(MoveCommand):
    end_at = OffsetDateTime()
    confirm_now = serializers.BooleanField(required=False, default=False)


@api_view(["GET"])
def capabilities(request):
    center(request)
    enabled = False
    code = features.DISABLED_CODE
    if development(request):
        try:
            authorize(request.user)
            enabled = True
            code = "ENABLED"
        except DomainError as error:
            code = str(error.detail["code"])
    return Response(
        {
            "enabled": enabled,
            "reason_code": code,
            "database": connection.vendor,
            "production_enabled": enabled,
            "notifications_enabled": False,
            "sqlite_test_override": settings.CALENDAR_ALLOW_SQLITE_TESTS,
        }
    )


@api_view(["POST"])
def publish(request, pk):
    if not development(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    get_object_or_404(SchedulePlan, pk=pk)
    command = PublishCommand(data=request.data)
    command.is_valid(raise_exception=True)
    try:
        result = publish_plan(
            request.user,
            pk,
            command.validated_data,
            request.headers.get("Idempotency-Key", ""),
        )
    except IntegrityError:
        return Response(
            {
                "code": "BOOKING_CONFLICT",
                "message": "Vincolo DB non rispettato: nessun effetto parziale",
            },
            status=409,
        )
    return Response(result)


@api_view(["POST"])
def move(request, pk):
    return command(request, pk, "reschedule", MoveCommand)


@api_view(["GET"])
def move_options(request, pk):
    if not development(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    get_object_or_404(LessonOccurrence, pk=pk)
    day = serializers.DateField().run_validation(request.query_params.get("date"))
    return Response(reschedule_options(request.user, pk, day))


def calendar_ready(request):
    if not development(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    return None


@api_view(["POST"])
def propose_change(request, pk):
    """Drag & drop in Agenda: nuova posizione/durata da confermare (o subito con confirm_now)."""
    from apps.calendar import changes

    blocked = calendar_ready(request)
    if blocked:
        return blocked
    get_object_or_404(LessonOccurrence, pk=pk)
    parsed = ProposeCommand(data=request.data)
    parsed.is_valid(raise_exception=True)
    try:
        result = changes.propose(
            request.user, pk, parsed.validated_data, request.headers.get("Idempotency-Key", "")
        )
    except IntegrityError:
        return Response({"code": "BOOKING_CONFLICT", "message": "Vincolo DB non rispettato: rollback"}, status=409)
    return Response(result)


@api_view(["GET"])
def lesson_changes(request):
    from apps.calendar import changes

    rows = changes.visible(request.user)
    if request.query_params.get("state"):
        rows = rows.filter(state=request.query_params["state"])
    if request.query_params.get("lesson"):
        rows = rows.filter(lesson_id=request.query_params["lesson"])
    return Response([changes.change_json(c, request.user) for c in rows[:300]])


@api_view(["POST"])
def lesson_change_action(request, pk, action):
    from apps.calendar import changes

    if action == "answer":
        accept = request.data.get("accept") if isinstance(request.data, dict) else None
        if not isinstance(accept, bool):
            return Response({"code": "INVALID_PAYLOAD", "message": "accept: booleano"}, status=400)
        note = str(request.data.get("note") or "").strip()[:300]
        try:
            return Response(changes.answer(request.user, pk, accept, note))
        except changes.LessonChange.DoesNotExist:
            return Response({"code": "NOT_FOUND"}, status=404)
    blocked = calendar_ready(request)
    if blocked:
        return blocked
    get_object_or_404(changes.LessonChange, pk=pk)
    try:
        if action == "confirm":
            return Response(changes.confirm_now(request.user, pk))
        if action == "withdraw":
            return Response(changes.withdraw(request.user, pk))
    except IntegrityError:
        return Response({"code": "BOOKING_CONFLICT", "message": "Vincolo DB non rispettato: rollback"}, status=409)
    return Response({"code": "NOT_FOUND"}, status=404)


@api_view(["POST"])
def cancel(request, pk):
    return command(request, pk, "cancel", CancelCommand)


def command(request, pk, operation, serializer):
    if not development(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    get_object_or_404(LessonOccurrence, pk=pk)
    parsed = serializer(data=request.data)
    parsed.is_valid(raise_exception=True)
    try:
        result = change_lesson(
            request.user,
            pk,
            operation,
            parsed.validated_data,
            request.headers.get("Idempotency-Key", ""),
        )
    except IntegrityError:
        return Response(
            {
                "code": "BOOKING_CONFLICT",
                "message": "Vincolo DB non rispettato: rollback",
            },
            status=409,
        )
    return Response(result)


class LessonSerializer(serializers.ModelSerializer):
    tutor_name = serializers.CharField(source="tutor.display_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    participants = serializers.SerializerMethodField()
    demand_key = serializers.CharField(source="demand.demand_key", read_only=True)
    experimental = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()

    class Meta:
        model = LessonOccurrence
        fields = [
            "id",
            "version",
            "state",
            "demand_key",
            "start_at",
            "end_at",
            "tutor",
            "tutor_name",
            "subject",
            "subject_name",
            "mode",
            "location",
            "space",
            "video",
            "participants",
            "experimental",
            # s2-calendario: serie/recupero e avvisi delle pratiche aperte.
            "series",
            "recurrence_key",
            "recovery",
            "warnings",
            "time_change",
        ]

    time_change = serializers.SerializerMethodField()

    def get_time_change(self, obj):
        """Modifica di orario/durata in attesa di conferma (drag & drop in Agenda)."""
        rows = [c for c in obj.time_changes.all() if c.state == "PENDING"]
        if not rows:
            return None
        c = rows[0]
        return {
            "id": str(c.id),
            "start_at": c.start_at.isoformat(),
            "end_at": c.end_at.isoformat(),
            "answers": [
                {
                    "party": a.party,
                    "who": a.tutor.display_name if a.tutor_id else a.student.display_name,
                    "status": a.status,
                }
                for a in c.answers.all()
            ],
        }

    def get_warnings(self, obj):
        return {
            "open_conflicts": getattr(obj, "open_conflicts", 0),
            "pending_change_requests": getattr(obj, "pending_changes", 0),
        }

    def get_participants(self, obj):
        return [
            {"student_id": str(p.student_id), "name": p.student.display_name}
            for p in obj.participants.all()
        ]

    def get_experimental(self, obj):
        return True


class CalendarPagination(PageNumberPagination):
    def get_next_link(self):
        from urllib.parse import urlsplit

        link = super().get_next_link()
        if not link:
            return None
        url = urlsplit(link)
        return url.path + "?" + url.query

    def get_previous_link(self):
        from urllib.parse import urlsplit

        link = super().get_previous_link()
        if not link:
            return None
        url = urlsplit(link)
        return url.path + "?" + url.query

    page_size = 100

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["revision"] = self.request.calendar_revision
        response.data["experimental"] = True
        return response


class CalendarView(generics.ListAPIView):
    serializer_class = LessonSerializer
    pagination_class = CalendarPagination

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        if not development(request):
            return Response({"code": features.DISABLED_CODE}, status=503)
        request.calendar_revision = lock_revision().revision
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            first = serializers.DateField().run_validation(
                self.request.query_params.get("from")
            )
            last = serializers.DateField().run_validation(
                self.request.query_params.get("until")
            )
            if not 0 < (last - first).days <= 62:
                raise ValueError()
        except (serializers.ValidationError, ValueError):
            raise serializers.ValidationError(
                {
                    "range": "Date from/until obbligatorie, fine esclusiva, massimo 62 giorni"
                }
            )
        start = local_to_utc(datetime.combine(first, time.min))
        end = local_to_utc(datetime.combine(last, time.min))
        return (
            LessonOccurrence.objects.filter(start_at__lt=end, end_at__gt=start)
            .annotate(
                open_conflicts=Count(
                    "conflict_cases",
                    filter=Q(conflict_cases__state="OPEN"),
                    distinct=True,
                ),
                pending_changes=Count(
                    "change_requests",
                    filter=Q(change_requests__state="SUBMITTED"),
                    distinct=True,
                ),
            )
            .select_related("tutor", "subject", "demand")
            .prefetch_related("participants__student", "time_changes__answers__tutor", "time_changes__answers__student")
            .order_by("start_at", "id")
        )


def lesson_scope(user):
    """Lezioni visibili a chi non è del centro: proprie come tutor o di studenti visibili."""
    from apps.identity.policies import active_roles, visible_students

    roles = active_roles(user)
    scope = Q(pk__in=[])
    if is_center(user):
        return Q(), set(), True
    if "TUTOR" in roles:
        scope |= Q(tutor__account=user)
    students = set(visible_students(user).values_list("id", flat=True))
    if students:
        scope |= Q(participants__student_id__in=students)
    return scope, students, False


@api_view(["GET"])
def my_lessons(request):
    """Settimana personale per tutor, tutori legali e studenti (flag FEATURE_CALENDAR)."""
    if not (
        features.calendar_enabled()
):
        return Response({"code": features.DISABLED_CODE}, status=503)
    try:
        first = serializers.DateField().run_validation(request.query_params.get("from"))
        last = serializers.DateField().run_validation(request.query_params.get("until"))
        if not 0 < (last - first).days <= 62:
            raise ValueError()
    except (serializers.ValidationError, ValueError):
        raise serializers.ValidationError(
            {"range": "Date from/until obbligatorie, fine esclusiva, massimo 62 giorni"}
        )
    scope, students, everyone = lesson_scope(request.user)
    start = local_to_utc(datetime.combine(first, time.min))
    end = local_to_utc(datetime.combine(last, time.min))
    rows = (
        LessonOccurrence.objects.filter(scope)
        .filter(
            start_at__lt=end,
            end_at__gt=start,
            state__in=("PUBLISHED", "CANCELLED"),
        )
        .select_related("tutor", "subject", "space", "video")
        .prefetch_related("participants__student", "time_changes__answers__tutor", "time_changes__answers__student")
        .distinct()
        .order_by("start_at", "id")[:300]
    )
    tutor_ids = set()
    if not everyone:
        from apps.education.models import Tutor

        tutor_ids = set(
            Tutor.objects.filter(account=request.user).values_list("id", flat=True)
        )
    out = []
    for lesson in rows:
        mine = everyone or lesson.tutor_id in tutor_ids
        people = list(lesson.participants.all())
        shown = [
            {"student_id": str(p.student_id), "name": p.student.display_name}
            for p in people
            if mine or p.student_id in students
        ]
        out.append(
            {
                "id": str(lesson.id),
                "state": lesson.state,
                "start_at": lesson.start_at.isoformat(),
                "end_at": lesson.end_at.isoformat(),
                "subject_name": lesson.subject.name,
                "tutor_name": lesson.tutor.display_name,
                "mode": lesson.mode,
                "location": lesson.location,
                "space_name": lesson.space.name if lesson.space_id else None,
                "as_tutor": bool(mine and not everyone),
                "participants": shown,
                "other_participants": len(people) - len(shown),
            }
        )
    return Response({"results": out, "experimental": True})
