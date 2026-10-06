"""Synthetic curriculum tests, not the full T31/UAT or PostgreSQL race suite."""

from datetime import date, timedelta
import pytest
from django.core.management import call_command
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient
from apps.identity.models import Account, RoleGrant
from apps.education.models import (
    Family,
    Student,
    Subject,
    LearningPath,
    PathEnrollment,
    TeachingGroup,
    GroupMembership,
    CurriculumBlock,
    TeachingRequest,
    RequestParticipant,
)
from apps.governance.models import CommandReceipt, PathAuditEvent, Decision
from apps.education.path_services import derive_requests, DomainError, Conflict

pytestmark = pytest.mark.django_db
FIRST = date(2026, 10, 1)
LAST = date(2027, 6, 30)


def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def cohort():
    center = Account.objects.create_superuser(
        username="path-center",
        email="path-center@example.invalid",
        password="synthetic-test-password",
    )
    family = Family.objects.create(reference="PARENTALI-SYNTHETIC")
    students = [
        Student.objects.create(family=family, display_name=f"Iscritto sintetico {i}")
        for i in range(1, 5)
    ]
    math = Subject.objects.create(name="Matematica sintetica")
    science = Subject.objects.create(name="Scienze sintetiche")
    path = LearningPath.objects.create(
        title="Programma sintetico",
        kind="HOME_EDUCATION",
        academic_year="2026/2027",
        level="Livello di prova",
        period_start=FIRST,
        period_end=LAST,
    )
    path.required_subjects.set([math, science])
    for student in students[:2]:
        PathEnrollment.objects.create(
            path=path, student=student, period_start=FIRST, period_end=LAST
        )
    group = TeachingGroup.objects.create(
        path=path, name="Sottogruppo sintetico", subject=math, approved=True
    )
    for student in students[:2]:
        GroupMembership.objects.create(
            group=group, student=student, period_start=FIRST, period_end=LAST
        )
    return center, path, students, math, science, group


def block(path, subject, student=None, group=None, **kwargs):
    data = dict(
        path=path,
        subject=subject,
        objective="Obiettivo interno sintetico",
        student=student,
        group=group,
        period_start=FIRST,
        period_end=LAST,
        duration_minutes=60,
        sessions_per_week=1,
        minutes_per_week=60,
        mode="IN_PERSON",
        priority="P1",
        mandatory=True,
    )
    data.update(kwargs)
    return CurriculumBlock.objects.create(**data)


def complete(cohort):
    center, path, students, math, science, group = cohort
    blocks = [block(path, math, group=group)]
    blocks += [
        block(path, science, student=s, duration_minutes=120, minutes_per_week=120)
        for s in students[:2]
    ]
    return blocks


