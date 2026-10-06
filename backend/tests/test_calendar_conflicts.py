"""GAP-E05 (s2-calendario): ConflictCase automatiche, risoluzione, ChangeRequest (T41)."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient
from apps.availability.models import AvailabilityException
from apps.calendar.models import (
    ChangeRequest,
    ConflictCase,
    LessonOccurrence,
    RecoveryObligation,
)
from apps.communications.models import OutboxEvent
from apps.education.models import GuardianLink
from apps.identity.models import Account, RoleGrant
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import post, week_lessons


def block_tutor(lesson):
    return AvailabilityException.objects.create(
        tutor_id=lesson.tutor_id,
        start_at=lesson.start_at,
        end_at=lesson.end_at,
        mode=lesson.mode,
        location=lesson.location,
        kind="REMOVE_AVAILABLE",
    )


def client_for(account):
    client = APIClient()
    client.force_authenticate(account)
    return client


def guardian_of(student_id, name="tutore", can_request_changes=True):
    from apps.privacy.models import GuardianLinkDetail

    account = Account.objects.create_user(
        username=name, email=f"{name}@example.invalid"
    )
    since = timezone.now() - timedelta(days=1)
    RoleGrant.objects.create(account=account, role="GUARDIAN", valid_from=since)
    link = GuardianLink.objects.create(
        account=account,
        student_id=student_id,
        can_view=True,
        verified=True,
        valid_from=since,
    )
    GuardianLinkDetail.objects.update_or_create(
        link=link, defaults={"can_request_changes": can_request_changes}
    )
    return account


def test_t41_availability_change_opens_case_without_touching_calendar(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    block_tutor(lesson)
    case = ConflictCase.objects.get(state="OPEN")
    assert case.lesson_id == lesson.id and case.kind == "VALIDATION"
    assert case.week_start == WEEK and case.codes
    lesson.refresh_from_db()
    assert lesson.state == "PUBLISHED" and lesson.version == 1
    # Nuove rilevazioni non duplicano la pratica aperta.
    assert (
        post(center[2], "/api/v1/conflict-cases/detect/", {}, "d1").status_code == 200
    )
    assert ConflictCase.objects.filter(state="OPEN").count() == 1
    rows = center[2].get("/api/v1/calendar/?from=2026-10-05&until=2026-10-12").data
    flagged = next(r for r in rows["results"] if r["id"] == str(lesson.id))
    assert flagged["warnings"]["open_conflicts"] == 1
    # Notifica interna solo agli operatori con ruolo CENTER (qui nessuno): mai famiglie.
    event = OutboxEvent.objects.get(event_type="conflict.opened")
    assert not event.deliveries.exists() and "participants" not in event.payload


def test_confirm_requires_revalidation_then_cancel_with_recovery(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    block = block_tutor(lesson)
    case = ConflictCase.objects.get(state="OPEN")
    url = f"/api/v1/conflict-cases/{case.id}/resolve/"
    confirm = {"expected_version": 1, "resolution": "CONFIRM", "reason": "Ok"}
    refused = post(center[2], url, confirm, "c1")
    assert refused.data["code"] == "CALENDAR_VALIDATION_FAILED"
    assert ConflictCase.objects.get(pk=case.id).state == "OPEN"
    cancel = {
        "expected_version": 1,
        "resolution": "CANCEL",
        "reason": "Tutor assente",
        "recovery_cause": "TUTOR_ABSENCE",
    }
    done = post(center[2], url, cancel, "c2")
    assert done.status_code == 200, done.data
    assert (
        done.data["state"] == "RESOLVED" and done.data["lesson"]["state"] == "CANCELLED"
    )
    obligation = RecoveryObligation.objects.get(pk=done.data["recovery_id"])
    assert obligation.origin_lesson_id == lesson.id and obligation.state == "OPEN"
    assert post(center[2], url, cancel, "c2").data == done.data
    block.delete()


def test_confirm_after_data_fixed(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    block = block_tutor(lesson)
    case = ConflictCase.objects.get(state="OPEN")
    block.delete()
    body = {"expected_version": 1, "resolution": "CONFIRM", "reason": "Rientrato"}
    done = post(center[2], f"/api/v1/conflict-cases/{case.id}/resolve/", body, "c1")
    assert done.status_code == 200, done.data
    assert done.data["resolution"] == "CONFIRM"
    lesson.refresh_from_db()
    assert lesson.version == 1


def test_resolution_center_only(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    block_tutor(lesson)
    case = ConflictCase.objects.get(state="OPEN")
    student = lesson.participants.values_list("student_id", flat=True).first()
    family = client_for(guardian_of(student))
    body = {"expected_version": 1, "resolution": "CANCEL", "reason": "No"}
    url = f"/api/v1/conflict-cases/{case.id}/resolve/"
    assert post(family, url, body, "f1").status_code == 403
    assert family.get("/api/v1/conflict-cases/").status_code == 403
    assert ConflictCase.objects.get(pk=case.id).state == "OPEN"


def test_guardian_absence_request_opens_case_only(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student))
    body = {
        "lesson_id": str(lesson.id),
        "kind": "ABSENCE",
        "reason": "Malattia",
        "student_id": str(student),
    }
    response = post(guardian, "/api/v1/change-requests/", body, "g1")
    assert response.status_code == 200, response.data
    assert response.data["calendar_changed"] is False
    case = ConflictCase.objects.get(pk=response.data["conflict_case_id"])
    assert case.kind == "STUDENT_ABSENCE"
    lesson.refresh_from_db()
    assert lesson.version == 1
    assert post(guardian, "/api/v1/change-requests/", body, "g1").data == response.data
    listed = guardian.get("/api/v1/change-requests/").data["results"]
    assert [r["id"] for r in listed] == [response.data["id"]]
    warnings = center[2].get("/api/v1/calendar/?from=2026-10-05&until=2026-10-12")
    row = next(r for r in warnings.data["results"] if r["id"] == str(lesson.id))
    assert row["warnings"]["pending_change_requests"] == 1
    # Senza studente visibile la richiesta è rifiutata.
    missing = post(
        guardian, "/api/v1/change-requests/", {**body, "student_id": None}, "g2"
    )
    assert missing.data["code"] == "STUDENT_REQUIRED"


def test_guardian_without_change_permission_is_forbidden(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student, "sola-lettura", False))
    body = {
        "lesson_id": str(lesson.id),
        "kind": "ABSENCE",
        "reason": "Impegno",
        "student_id": str(student),
    }
    response = post(guardian, "/api/v1/change-requests/", body, "ro1")
    assert response.status_code == 403, response.data
    assert not ChangeRequest.objects.exists()


def test_outsider_gets_404_and_cannot_decide(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    other = (
        week_lessons(WEEK, state="PUBLISHED")
        .exclude(participants__student_id__in=lesson.participants.values("student_id"))
        .first()
    )
    student = other.participants.values_list("student_id", flat=True).first()
    outsider = client_for(guardian_of(student, "estraneo"))
    body = {
        "lesson_id": str(lesson.id),
        "kind": "CANCEL",
        "reason": "x",
        "student_id": str(student),
    }
    assert post(outsider, "/api/v1/change-requests/", body, "o1").status_code == 404
    assert not ChangeRequest.objects.exists()


def test_reschedule_request_decided_and_applied(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    account = guardian_of(student)
    guardian = client_for(account)
    target = lesson.start_at + timedelta(days=7)
    created = post(
        guardian,
        "/api/v1/change-requests/",
        {
            "lesson_id": str(lesson.id),
            "kind": "RESCHEDULE",
            "reason": "Gita",
            "student_id": str(student),
            "proposal": {"start_at": target.isoformat()},
        },
        "g1",
    ).data
    url = f"/api/v1/change-requests/{created['id']}/decide/"
    body = {"expected_version": 1, "decision": "ACCEPT", "apply": True, "reason": "Ok"}
    assert post(guardian, url, body, "g-d").status_code == 403
    decided = post(center[2], url, body, "d1")
    assert decided.status_code == 200, decided.data
    assert decided.data["state"] == "SUBMITTED" and decided.data["awaiting"] == "TUTOR"
    lesson.refresh_from_db()
    assert lesson.version == 1
    from tests.test_p4_operativita import tutor_client

    confirm = f"/api/v1/change-requests/{created['id']}/tutor-confirm/"
    done = post(tutor_client(lesson), confirm, {"expected_version": 2, "decision": "CONFIRM", "reason": "Va bene"}, "t1")
    assert done.status_code == 200, done.data
    assert done.data["state"] == "ACCEPTED"
    lesson.refresh_from_db()
    assert lesson.start_at == target and lesson.version == 2
    assert OutboxEvent.objects.filter(
        event_type="change_request.decided", deliveries__recipient=account
    ).exists()
    again = post(center[2], url, {**body, "expected_version": 3}, "d2")
    assert again.data["code"] == "CHANGE_REQUEST_CLOSED"


def test_withdraw_only_by_requester(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student))
    other = client_for(guardian_of(student, "altro"))
    created = post(
        guardian,
        "/api/v1/change-requests/",
        {
            "lesson_id": str(lesson.id),
            "kind": "CANCEL",
            "reason": "x",
            "student_id": str(student),
        },
        "g1",
    ).data
    url = f"/api/v1/change-requests/{created['id']}/withdraw/"
    body = {"expected_version": 1, "reason": "Ripensamento"}
    assert post(other, url, body, "o1").status_code == 404
    done = post(guardian, url, body, "g2")
    assert done.status_code == 200 and done.data["state"] == "WITHDRAWN"
    assert LessonOccurrence.objects.get(pk=lesson.id).state == "PUBLISHED"
