from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from rest_framework import serializers
from apps.education.models import Student, Tutor, Resource, TeachingRequest
from apps.availability.models import AvailabilityRule
from apps.governance.models import Decision
from apps.identity.policies import (
    is_center,
    can_manage_student_availability,
    active_roles,
)


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ["id", "display_name", "level", "active", "version"]


class TutorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tutor
        fields = ["id", "display_name", "version"]


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ["id", "name", "kind", "student_capacity", "active", "version"]
        read_only_fields = ["version"]

    def validate(self, attrs):
        # Stesso vincolo del database (resource_capacity_by_kind), con errore leggibile.
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if "kind" in attrs or "student_capacity" in attrs:
            capacity = attrs.get(
                "student_capacity", getattr(self.instance, "student_capacity", None)
            )
            if kind == "SPACE":
                if not capacity or capacity < 1:
                    raise serializers.ValidationError(
                        {"student_capacity": "Un'aula richiede una capienza di almeno 1 studente"}
                    )
            elif kind == "VIDEO_CHANNEL":
                attrs["student_capacity"] = None
        if "name" in attrs:
            attrs["name"] = attrs["name"].strip()
            if not attrs["name"]:
                raise serializers.ValidationError({"name": "Nome obbligatorio"})
        return attrs


class RequestSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    participant_ids = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    preferred_tutors = serializers.SerializerMethodField()
    derived = serializers.SerializerMethodField()
    own = serializers.SerializerMethodField()
    participant_names = serializers.SerializerMethodField()

    class Meta:
        model = TeachingRequest
        fields = [
            "id",
            "student",
            "target_type",
            "participant_ids",
            "subject_name",
            "mode",
            "duration_minutes",
            "sessions_per_week",
            "period_start",
            "period_end",
            "version",
            # v0.9.4: approvazione e scelta del tutor
            "subject",
            "student_name",
            "priority",
            "mandatory",
            "status",
            "origin",
            "tutor_choice",
            "preferred_tutors",
            "notes",
            "review_note",
            "reviewed_at",
            "created_at",
            "derived",
            "own",
            # v0.9.6: tipo di richiesta (singola o ricorrente)
            "kind",
            "fixed_time",
            # v0.9.9: verifica delle lezioni e lezioni di gruppo
            "planning_state",
            "completed_at",
            "group_label",
            "participant_names",
        ]

    def get_student_name(self, obj):
        if obj.group_label:
            return obj.group_label
        return obj.student.display_name if obj.student_id else ""

    def get_preferred_tutors(self, obj):
        return [
            {"id": str(t.id), "display_name": t.display_name}
            for t in obj.preferred_tutors.all()
        ]

    def get_derived(self, obj):
        return bool(obj.curriculum_block_id)

    def get_own(self, obj):
        return obj.requested_by_id == self.context["request"].user.id

    def get_target_type(self, obj):
        return "GROUP" if obj.group_id or obj.group_label else "STUDENT"

    def get_participant_names(self, obj):
        ids = set(self.get_participant_ids(obj))
        if not obj.group_label:
            return []
        return sorted(
            p.student.display_name for p in obj.participants.all() if str(p.student_id) in ids
        )

    def get_participant_ids(self, obj):
        from apps.identity.policies import visible_students

        scope = set(
            visible_students(self.context["request"].user).values_list("id", flat=True)
        )
        ids = (
            set(obj.participants.values_list("student_id", flat=True))
            if obj.curriculum_block_id or obj.group_label
            else ({obj.student_id} if obj.student_id else set())
        )
        return [str(i) for i in sorted(ids & scope, key=str)]


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Decision
        fields = [
            "id",
            "code",
            "title",
            "proposed_default",
            "status",
            "owner",
            "outcome",
            "approved_at",
            "version",
        ]


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityRule
        fields = [
            "id",
            "tutor",
            "student",
            "weekday",
            "start_time",
            "end_time",
            "period_start",
            "period_end",
            "timezone",
            "mode",
            "location",
            "status",
            "version",
        ]
        read_only_fields = ["id", "status", "version"]

    def to_internal_value(self, data):
        extras = set(data) - set(self.fields)
        immutable = set(data) & {"id", "status", "version"}
        if extras or immutable:
            raise serializers.ValidationError(
                {
                    "fields": "Campi sconosciuti o non scrivibili: "
                    + ", ".join(sorted(extras | immutable))
                }
            )
        return super().to_internal_value(data)

    def get_fields(self):
        fields = super().get_fields()
        user = self.context["request"].user
        if not is_center(user):
            from apps.identity.policies import visible_students

            fields["student"].queryset = visible_students(user)
            fields["tutor"].queryset = (
                Tutor.objects.filter(account=user)
                if "TUTOR" in active_roles(user)
                else Tutor.objects.none()
            )
        return fields

    def validate(self, data):
        if bool(data.get("tutor")) == bool(data.get("student")):
            raise serializers.ValidationError(
                "Indicare un solo soggetto: tutor oppure studente"
            )
        user = self.context["request"].user
        if data.get("student") and not can_manage_student_availability(
            user, data["student"]
        ):
            raise serializers.ValidationError("Modifica disponibilità non autorizzata")
        if data["end_time"] <= data["start_time"]:
            raise serializers.ValidationError(
                {
                    "end_time": "Deve essere successiva all'inizio; suddividere le finestre oltre mezzanotte"
                }
            )
        if data["period_end"] < data["period_start"]:
            raise serializers.ValidationError({"period_end": "Periodo non valido"})
        if data["weekday"] > 6:
            raise serializers.ValidationError({"weekday": "Usare un valore tra 0 e 6"})
        if data["mode"] == "IN_PERSON" and data["location"] != "ON_SITE":
            raise serializers.ValidationError(
                {"location": "La presenza richiede la sede"}
            )
        try:
            ZoneInfo(data.get("timezone", "Europe/Rome"))
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError({"timezone": "Fuso IANA non valido"})
        return data