def command(c, path, version=1, key="synthetic-key"):
    return c.post(
        f"/api/v1/learning-paths/{path.id}/derive-requests/",
        {"expected_version": version},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def test_complete_program_generates_canonical_requests(cohort):
    center, path, students, *_ = cohort
    complete(cohort)
    response = command(client(center), path)
    assert response.status_code == 200, response.data
    assert response.data["created"] == 3
    assert response.data["calendar_changed"] is False
    assert TeachingRequest.objects.count() == 3
    assert RequestParticipant.objects.count() == 4
    # Group tutor time counted once; beneficiaries counted individually.
    assert (
        sum(
            r.duration_minutes * r.sessions_per_week
            for r in TeachingRequest.objects.all()
        )
        == 300
    )
    assert (
        sum(
            p.request.duration_minutes * p.request.sessions_per_week
            for p in RequestParticipant.objects.select_related("request")
        )
        == 360
    )
    assert set(TeachingRequest.objects.values_list("mode", flat=True)) == {"IN_PERSON"}


def test_exact_replay_returns_original_even_after_version_changed(cohort):
    center, path, *_ = cohort
    complete(cohort)
    c = client(center)
    first = command(c, path)
    second = command(c, path)
    assert second.status_code == 200
    assert first.data == second.data
    assert TeachingRequest.objects.count() == 3
    assert CommandReceipt.objects.count() == 1
    assert PathAuditEvent.objects.filter(operation="derive_curriculum").count() == 1


def test_new_key_does_not_duplicate(cohort):
    center, path, *_ = cohort
    complete(cohort)
    c = client(center)
    first = command(c, path)
    path.refresh_from_db()
    second = command(c, path, path.version, key="other-key")
    assert second.status_code == 200
    assert second.data["created"] == 0
    assert second.data["request_ids"] == first.data["request_ids"]
    assert TeachingRequest.objects.count() == 3


def test_same_key_different_body_conflicts(cohort):
    center, path, *_ = cohort
    complete(cohort)
    c = client(center)
    command(c, path)
    assert command(c, path, version=2).status_code == 409


def test_stale_version_no_partial_writes(cohort):
    center, path, *_ = cohort
    complete(cohort)
    assert command(client(center), path, version=99).status_code == 409
    assert TeachingRequest.objects.count() == 0
    assert CommandReceipt.objects.count() == 0


def test_missing_key_rejected(cohort):
    center, path, *_ = cohort
    complete(cohort)
    response = client(center).post(
        f"/api/v1/learning-paths/{path.id}/derive-requests/",
        {"expected_version": 1},
        format="json",
    )
    assert response.status_code == 422
    assert TeachingRequest.objects.count() == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_version": True},
        {"expected_version": 0},
        {"expected_version": 1, "role": "CENTER"},
    ],
)
def test_derive_payload_strict(cohort, body):
    center, path, *_ = cohort
    assert (
        client(center)
        .post(
            f"/api/v1/learning-paths/{path.id}/derive-requests/",
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY="key",
        )
        .status_code
        == 400
    )


def test_missing_subject_blocks_entire_derivation(cohort):
    center, path, students, math, science, group = cohort
    block(path, math, group=group)
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "INCOMPLETE_PROGRAM"
    assert TeachingRequest.objects.count() == 0


def test_partial_period_not_complete_program(cohort):
    center, path, students, math, science, group = cohort
    complete(cohort)
    target = path.blocks.filter(subject=science).first()
    target.period_start = FIRST + timedelta(days=2)
    target.save()
    response = command(client(center), path)
    assert response.status_code == 422
    assert TeachingRequest.objects.count() == 0


def test_individual_and_group_same_subject_not_double_counted(cohort):
    center, path, students, math, science, group = cohort
    complete(cohort)
    block(path, math, student=students[0])
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "DUPLICATE_CURRICULUM_COVERAGE"
    assert TeachingRequest.objects.count() == 0


def test_physical_group_of_three_rejected(cohort):
    center, path, students, math, science, group = cohort
    complete(cohort)
    PathEnrollment.objects.create(
        path=path, student=students[2], period_start=FIRST, period_end=LAST
    )
    GroupMembership.objects.create(
        group=group, student=students[2], period_start=FIRST, period_end=LAST
    )
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "SPACE_CAPACITY"


def test_online_capacity_must_be_explicit(cohort):
    center, path, *_ = cohort
    complete(cohort)
    b = path.blocks.filter(group__isnull=False).get()
    b.mode = "ONLINE"
    b.save()
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "ONLINE_CAPACITY"


def test_online_capacity_separate_from_physical(cohort):
    center, path, students, math, science, group = cohort
    complete(cohort)
    PathEnrollment.objects.create(
        path=path, student=students[2], period_start=FIRST, period_end=LAST
    )
    GroupMembership.objects.create(
        group=group, student=students[2], period_start=FIRST, period_end=LAST
    )
    group.online_capacity = 3
    group.save()
    b = path.blocks.filter(group__isnull=False).get()
    b.mode = "ONLINE"
    b.save()
    block(path, science, student=students[2])
    assert command(client(center), path).status_code == 200


def test_group_must_be_approved(cohort):
    center, path, _, _, _, group = cohort
    complete(cohort)
    group.approved = False
    group.save()
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "GROUP_NOT_APPROVED"


