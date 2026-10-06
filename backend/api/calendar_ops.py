"""API s2-calendario: comandi operativi, serie, recuperi, presenze, pratiche, piano.

Stessi presupposti di api/calendar.py: flag sperimentali, PostgreSQL (override solo
nei test), Idempotency-Key obbligatoria, corpo chiuso, risposta dei soli dati utili.
"""

from django.conf import settings
from config import features
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from apps.identity.policies import is_center
from apps.education.path_services import DomainError
from apps.scheduling.models import SchedulePlan
from apps.calendar import operations, series as series_ops, conflicts, lifecycle
from apps.calendar.models import (
    LessonOccurrence,
    LessonSeries,
    RecoveryObligation,
    ConflictCase,
    HorizonProposal,
)
from apps.calendar.services import supported
from apps.calendar.scope import is_lesson_tutor
from .planning_data import OffsetDateTime
from apps.reasons import ReasonField, reason_or_default  # noqa: F401

MODES = ["IN_PERSON", "ONLINE"]
LOCATIONS = ["ON_SITE", "REMOTE"]


class Strict(serializers.Serializer):
    """Corpo chiuso: campi sconosciuti rifiutati, interi e booleani JSON esatti."""

    INTS = ("expected_version", "expected_revision", "first_version", "second_version")
    BOOLS = ("confirm_correction", "apply")

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["Campi non previsti dal comando"]}
            )
        for name in self.INTS:
            if name in self.fields and name in data and type(data[name]) is not int:
                raise serializers.ValidationError({name: "Intero JSON richiesto"})
        for name in self.BOOLS:
            if name in self.fields and name in data and type(data[name]) is not bool:
                raise serializers.ValidationError({name: "Booleano JSON richiesto"})
        return super().to_internal_value(data)


def Uuid(**kw):
    return serializers.UUIDField(**kw)


class Versioned(Strict):
    expected_version = serializers.IntegerField(min_value=1)
    reason = ReasonField()


class MoveCmd(Versioned):
    start_at = OffsetDateTime()


class ChangesSer(Strict):
    start_at = OffsetDateTime(required=False)
    tutor_id = Uuid(required=False)
    mode = serializers.ChoiceField(MODES, required=False)
    location = serializers.ChoiceField(LOCATIONS, required=False)
    space_id = Uuid(required=False, allow_null=True)
    video_id = Uuid(required=False, allow_null=True)


class ModifyCmd(Versioned):
    changes = ChangesSer()


class SwapCmd(Strict):
    first_id = Uuid()
    first_version = serializers.IntegerField(min_value=1)
    second_id = Uuid()
    second_version = serializers.IntegerField(min_value=1)
    reason = ReasonField()


CAUSES = [
    "CENTER_CANCELLATION",
    "FAMILY_REQUEST",
    "TUTOR_ABSENCE",
    "STUDENT_ABSENCE",
    "CLOSURE",
]


class RecoveryCmd(Versioned):
    cause = serializers.ChoiceField(CAUSES)
    participant_ids = serializers.ListField(child=Uuid(), min_length=1, max_length=20)
    minutes = serializers.IntegerField(required=False, min_value=15, max_value=240)
    grant_late_notice = serializers.BooleanField(required=False, default=False)


class MakeupCmd(Versioned):
    start_at = OffsetDateTime()
    tutor_id = Uuid()
    mode = serializers.ChoiceField(MODES)
    location = serializers.ChoiceField(LOCATIONS)
    space_id = Uuid(allow_null=True)
    video_id = Uuid(allow_null=True)


class EntrySer(Strict):
    student_id = Uuid()
    status = serializers.ChoiceField(["PRESENT", "ABSENT", "JUSTIFIED", "NOT_RECORDED"])
    minutes = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class AttendanceCmd(Strict):
    expected_version = serializers.IntegerField(min_value=1)
    entries = EntrySer(many=True, allow_empty=False, max_length=40)
    reason = ReasonField()


