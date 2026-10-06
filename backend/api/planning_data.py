from datetime import datetime
from django.conf import settings
from config import features
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from apps.identity.policies import is_center
from apps.education.path_services import Conflict
from apps.availability.models import (
    AvailabilityRule,
    AvailabilityDeclaration,
    AvailabilityException,
    AvailabilityConflict,
)
from apps.scheduling.models import (
    TutorSkill,
    TutorOperatingPolicy,
    ResourceTiming,
    ServiceWindow,
    Closure,
    PlanningPolicy,
    PlanningSnapshot,
    ScheduleRun,
    SchedulePlan,
    PlanningAudit,
)
from apps.scheduling.revision import lock_revision
from apps.scheduling.models import LessonSeries
from apps.scheduling.contracts import FULL_VECTOR
from apps.scheduling.policies import fairness_policy
from apps.scheduling.source import compile_source, DataNotReady
from apps.scheduling.runs import submit_run, cancel_run
from .paths import StrictModelSerializer
from apps.reasons import ReasonField, reason_or_default  # noqa: F401


def gate(request):
    if not is_center(request.user):
        raise PermissionDenied()
    # v0.9.4: come calendario e portali (guida v3.1, T1) la pianificazione dipende
    # solo dal flag FEATURE_PLANNING, non da DEBUG: in produzione è attiva per
    # default e si spegne con FEATURE_PLANNING=0.
    return features.planning_enabled()