def test_dated_membership_change_requires_segmentation(cohort):
    center, path, _, _, _, group = cohort
    complete(cohort)
    m = group.memberships.first()
    m.period_end = LAST - timedelta(days=1)
    m.save()
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "MEMBERSHIP_SEGMENT_REQUIRED"


def test_short_enrollment_cannot_cover_block(cohort):
    center, path, *_ = cohort
    complete(cohort)
    e = path.enrollments.first()
    e.period_end = LAST - timedelta(days=1)
    e.save()
    response = command(client(center), path)
    assert response.status_code == 422
    assert str(response.data["code"]) == "ENROLLMENT_NOT_COVERED"


def test_no_required_subjects_cannot_derive(cohort):
    center, path, *_ = cohort
    path.required_subjects.clear()
    assert command(client(center), path).status_code == 422


def test_minute_database_constraint(cohort):
    _, path, students, math, *_ = cohort
    with pytest.raises(IntegrityError), transaction.atomic():
        block(path, math, student=students[0], minutes_per_week=90)


def test_target_database_xor_constraint(cohort):
    _, path, students, math, _, group = cohort
    with pytest.raises(IntegrityError), transaction.atomic():
        block(path, math, student=students[0], group=group)


def test_api_invalid_block_rolled_back(cohort):
    center, path, students, math, *_ = cohort
    response = client(center).post(
        "/api/v1/curriculum-blocks/",
        {
            "path": str(path.id),
            "subject": str(math.id),
            "objective": "test",
            "student": str(students[0].id),
            "period_start": "2026-09-01",
            "period_end": "2027-06-30",
            "minutes_per_week": 60,
            "duration_minutes": 60,
            "sessions_per_week": 1,
            "mode": "IN_PERSON",
            "priority": "P1",
            "mandatory": True,
        },
        format="json",
    )
    assert response.status_code == 422
    assert CurriculumBlock.objects.count() == 0
    path.refresh_from_db()
    assert path.version == 1


def test_program_frozen_after_derivation(cohort):
    center, path, students, *_ = cohort
    complete(cohort)
    c = client(center)
    command(c, path)
    response = c.post(
        "/api/v1/path-enrollments/",
        {
            "path": str(path.id),
            "student": str(students[2].id),
            "period_start": str(FIRST),
            "period_end": str(LAST),
            "active": True,
        },
        format="json",
    )
    assert response.status_code == 409
    assert path.enrollments.count() == 2


def test_source_tampering_is_not_silently_overwritten(cohort):
    center, path, *_ = cohort
    complete(cohort)
    c = client(center)
    command(c, path)
    path.refresh_from_db()
    r = TeachingRequest.objects.first()
    r.sessions_per_week = 5
    r.save()
    response = command(c, path, version=path.version, key="new-key")
    assert response.status_code == 409
    r.refresh_from_db()
    assert r.sessions_per_week == 5


@pytest.fixture
def family_user(cohort):
    from apps.education.models import GuardianLink

    _, _, students, *_ = cohort
    account = Account.objects.create_user(
        username="path-guardian", email="path-guardian@example.invalid"
    )
    RoleGrant.objects.create(
        account=account, role="GUARDIAN", valid_from=timezone.now()
    )
    link = GuardianLink.objects.create(
        account=account,
        student=students[0],
        verified=True,
        can_view=True,
        valid_from=timezone.now(),
    )
    return account, link


def test_family_summary_only_own_child(cohort, family_user):
    _, path, students, *_ = cohort
    complete(cohort)
    account, _ = family_user
    response = client(account).get(
        f"/api/v1/learning-paths/{path.id}/curriculum-summary/"
    )
    assert response.status_code == 200
    assert [s["student_id"] for s in response.data["students"]] == [str(students[0].id)]
    assert str(students[1].id) not in str(response.data)
    assert students[1].display_name not in str(response.data)
    assert all(
        s["scheduled_minutes"] is None and s["attended_minutes"] is None
        for s in response.data["students"][0]["subjects"]
    )


def test_group_request_does_not_leak_other_participants(cohort, family_user):
    center, path, students, *_ = cohort
    complete(cohort)
    command(client(center), path)
    account, _ = family_user
    response = client(account).get("/api/v1/teaching-requests/")
    assert response.data["count"] == 2
    assert all(
        r["participant_ids"] == [str(students[0].id)] for r in response.data["results"]
    )
    assert str(students[1].id) not in str(response.data)