class CompleteCmd(Strict):
    expected_version = serializers.IntegerField(min_value=1)
    reason = ReasonField()


class CorrectionCmd(Versioned):
    entries = EntrySer(many=True, allow_empty=False, max_length=40)
    confirm_correction = serializers.BooleanField()


class SeriesCreateCmd(Strict):
    request_id = Uuid()
    start_date = serializers.DateField()
    start_time = serializers.TimeField(input_formats=["%H:%M"])
    rrule = serializers.CharField(max_length=200)
    exdates = serializers.ListField(
        child=serializers.DateField(), required=False, max_length=60
    )
    tutor_id = Uuid()
    mode = serializers.ChoiceField(MODES)
    location = serializers.ChoiceField(LOCATIONS)
    space_id = Uuid(allow_null=True)
    video_id = Uuid(allow_null=True)
    reason = ReasonField()
    origin_lesson_id = Uuid(required=False, allow_null=True)


class ExdateCmd(Versioned):
    date = serializers.DateField()


class OverrideCmd(Versioned):
    date = serializers.DateField()
    local_start = serializers.CharField(max_length=16)

    def validate_local_start(self, value):
        return series_ops.parse_local(value)


class SplitChanges(Strict):
    start_time = serializers.TimeField(input_formats=["%H:%M"], required=False)
    rrule = serializers.CharField(max_length=200, required=False)
    tutor_id = Uuid(required=False)
    mode = serializers.ChoiceField(MODES, required=False)
    location = serializers.ChoiceField(LOCATIONS, required=False)
    space_id = Uuid(required=False, allow_null=True)
    video_id = Uuid(required=False, allow_null=True)


class SplitCmd(Versioned):
    from_date = serializers.DateField()
    changes = SplitChanges()


class ResolveCmd(Versioned):
    resolution = serializers.ChoiceField(["CANCEL", "RESCHEDULE", "CONFIRM"])
    start_at = OffsetDateTime(required=False)
    recovery_cause = serializers.ChoiceField(CAUSES, required=False)
    grant_late_notice = serializers.BooleanField(required=False, default=False)


class ChangeRequestCmd(Strict):
    lesson_id = Uuid()
    kind = serializers.ChoiceField(["CANCEL", "RESCHEDULE", "ABSENCE", "OTHER"])
    reason = ReasonField()
    proposal = serializers.DictField(required=False)
    student_id = Uuid(required=False, allow_null=True)


class DecideCmd(Versioned):
    decision = serializers.ChoiceField(["ACCEPT", "REJECT"])
    apply = serializers.BooleanField(required=False)


class TutorConfirmCmd(Versioned):
    decision = serializers.ChoiceField(["CONFIRM", "REJECT"])


class ValidatePlanCmd(Strict):
    expected_revision = serializers.IntegerField(min_value=0)


class RejectPlanCmd(Versioned):
    pass


class EmptyCmd(Strict):
    pass


class HorizonCmd(Strict):
    weeks = serializers.IntegerField(required=False, min_value=1, max_value=12)
    policy_id = Uuid(required=False)


def flags():
    return (
        features.calendar_enabled()
)


def plain(value):
    """UUID→str per corpo idempotente stabile e confronti coerenti."""
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    if hasattr(value, "hex") and type(value).__name__ == "UUID":
        return str(value)
    return value