class OffsetDateTime(serializers.DateTimeField):
    def to_internal_value(self, value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.utcoffset() is None or parsed.second or parsed.microsecond:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise serializers.ValidationError(
                "Istante ISO con offset esplicito e precisione al minuto richiesto"
            )
        return super().to_internal_value(value)


CONFIG_MODELS = {
    "tutor-skills": TutorSkill,
    "tutor-operating-policies": TutorOperatingPolicy,
    "resource-timings": ResourceTiming,
    "service-windows": ServiceWindow,
    "closures": Closure,
    "planning-policies": PlanningPolicy,
    "lesson-series": LessonSeries,  # s8: GAP-D03
    "availability-declarations": AvailabilityDeclaration,
    "availability-exceptions": AvailabilityException,
    "availability-conflicts": AvailabilityConflict,
}


def serializer_for(model):
    class ConfigSerializer(StrictModelSerializer):
        class Meta:
            fields = "__all__"
            read_only_fields = ["id", "created_at", "updated_at", "version"]

        def get_fields(self):
            fields = super().get_fields()
            for name in ("start_at", "end_at"):
                if name in fields:
                    fields[name] = OffsetDateTime(required=not self.partial)
            if model is Closure:
                # La descrizione della chiusura è facoltativa: vuota diventa «Chiusura».
                fields["reason"] = serializers.CharField(
                    max_length=160, required=False, allow_blank=True, allow_null=True
                )
            if model is PlanningPolicy:
                fields["unsupported_constraints"] = serializers.ListField(
                    child=serializers.CharField(max_length=80),
                    max_length=20,
                    required=not self.partial,
                )
            return fields

        def to_internal_value(self, data):
            if isinstance(data, dict) and type(data.get("budget_seconds")) is bool:
                raise serializers.ValidationError(
                    {"budget_seconds": "Numero richiesto, non booleano"}
                )
            return super().to_internal_value(data)

        def validate(self, data):
            def value(name):
                return data.get(name, getattr(self.instance, name, None))

            if model is Closure and (
                "reason" in data or self.instance is None
            ) and not (data.get("reason") or "").strip():
                data["reason"] = "Chiusura"

            if model in (
                AvailabilityDeclaration,
                AvailabilityException,
                AvailabilityConflict,
            ) and bool(value("tutor")) == bool(value("student")):
                raise serializers.ValidationError(
                    "Un solo soggetto: tutor oppure studente"
                )
            for first, last in [
                ("period_start", "period_end"),
                ("valid_from", "valid_until"),
                ("start_time", "end_time"),
                ("start_at", "end_at"),
            ]:
                a, b = value(first), value(last)
                if (
                    a is not None
                    and b is not None
                    and (b < a or (first in ("start_time", "start_at") and b == a))
                ):
                    raise serializers.ValidationError("Intervallo non valido")
            weekday = value("weekday")
            if weekday is not None and weekday > 6:
                raise serializers.ValidationError("Giorno tra 0 e 6")
            if value("mode") == "IN_PERSON" and value("location") not in (
                None,
                "ON_SITE",
            ):
                raise serializers.ValidationError("Presenza solo in sede")
            if model is TutorOperatingPolicy:
                if (
                    not 1 <= value("daily_limit_minutes") <= 10140
                    or not 1 <= value("weekly_limit_minutes") <= 10140
                ):
                    raise serializers.ValidationError(
                        "Limiti in minuti positivi entro il limite del prototipo"
                    )
            if model is PlanningPolicy:
                import math

                budget = value("budget_seconds")
                if not math.isfinite(budget) or not 0.1 <= budget <= 30:
                    raise serializers.ValidationError("Budget tra 0.1 e 30 secondi")
                order = value("objective_order") or ["P0", "P1", "P2"]
                if (
                    not isinstance(order, list)
                    or len(set(order)) != len(order)
                    or not set(order) <= set(FULL_VECTOR)
                    or [t for t in order if t in ("P0", "P1", "P2")]
                    != ["P0", "P1", "P2"]
                ):
                    raise serializers.ValidationError(
                        "Ordine obiettivi: P0, P1, P2 in ordine, poi F/C/R/P/G opzionali"
                    )
                if not 1 <= (value("horizon_weeks") or 1) <= 6:
                    raise serializers.ValidationError("Orizzonte tra 1 e 6 settimane")
                if "F" in order:
                    try:
                        fairness_policy(
                            value("fairness_policy_id") or "fairness-default",
                            value("fairness_policy_version") or 1,
                        )
                    except ValueError:
                        raise serializers.ValidationError(
                            "Policy di equità non registrata"
                        )
            if (
                model is ResourceTiming
                and value("resource").kind == "VIDEO_CHANNEL"
                and value("buffer_minutes") != 0
            ):
                raise serializers.ValidationError(
                    "Nessun buffer su un canale video esclusivo"
                )
            return data

    ConfigSerializer.Meta.model = model
    return ConfigSerializer


class ConfigView(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not gate(request):
            raise PermissionDenied("Configurazione sperimentale disabilitata")

    def get_queryset(self):
        return self.model.objects.order_by("id")

    def get_serializer_class(self):
        return serializer_for(self.model)

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            raise Conflict(
                "CONFIGURATION_CONFLICT",
                "Configurazione già presente o vincolo di integrità non rispettato",
            )

    @transaction.atomic
    def perform_create(self, serializer):
        lock_revision()
        obj = serializer.save()
        PlanningAudit.objects.create(
            actor=self.request.user,
            operation="create:" + self.model._meta.model_name,
            object_id=obj.id,
        )

    def partial_update(self, request, *args, **kwargs):
        body = dict(request.data)
        expected = body.pop("expected_version", None)
        if type(expected) is not int:
            return Response(
                {"code": "INVALID_PAYLOAD", "message": "expected_version obbligatoria"},
                status=400,
            )
        with transaction.atomic():
            lock_revision()
            obj = get_object_or_404(
                self.model.objects.select_for_update(), pk=kwargs["pk"]
            )
            if obj.version != expected:
                raise Conflict(
                    "VERSION_CONFLICT", "Configurazione cambiata: ricaricare"
                )
            serializer = self.get_serializer(obj, data=body, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            PlanningAudit.objects.create(
                actor=request.user,
                operation="update:" + self.model._meta.model_name,
                object_id=obj.id,
            )
            return Response(serializer.data)


def config_view(model):
    return type(model.__name__ + "View", (ConfigView,), {"model": model})


class UnlockItem(serializers.Serializer):
    lesson_id = serializers.UUIDField()
    reason = ReasonField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or "lesson_id" not in data or not set(data) <= {"lesson_id", "reason"}:
            raise serializers.ValidationError("Fornire lesson_id (reason facoltativo)")
        return super().to_internal_value(data)


class RunCommand(serializers.Serializer):
    policy_id = serializers.UUIDField()
    horizon_start = serializers.DateField()
    expected_revision = serializers.IntegerField(min_value=0)
    mode = serializers.ChoiceField(choices=["STRICT", "COVERAGE"])
    # s8 (GAP-D05): optional authorised local replanning.
    unlock = UnlockItem(many=True, required=False)
    propose_scope_expansion = serializers.BooleanField(required=False)
    # v0.9.4: STANDARD (budget della policy) o THOROUGH (accurato, es. notturno).
    effort = serializers.ChoiceField(choices=["STANDARD", "THOROUGH"], required=False)
    REQUIRED = {"policy_id", "horizon_start", "expected_revision", "mode"}

    def to_internal_value(self, data):
        if (
            not isinstance(data, dict)
            or not self.REQUIRED <= set(data) <= set(self.fields)
            or ("propose_scope_expansion" in data and not data.get("unlock"))
        ):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Fornire solo policy_id, horizon_start, expected_revision, mode"
                    ]
                }
            )
        return super().to_internal_value(data)


