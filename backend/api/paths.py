from datetime import timedelta
from django.db import transaction, IntegrityError
from apps.scheduling.revision import lock_revision
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from apps.identity.policies import is_center, visible_students
from apps.education.models import (
    LearningPath,
    PathEnrollment,
    TeachingGroup,
    GroupMembership,
    CurriculumBlock,
    Subject,
    TeachingRequest,
)
from apps.education.path_services import (
    DomainError,
    Conflict,
    assert_period,
    participant_ids,
    validate_blocks,
    derive_requests,
    touch_path,
)
from apps.governance.models import PathAuditEvent


class StrictModelSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {"non_field_errors": ["Oggetto JSON richiesto"]}
            )
        extras = set(data) - set(self.fields)
        readonly = {name for name, f in self.fields.items() if f.read_only} & set(data)
        if extras or readonly:
            raise serializers.ValidationError(
                {
                    "fields": "Campi sconosciuti o non scrivibili: "
                    + ", ".join(sorted(extras | readonly))
                }
            )
        return super().to_internal_value(data)


class SubjectSerializer(StrictModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "description", "active", "version"]
        read_only_fields = ["id", "version"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Il nome è obbligatorio")
        clash = Subject.objects.filter(name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Esiste già una materia con questo nome")
        return value


class PathSerializer(StrictModelSerializer):
    class Meta:
        model = LearningPath
        fields = [
            "id",
            "title",
            "kind",
            "academic_year",
            "level",
            "period_start",
            "period_end",
            "required_subjects",
            "curriculum_version",
            "version",
        ]
        read_only_fields = ["id", "curriculum_version", "version"]

    def validate(self, data):
        if data["period_end"] < data["period_start"]:
            raise serializers.ValidationError("Periodo non valido")
        if not data.get("required_subjects"):
            raise serializers.ValidationError(
                "Indicare le materie del programma; nessun programma scolastico viene inventato"
            )
        return data


class EnrollmentSerializer(StrictModelSerializer):
    student_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = PathEnrollment
        fields = [
            "id",
            "path",
            "student",
            "student_name",
            "period_start",
            "period_end",
            "active",
            "version",
        ]
        read_only_fields = ["id", "student_name", "version"]


class GroupSerializer(StrictModelSerializer):
    class Meta:
        model = TeachingGroup
        fields = [
            "id",
            "path",
            "name",
            "subject",
            "online_capacity",
            "approved",
            "version",
        ]
        read_only_fields = ["id", "version"]


class MembershipSerializer(StrictModelSerializer):
    class Meta:
        model = GroupMembership
        fields = ["id", "group", "student", "period_start", "period_end", "version"]
        read_only_fields = ["id", "version"]


class BlockSerializer(StrictModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = CurriculumBlock
        fields = [
            "id",
            "path",
            "subject",
            "subject_name",
            "objective",
            "student",
            "group",
            "period_start",
            "period_end",
            "minutes_per_week",
            "duration_minutes",
            "sessions_per_week",
            "mode",
            "priority",
            "mandatory",
            "version",
        ]
        read_only_fields = ["id", "subject_name", "version"]

    def validate(self, data):
        if bool(data.get("student")) == bool(data.get("group")):
            raise serializers.ValidationError(
                "Scegliere studente oppure gruppo, non entrambi"
            )
        if (
            data["sessions_per_week"] < 1
            or data["minutes_per_week"]
            != data["duration_minutes"] * data["sessions_per_week"]
        ):
            raise serializers.ValidationError(
                "Minuti settimanali = durata × sessioni richieste"
            )
        return data


class CenterCreateView(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        if not is_center(request.user):
            raise PermissionDenied()
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {
                    "code": "DATA_CONFLICT",
                    "message": "Dati già presenti o modificati da un altro comando: ricaricare",
                },
                status=409,
            )

    def assert_mutable(self, path):
        if TeachingRequest.objects.filter(curriculum_block__path=path).exists():
            raise Conflict(
                "CURRICULUM_FROZEN",
                "Curriculum già derivato: revisione esplicita necessaria; modifiche dirette disabilitate",
            )


class SubjectsView(CenterCreateView):
    """Materie (v0.9.6): pagina dedicata del centro con modifica, archiviazione
    ed eliminazione delle sole materie mai usate."""

    serializer_class = SubjectSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if is_center(self.request.user):
            return Subject.objects.all().order_by("id")
        return (
            Subject.objects.filter(
                learning_paths__enrollments__student__in=visible_students(
                    self.request.user
                ),
                learning_paths__enrollments__active=True,
            )
            .distinct()
            .order_by("id")
        )

    def partial_update(self, request, *args, **kwargs):
        if not is_center(request.user):
            raise PermissionDenied()
        subject = self.get_object()
        body = SubjectSerializer(subject, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            body.save(version=subject.version + 1)
        return Response(SubjectSerializer(subject).data)

    def destroy(self, request, *args, **kwargs):
        if not is_center(request.user):
            raise PermissionDenied()
        subject = self.get_object()
        if subject_usage(subject)["total"]:
            raise Conflict(
                "SUBJECT_IN_USE",
                "Materia già usata da richieste, competenze o percorsi: archiviarla invece di eliminarla",
            )
        subject.delete()
        return Response(status=204)

    @action(detail=False, methods=["get"])
    def overview(self, request):
        """Scheda di ogni materia: tutor competenti, richieste e percorsi."""
        if not is_center(request.user):
            raise PermissionDenied()
        from datetime import date
        from apps.scheduling.models import TutorSkill

        today = date.today()
        skills = (
            TutorSkill.objects.select_related("tutor")
            .filter(tutor__active=True)
            .order_by("tutor__display_name", "level")
        )
        by_subject = {}
        for skill in skills:
            tutors = by_subject.setdefault(skill.subject_id, {})
            row = tutors.setdefault(
                skill.tutor_id,
                {
                    "id": str(skill.tutor_id),
                    "display_name": skill.tutor.display_name,
                    "levels": set(),
                    "modes": set(),
                    "pending": False,
                    "expired": True,
                },
            )
            current = skill.valid_until >= today
            if skill.approved and current:
                row["levels"].add(skill.level)
                row["modes"].add(skill.mode)
                row["expired"] = False
            elif not skill.approved and current:
                row["pending"] = True
                row["expired"] = False
        requests = TeachingRequest.objects.filter(
            status__in=["PENDING", "APPROVED"], period_end__gte=today
        ).values_list("subject_id", "status", "kind")
        counts = {}
        for subject_id, status, kind in requests:
            c = counts.setdefault(
                subject_id, {"pending": 0, "approved": 0, "series": 0, "single": 0}
            )
            c["pending" if status == "PENDING" else "approved"] += 1
            if kind == "SERIES":
                c["series"] += 1
            elif kind == "SINGLE":
                c["single"] += 1
        out = []
        for subject in Subject.objects.order_by("name"):
            tutors = sorted(
                by_subject.get(subject.id, {}).values(),
                key=lambda t: t["display_name"],
            )
            usage = subject_usage(subject)
            out.append(
                {
                    **SubjectSerializer(subject).data,
                    "tutors": [
                        {
                            **t,
                            "levels": sorted(t["levels"]),
                            "modes": sorted(t["modes"]),
                        }
                        for t in tutors
                    ],
                    "requests": counts.get(
                        subject.id,
                        {"pending": 0, "approved": 0, "series": 0, "single": 0},
                    ),
                    "paths": usage["paths"],
                    "deletable": usage["total"] == 0,
                }
            )
        return Response({"results": out})


def subject_usage(subject):
    from apps.scheduling.models import TutorSkill

    paths = LearningPath.objects.filter(required_subjects=subject).count()
    total = (
        paths
        + TeachingRequest.objects.filter(subject=subject).count()
        + TutorSkill.objects.filter(subject=subject).count()
        + TeachingGroup.objects.filter(subject=subject).count()
        + CurriculumBlock.objects.filter(subject=subject).count()
    )
    return {"paths": paths, "total": total}


class PathsView(CenterCreateView):
    serializer_class = PathSerializer

    def get_queryset(self):
        qs = LearningPath.objects.all()
        if not is_center(self.request.user):
            qs = qs.filter(
                enrollments__student__in=visible_students(self.request.user),
                enrollments__active=True,
            ).distinct()
        return qs.order_by("id")

    @transaction.atomic
    def perform_create(self, serializer):
        path = serializer.save()
        PathAuditEvent.objects.create(
            path=path,
            actor=self.request.user,
            operation="create_path",
            details={"kind": path.kind},
        )

    @action(detail=True, methods=["post"], url_path="derive-requests")
    def derive(self, request, pk=None):
        if not is_center(request.user):
            raise PermissionDenied()
        path = self.get_object()
        body = request.data
        if (
            not isinstance(body, dict)
            or set(body) != {"expected_version"}
            or type(body["expected_version"]) is not int
            or body["expected_version"] < 1
        ):
            return Response(
                {
                    "code": "INVALID_PAYLOAD",
                    "message": "Fornire solo expected_version intera positiva",
                },
                status=400,
            )
        result = derive_requests(
            path.id,
            request.user,
            body["expected_version"],
            request.headers.get("Idempotency-Key", ""),
        )
        return Response(result)

    @action(detail=True, methods=["get"], url_path="curriculum-summary")
    def summary(self, request, pk=None):
        path = self.get_object()
        scope = visible_students(request.user)
        enrollments = (
            path.enrollments.filter(active=True, student__in=scope)
            .select_related("student")
            .order_by("student_id")
        )
        subjects = list(path.required_subjects.order_by("name"))
        blocks = list(path.blocks.select_related("group", "subject"))
        rows = []
        for enrollment in enrollments:
            subject_rows = []
            for subject in subjects:
                own = []
                invalid = []
                for block in blocks:
                    if block.subject_id != subject.id:
                        continue
                    # Consider only potentially pertinent targets to avoid leaking other enrollment errors.
                    if block.student_id != enrollment.student_id and not (
                        block.group_id
                        and block.group.memberships.filter(
                            student_id=enrollment.student_id
                        ).exists()
                    ):
                        continue
                    try:
                        if enrollment.student_id in participant_ids(block):
                            own.append(block)
                    except DomainError as error:
                        invalid.append(str(error.detail["code"]))
                cursor = enrollment.period_start
                intervals = sorted((b.period_start, b.period_end) for b in own)
                for first, last in intervals:
                    if last < cursor:
                        continue
                    if first > cursor:
                        break
                    cursor = max(cursor, last + timedelta(days=1))
                # Sum only concurrently applicable minutes; sequential terms are never added together.
                boundaries = sorted(
                    {enrollment.period_start, enrollment.period_end + timedelta(days=1)}
                    | {max(b.period_start, enrollment.period_start) for b in own}
                    | {
                        min(b.period_end, enrollment.period_end) + timedelta(days=1)
                        for b in own
                    }
                )
                segments = []
                for first, after in zip(boundaries, boundaries[1:]):
                    if (
                        first >= after
                        or first < enrollment.period_start
                        or first > enrollment.period_end
                    ):
                        continue
                    active = [b for b in own if b.period_start <= first <= b.period_end]
                    segments.append(
                        {
                            "period_start": str(first),
                            "period_end": str(after - timedelta(days=1)),
                            "required_minutes_per_week": sum(
                                b.minutes_per_week for b in active
                            ),
                            "overlap": len(active) > 1,
                        }
                    )
                subject_rows.append(
                    {
                        "subject_id": str(subject.id),
                        "subject_name": subject.name,
                        "covered_full_period": cursor > enrollment.period_end
                        and not invalid,
                        "segments": segments,
                        "validation_codes": sorted(set(invalid)),
                        "scheduled_minutes": None,
                        "attended_minutes": None,
                    }
                )
            rows.append(
                {
                    "student_id": str(enrollment.student_id),
                    "student_name": enrollment.student.display_name,
                    "subjects": subject_rows,
                }
            )
        return Response(
            {
                "path_id": str(path.id),
                "version": path.version,
                "measure": "required_weekly_minutes_by_period",
                "students": rows,
                "calendar_available": False,
            }
        )


class EnrollmentsView(CenterCreateView):
    serializer_class = EnrollmentSerializer

    def get_queryset(self):
        return (
            PathEnrollment.objects.filter(
                student__in=visible_students(self.request.user)
            )
            .select_related("student")
            .order_by("id")
        )

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        lock_revision()
        path = LearningPath.objects.select_for_update().get(pk=data["path"].pk)
        self.assert_mutable(path)
        assert_period(path, data["period_start"], data["period_end"])
        if not data["student"].active:
            raise DomainError("STUDENT_INACTIVE", "Lo studente deve essere attivo")
        obj = serializer.save()
        touch_path(
            path, self.request.user, "enroll_student", {"enrollment_id": str(obj.id)}
        )


class GroupsView(CenterCreateView):
    serializer_class = GroupSerializer

    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        return TeachingGroup.objects.all().order_by("id")

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        lock_revision()
        path = LearningPath.objects.select_for_update().get(pk=data["path"].pk)
        self.assert_mutable(path)
        if not path.required_subjects.filter(pk=data["subject"].pk).exists():
            raise DomainError("SUBJECT_OUTSIDE_CURRICULUM", "Materia fuori programma")
        obj = serializer.save()
        touch_path(path, self.request.user, "create_group", {"group_id": str(obj.id)})


class MembershipsView(CenterCreateView):
    serializer_class = MembershipSerializer

    def get_queryset(self):
        if not is_center(self.request.user):
            raise PermissionDenied()
        return GroupMembership.objects.all().order_by("id")

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        lock_revision()
        path = LearningPath.objects.select_for_update().get(pk=data["group"].path_id)
        self.assert_mutable(path)
        assert_period(path, data["period_start"], data["period_end"])
        if not PathEnrollment.objects.filter(
            path=path,
            student=data["student"],
            active=True,
            period_start__lte=data["period_start"],
            period_end__gte=data["period_end"],
        ).exists():
            raise DomainError(
                "ENROLLMENT_NOT_COVERED",
                "Iscrizione al percorso necessaria per tutto il periodo",
            )
        obj = serializer.save()
        validate_blocks(path)
        touch_path(
            path, self.request.user, "add_group_member", {"membership_id": str(obj.id)}
        )


class BlocksView(CenterCreateView):
    serializer_class = BlockSerializer

    def get_queryset(self):
        # Full target/group/objective data remains center-only in this prototype. Families use summary.
        if not is_center(self.request.user):
            raise PermissionDenied()
        return CurriculumBlock.objects.select_related("subject").order_by("id")

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        lock_revision()
        path = LearningPath.objects.select_for_update().get(pk=data["path"].pk)
        self.assert_mutable(path)
        obj = serializer.save()
        validate_blocks(path)
        touch_path(
            path,
            self.request.user,
            "create_curriculum_block",
            {"block_id": str(obj.id)},
        )