def test_guardian_cannot_manage_cohort_or_derive(cohort, family_user):
    _, path, *_ = cohort
    account, _ = family_user
    c = client(account)
    for endpoint in (
        "learning-paths",
        "path-enrollments",
        "curriculum-blocks",
        "teaching-groups",
        "group-memberships",
        "subjects",
    ):
        assert c.post("/api/v1/" + endpoint + "/", {}, format="json").status_code == 403
    assert command(c, path).status_code == 403
    assert c.get("/api/v1/teaching-groups/").status_code == 403
    assert c.get("/api/v1/curriculum-blocks/").status_code == 403


def test_revocation_hides_whole_path(cohort, family_user):
    _, path, *_ = cohort
    account, link = family_user
    c = client(account)
    assert c.get(f"/api/v1/learning-paths/{path.id}/").status_code == 200
    link.revoked_at = timezone.now()
    link.save()
    assert c.get(f"/api/v1/learning-paths/{path.id}/").status_code == 404
    assert (
        c.get(f"/api/v1/learning-paths/{path.id}/curriculum-summary/").status_code
        == 404
    )
    assert c.get("/api/v1/path-enrollments/").data["count"] == 0


def test_sequential_blocks_do_not_sum_weekly_minutes(cohort):
    center, path, students, math, science, group = cohort
    middle = date(2027, 1, 31)
    block(path, math, group=group, period_end=middle)
    block(
        path,
        math,
        group=group,
        period_start=middle + timedelta(days=1),
        duration_minutes=120,
        minutes_per_week=120,
    )
    for s in students[:2]:
        block(path, science, student=s)
    assert command(client(center), path).status_code == 200
    response = client(center).get(
        f"/api/v1/learning-paths/{path.id}/curriculum-summary/"
    )
    subject = next(
        s
        for s in response.data["students"][0]["subjects"]
        if s["subject_name"] == math.name
    )
    assert [s["required_minutes_per_week"] for s in subject["segments"]] == [60, 120]
    assert subject["covered_full_period"] is True


def test_create_path_requires_declared_subjects(cohort):
    center, *_ = cohort
    response = client(center).post(
        "/api/v1/learning-paths/",
        {
            "title": "Test",
            "kind": "HOME_EDUCATION",
            "academic_year": "2026/2027",
            "level": "Test",
            "period_start": str(FIRST),
            "period_end": str(LAST),
            "required_subjects": [],
        },
        format="json",
    )
    assert response.status_code == 400


def test_create_enrollment_touches_version_and_audit(cohort):
    center, path, students, *_ = cohort
    response = client(center).post(
        "/api/v1/path-enrollments/",
        {
            "path": str(path.id),
            "student": str(students[2].id),
            "period_start": str(FIRST),
            "period_end": str(LAST),
            "active": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    path.refresh_from_db()
    assert path.version == 2
    assert PathAuditEvent.objects.filter(operation="enroll_student").count() == 1


def test_scope_clarification_does_not_sign_g1():
    call_command("bootstrap_center")
    call_command("record_parentali_scope")
    d = Decision.objects.get(code="D01")
    assert "tutto il programma scolastico" in d.outcome
    assert d.status == "PROPOSED" and d.approved_at is None


def test_optional_demo_is_idempotent_and_synthetic(cohort):
    center, *_ = cohort
    call_command("seed_parentali_demo", actor=center.username)
    requests = TeachingRequest.objects.count()
    call_command("seed_parentali_demo", actor=center.username)
    assert TeachingRequest.objects.count() == requests == 4
    assert RequestParticipant.objects.count() == 8


def test_record_scope_does_not_downgrade_approved_decision():
    Decision.objects.create(
        code="D01",
        title="Decisione approvata",
        status="APPROVED",
        outcome="Esito già approvato",
    )
    call_command("record_parentali_scope")
    assert Decision.objects.get(code="D01").status == "APPROVED"