@api_view(["GET"])
def data_readiness(request):
    if not gate(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    try:
        week = serializers.DateField().run_validation(
            request.query_params.get("horizon_start")
        )
        policy_id = serializers.UUIDField().run_validation(
            request.query_params.get("policy_id")
        )
    except serializers.ValidationError:
        return Response({"code": "INVALID_PAYLOAD"}, status=400)
    policy = get_object_or_404(PlanningPolicy, pk=policy_id)
    with transaction.atomic():
        rev = lock_revision().revision
        try:
            dto, specs = compile_source(
                policy, week, request.query_params.get("mode", "STRICT")
            )
        except DataNotReady as error:
            return Response(
                {
                    "ready": False,
                    "revision": rev,
                    "issues": [
                        {
                            "code": error.code,
                            "message": error.message,
                            **({"request_id": error.ref} if error.ref else {}),
                        }
                    ],
                    "publishable": False,
                }
            )
    return Response(
        {
            "ready": True,
            "revision": rev,
            "unit_count": len(specs),
            "horizon_minutes": dto["horizon_minutes"],
            "issues": [],
            "publishable": False,
            "scope": "DATABASE",
        }
    )


@api_view(["POST"])
def create_run(request):
    if not gate(request):
        return Response({"code": features.DISABLED_CODE}, status=503)
    serializer = RunCommand(data=request.data)
    serializer.is_valid(raise_exception=True)
    body = serializer.validated_data
    get_object_or_404(PlanningPolicy, pk=body["policy_id"])
    try:
        result = submit_run(
            request.user,
            body["policy_id"],
            body["horizon_start"],
            body["expected_revision"],
            body["mode"],
            request.headers.get("Idempotency-Key", ""),
            unlock=body.get("unlock") or None,
            propose_scope_expansion=body.get("propose_scope_expansion", False),
            effort=body.get("effort", "STANDARD"),
        )
    except DataNotReady as error:
        return Response(
            {
                "code": error.code,
                "message": error.message,
                **({"request_id": error.ref} if error.ref else {}),
            },
            status=422,
        )
    return Response(result, status=202)


AUTOPLAN_SCHEMA = "auto-1"


class RunView(viewsets.ReadOnlyModelViewSet):
    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        qs = ScheduleRun.objects.select_related("snapshot", "dispatch").order_by(
            "-created_at"
        )
        if self.action == "list":
            # Le esecuzioni del pianificatore mensile non hanno assegnazioni/validazione
            # del motore settimanale: nell'elenco romperebbero le schermate delle proposte.
            qs = qs.exclude(snapshot__schema_version=AUTOPLAN_SCHEMA)
        return qs

    def get_serializer_class(self):
        class RunSerializer(serializers.ModelSerializer):
            snapshot_id = serializers.UUIDField(read_only=True)
            snapshot_revision = serializers.IntegerField(
                source="snapshot.revision", read_only=True
            )
            stale = serializers.SerializerMethodField()
            publishable = serializers.SerializerMethodField()
            dispatch_status = serializers.CharField(
                source="dispatch.status", read_only=True
            )
            budget_seconds = serializers.FloatField(
                source="snapshot.data.budget_seconds", read_only=True
            )
            horizon_start = serializers.DateField(
                source="snapshot.horizon_start", read_only=True
            )

            class Meta:
                model = ScheduleRun
                fields = [
                    "id",
                    "status",
                    "phase",
                    "created_at",
                    "started_at",
                    "finished_at",
                    "heartbeat_at",
                    "attempts",
                    "cancel_requested",
                    "error_code",
                    "result",
                    "snapshot_id",
                    "snapshot_revision",
                    "stale",
                    "publishable",
                    "dispatch_status",
                    "budget_seconds",
                    "horizon_start",
                ]

            def get_stale(self, obj):
                from apps.scheduling.models import PlanningRevision

                return (
                    PlanningRevision.objects.get(pk=1).revision != obj.snapshot.revision
                )

            def get_publishable(self, obj):
                return False

        return RunSerializer

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        if not gate(request):
            return Response({"code": features.DISABLED_CODE}, status=503)
        obj = self.get_object()
        obj = cancel_run(obj.id, request.user)
        return Response(self.get_serializer(obj).data)


class PlanView(viewsets.ReadOnlyModelViewSet):
    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        qs = SchedulePlan.objects.select_related(
            "run__snapshot", "publication"
        ).order_by("-created_at")
        if self.action == "list":
            qs = qs.exclude(run__snapshot__schema_version=AUTOPLAN_SCHEMA)
        return qs

    def get_serializer_class(self):
        class PlanSerializer(serializers.ModelSerializer):
            state = serializers.SerializerMethodField()
            publishable = serializers.SerializerMethodField()
            experimental_publish_available = serializers.SerializerMethodField()
            snapshot_revision = serializers.IntegerField(
                source="run.snapshot.revision", read_only=True
            )
            version = serializers.SerializerMethodField()
            publication_id = serializers.SerializerMethodField()

            class Meta:
                model = SchedulePlan
                fields = [
                    "id",
                    "run",
                    "state",
                    "assignments",
                    "result_hash",
                    "created_at",
                    "publishable",
                    "experimental_publish_available",
                    "snapshot_revision",
                    "version",
                    "publication_id",
                ]

            def get_version(self, obj):
                return 1

            def get_publication_id(self, obj):
                return str(obj.publication.id) if hasattr(obj, "publication") else None

            def get_experimental_publish_available(self, obj):
                from apps.calendar.services import supported

                return (
                    features.calendar_enabled()
                    and supported()
                    and self.get_state(obj) == "VALIDATED"
                )

            def get_state(self, obj):
                if hasattr(obj, "publication"):
                    return "PUBLISHED"
                from apps.scheduling.models import PlanningRevision

                return (
                    "STALE"
                    if PlanningRevision.objects.get(pk=1).revision
                    != obj.run.snapshot.revision
                    else obj.state
                )

            def get_publishable(self, obj):
                return False

        return PlanSerializer

    @action(detail=True, methods=["post"], url_path="derive-series")
    def derive_series(self, request, pk=None):
        """s8 (GAP-D03): confirm the plan's slots as recurring LessonSeries."""
        if not gate(request):
            return Response({"code": features.DISABLED_CODE}, status=503)
        from apps.scheduling.series import derive_series_from_plan

        body = request.data if isinstance(request.data, dict) else None
        if body is None or not set(body) <= {"stability"}:
            return Response({"code": "INVALID_PAYLOAD"}, status=400)
        plan = self.get_object()
        rows, revision = derive_series_from_plan(
            plan, request.user, body.get("stability", "PREFERRED")
        )
        return Response(
            {"series": [str(r.id) for r in rows], "revision": revision}, status=201
        )