def execute(request, fn, serializer, *args, center_only=True):
    if center_only and not is_center(request.user):
        raise PermissionDenied()
    if not flags():
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    parsed = serializer(data=request.data)
    parsed.is_valid(raise_exception=True)
    try:
        result = fn(
            request.user,
            *args,
            plain(dict(parsed.validated_data)),
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
    except DomainError as error:
        if error.detail.get("code") == "NOT_FOUND":
            return Response(error.detail, status=404)
        if error.detail.get("code") == "FORBIDDEN":
            return Response(error.detail, status=403)
        raise
    return Response(result)


# --- comandi sulle lezioni ---------------------------------------------------------


@api_view(["POST"])
def move(request, pk):
    return execute(request, operations.move_lesson, MoveCmd, pk)


@api_view(["POST"])
def modify(request, pk):
    return execute(request, operations.modify_lesson, ModifyCmd, pk)


@api_view(["POST"])
def swap(request):
    return execute(request, operations.swap_lessons, SwapCmd)


@api_view(["POST"])
def recovery(request, pk):
    return execute(request, operations.create_recovery, RecoveryCmd, pk)


@api_view(["POST"])
def makeup(request, pk):
    return execute(request, operations.schedule_makeup, MakeupCmd, pk)


@api_view(["POST"])
def waive(request, pk):
    return execute(request, operations.waive_recovery, Versioned, pk)


@api_view(["GET", "POST"])
def attendance(request, pk):
    if request.method == "POST":
        return execute(
            request, operations.record_attendance, AttendanceCmd, pk, center_only=False
        )
    if not flags():
        return Response({"code": features.DISABLED_CODE}, status=503)
    lesson = get_object_or_404(LessonOccurrence.objects.select_related("tutor"), pk=pk)
    if not (is_center(request.user) or is_lesson_tutor(request.user, lesson)):
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response({**operations.attendance_summary(lesson), "experimental": True})


@api_view(["POST"])
def complete(request, pk):
    return execute(
        request, operations.complete_lesson, CompleteCmd, pk, center_only=False
    )


@api_view(["POST"])
def admin_correction(request, pk):
    return execute(request, operations.admin_correction, CorrectionCmd, pk)


@api_view(["GET"])
def recovery_list(request):
    if not is_center(request.user):
        raise PermissionDenied()
    rows = RecoveryObligation.objects.select_related("demand").order_by("-created_at")
    if request.query_params.get("state"):
        rows = rows.filter(state=request.query_params["state"])
    return Response(
        {
            "results": [operations.obligation_summary(r) for r in rows[:200]],
            "experimental": True,
        }
    )


# --- serie -------------------------------------------------------------------------


@api_view(["GET", "POST"])
def series_collection(request):
    if request.method == "POST":
        return execute(request, series_ops.create_series, SeriesCreateCmd)
    if not is_center(request.user):
        raise PermissionDenied()
    rows = LessonSeries.objects.order_by("request_id", "start_date", "id")
    if request.query_params.get("request"):
        rows = rows.filter(
            request_id=serializers.UUIDField().run_validation(
                request.query_params["request"]
            )
        )
    return Response(
        {
            "results": [series_ops.series_summary(s) for s in rows[:200]],
            "experimental": True,
        }
    )


@api_view(["GET"])
def series_detail(request, pk):
    if not is_center(request.user):
        raise PermissionDenied()
    row = get_object_or_404(LessonSeries, pk=pk)
    first = request.query_params.get("from")
    last = request.query_params.get("until")
    first = serializers.DateField().run_validation(first) if first else row.start_date
    last = serializers.DateField().run_validation(last) if last else None
    if last is not None and not 0 < (last - first).days <= 400:
        raise serializers.ValidationError({"range": "Intervallo da 1 a 400 giorni"})
    return Response(
        {
            **series_ops.series_summary(row),
            "occurrences": series_ops.occurrences(row, first, last),
            "experimental": True,
        }
    )


@api_view(["POST"])
def series_exdate(request, pk):
    return execute(request, series_ops.add_exdate, ExdateCmd, pk)


@api_view(["POST"])
def series_override(request, pk):
    return execute(request, series_ops.override_occurrence, OverrideCmd, pk)


@api_view(["POST"])
def series_split(request, pk):
    return execute(request, series_ops.split_series, SplitCmd, pk)


# --- pratiche e richieste ----------------------------------------------------------


@api_view(["GET"])
def conflict_list(request):
    if not is_center(request.user):
        raise PermissionDenied()
    rows = ConflictCase.objects.order_by("-created_at")
    if request.query_params.get("state"):
        rows = rows.filter(state=request.query_params["state"])
    return Response(
        {
            "results": [conflicts.case_summary(c) for c in rows[:200]],
            "experimental": True,
        }
    )


@api_view(["POST"])
def conflict_detect(request):
    return execute(request, conflicts.run_detection, EmptyCmd)


@api_view(["POST"])
def conflict_resolve(request, pk):
    return execute(request, conflicts.resolve_conflict, ResolveCmd, pk)


@api_view(["GET", "POST"])
def change_requests(request):
    if request.method == "POST":
        return execute(
            request,
            conflicts.submit_change_request,
            ChangeRequestCmd,
            center_only=False,
        )
    if not flags():
        return Response({"code": features.DISABLED_CODE}, status=503)
    rows = conflicts.visible_change_requests(request.user)
    if request.query_params.get("state"):
        rows = rows.filter(state=request.query_params["state"])
    return Response(
        {
            "results": [conflicts.request_summary(r) for r in rows[:200]],
            "experimental": True,
        }
    )


@api_view(["POST"])
def change_decide(request, pk):
    return execute(request, conflicts.decide_change_request, DecideCmd, pk)


@api_view(["POST"])
def change_tutor_confirm(request, pk):
    """Seconda conferma, del tutor della lezione, sulle richieste delle famiglie (P4)."""
    return execute(
        request, conflicts.tutor_confirm_change_request, TutorConfirmCmd, pk, center_only=False
    )


@api_view(["POST"])
def change_withdraw(request, pk):
    return execute(
        request, conflicts.withdraw_change_request, Versioned, pk, center_only=False
    )


# --- ciclo di vita del piano e orizzonte -------------------------------------------


@api_view(["POST"])
def plan_validate(request, pk):
    return execute(request, lifecycle.validate_plan, ValidatePlanCmd, pk)


@api_view(["POST"])
def plan_reject(request, pk):
    return execute(request, lifecycle.reject_plan, RejectPlanCmd, pk)


@api_view(["GET"])
def plan_lifecycle(request, pk):
    if not is_center(request.user):
        raise PermissionDenied()
    plan = get_object_or_404(
        SchedulePlan.objects.select_related("run__snapshot"), pk=pk
    )
    return Response(lifecycle.plan_lifecycle(plan))


@api_view(["GET", "POST"])
def horizon(request):
    if request.method == "POST":
        return execute(request, lifecycle.horizon_command, HorizonCmd)
    if not is_center(request.user):
        raise PermissionDenied()
    rows = HorizonProposal.objects.order_by("-created_at", "week_start")[:100]
    return Response(
        {"results": [lifecycle.proposal_summary(r) for r in rows], "experimental": True}
    )


@api_view(["GET"])
def substitutes(request, pk):
    """P4: tutor che possono sostituire quello assente (solo centro, nessuna scrittura)."""
    if not flags():
        return Response({"code": features.DISABLED_CODE}, status=503)
    if not supported():
        return Response({"code": "POSTGRES_REQUIRED"}, status=503)
    if not is_center(request.user):
        raise PermissionDenied()
    from apps.calendar.substitutes import substitutes as find

    lesson = get_object_or_404(LessonOccurrence, pk=pk)
    return Response({**find(lesson), "experimental": True})


class GuardianConfirmCmd(Versioned):
    decision = serializers.ChoiceField(["CONFIRM", "REJECT"])


@api_view(["POST"])
def change_guardian_confirm(request, pk):
    """P5: conferma dei genitori sulle modifiche proposte dal tutor e accolte dal centro."""
    return execute(
        request, conflicts.guardian_confirm_change_request, GuardianConfirmCmd, pk, center_only=False
    )
