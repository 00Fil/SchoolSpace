"""GAP-E04 (s2-calendario): presenze per partecipante, COMPLETED, correzione (T30)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient
from apps.identity.models import Account, RoleGrant
from apps.calendar.models import (
    Attendance,
    AttendanceRevision,
    CalendarAudit,
    RecoveryObligation,
)
from apps.communications.models import OutboxEvent
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import post, set_now, week_lessons


def tutor_client(lesson):
    account = lesson.tutor.account
    RoleGrant.objects.create(
        account=account, role="TUTOR", valid_from=timezone.now() - timedelta(days=1)
    )
    client = APIClient()
    client.force_authenticate(account)
    return client


def entries(lesson, *statuses):
    students = lesson.participants.order_by("student_id").values_list(
        "student_id", flat=True
    )
    out = []
    for student, status in zip(students, statuses):
        entry = {"student_id": str(student), "status": status}
        if status == "PRESENT":
            entry["minutes"] = 60
        out.append(entry)
    return out


@pytest.fixture
def ended(center, monkeypatch):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    set_now(monkeypatch, lesson.end_at + timedelta(minutes=5))
    return center, lesson


def test_t30_tutor_records_center_corrects(ended):
    center, lesson = ended
    tutor = tutor_client(lesson)
    url = f"/api/v1/occurrences/{lesson.id}/attendance/"
    body = {"expected_version": 1, "entries": entries(lesson, "PRESENT", "ABSENT")}
    recorded = post(tutor, url, body, "a1")
    assert recorded.status_code == 200, recorded.data
    assert recorded.data["counts"] == {
        "PRESENT": 1,
        "ABSENT": 1,
        "JUSTIFIED": 0,
        "NOT_RECORDED": 0,
    }
    assert post(tutor, url, body, "a1").data == recorded.data
    assert tutor.get(url).status_code == 200
    done = post(
        tutor,
        f"/api/v1/occurrences/{lesson.id}/complete/",
        {"expected_version": 1},
        "c1",
    )
    assert done.status_code == 200, done.data
    lesson.refresh_from_db()
    assert lesson.state == "COMPLETED" and lesson.completed_at is not None
    assert OutboxEvent.objects.filter(event_type="lesson.completed").exists()
    # Dopo COMPLETED il tutor non riscrive le presenze.
    late = post(tutor, url, {**body, "expected_version": 2}, "a2")
    assert late.data["code"] == "ATTENDANCE_LOCKED"
    # Il tutor non può fare correzioni amministrative.
    correction = {
        "expected_version": 2,
        "entries": entries(lesson, "PRESENT", "JUSTIFIED"),
        "reason": "Certificato medico",
        "confirm_correction": True,
    }
    corr_url = f"/api/v1/occurrences/{lesson.id}/admin-correction/"
    assert post(tutor, corr_url, correction, "x1").status_code == 403
    unconfirmed = post(
        center[2], corr_url, {**correction, "confirm_correction": False}, "x2"
    )
    assert unconfirmed.data["code"] == "CORRECTION_CONFIRMATION"
    fixed = post(center[2], corr_url, correction, "x3")
    assert fixed.status_code == 200, fixed.data
    assert fixed.data["counts"]["JUSTIFIED"] == 1
    audit = CalendarAudit.objects.get(operation="ADMIN_CORRECTION")
    assert audit.reason == "Certificato medico" and audit.actor == center[0]
    assert audit.before["entries"] != audit.after["entries"]
    absent = Attendance.objects.get(lesson=lesson, status="JUSTIFIED")
    history = list(
        absent.revisions.order_by("sequence").values_list("status", "command")
    )
    assert history == [("ABSENT", "RECORD"), ("JUSTIFIED", "ADMIN_CORRECTION")]
    same = post(center[2], corr_url, {**correction, "expected_version": 3}, "x4")
    assert same.data["code"] == "NO_CHANGES"
    assert OutboxEvent.objects.filter(event_type="attendance.corrected").count() == 1


def test_complete_requires_end_and_all_participants(center, monkeypatch):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    url = f"/api/v1/occurrences/{lesson.id}/attendance/"
    body = {"expected_version": 1, "entries": entries(lesson, "PRESENT")}
    assert post(center[2], url, body, "a0").data["code"] == "LESSON_NOT_STARTED"
    set_now(monkeypatch, lesson.start_at + timedelta(minutes=10))
    assert post(center[2], url, body, "a1").status_code == 200
    complete = f"/api/v1/occurrences/{lesson.id}/complete/"
    early = post(center[2], complete, {"expected_version": 1}, "c0")
    assert early.data["code"] == "LESSON_NOT_ENDED"
    set_now(monkeypatch, lesson.end_at + timedelta(minutes=1))
    partial = post(center[2], complete, {"expected_version": 1}, "c1")
    assert partial.data["code"] == "ATTENDANCE_INCOMPLETE"


@pytest.mark.parametrize(
    "entry_change,code",
    [
        (
            {"student_id": "00000000-0000-0000-0000-000000000001"},
            "ATTENDANCE_PARTICIPANT_INVALID",
        ),
        ({"status": "ABSENT", "minutes": 30}, "ATTENDANCE_MINUTES_INVALID"),
        ({"minutes": 61}, "ATTENDANCE_MINUTES_INVALID"),
    ],
)
def test_attendance_validation(ended, entry_change, code):
    center, lesson = ended
    entry = {**entries(lesson, "PRESENT")[0], **entry_change}
    response = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/attendance/",
        {"expected_version": 1, "entries": [entry]},
        "bad",
    )
    assert response.data["code"] == code and not Attendance.objects.exists()


def test_tutor_permission_setting_and_outsiders(ended, settings):
    center, lesson = ended
    url = f"/api/v1/occurrences/{lesson.id}/attendance/"
    body = {"expected_version": 1, "entries": entries(lesson, "PRESENT", "PRESENT")}
    settings.CALENDAR_TUTOR_RECORDS_ATTENDANCE = False
    tutor = tutor_client(lesson)
    assert post(tutor, url, body, "t1").status_code == 403
    family = APIClient()
    family.force_authenticate(
        Account.objects.create_user(username="fam", email="fam@example.invalid")
    )
    assert post(family, url, body, "f1").status_code == 403
    assert family.get(url).status_code == 404
    assert not Attendance.objects.exists()


def test_recovery_from_completed_only_for_absent(ended):
    center, lesson = ended
    url = f"/api/v1/occurrences/{lesson.id}/attendance/"
    rows = entries(lesson, "PRESENT", "ABSENT")
    post(center[2], url, {"expected_version": 1, "entries": rows}, "a1")
    post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/complete/",
        {"expected_version": 1},
        "c1",
    )
    rec_url = f"/api/v1/occurrences/{lesson.id}/recovery/"
    body = {
        "expected_version": 2,
        "cause": "STUDENT_ABSENCE",
        "participant_ids": [rows[0]["student_id"]],
        "reason": "Recupero assente",
    }
    wrong = post(center[2], rec_url, body, "r1")
    assert wrong.data["code"] == "RECOVERY_PARTICIPANTS_INVALID"
    ok = post(
        center[2], rec_url,
        # D06: assenza non avvisata 24 ore prima -> il centro concede il recupero esplicitamente
        {**body, "participant_ids": [rows[1]["student_id"]], "grant_late_notice": True}, "r2"
    )
    assert ok.status_code == 200, ok.data
    assert RecoveryObligation.objects.get().participants == [rows[1]["student_id"]]


def test_audit_and_revisions_append_only_in_orm(ended):
    center, lesson = ended
    post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/attendance/",
        {"expected_version": 1, "entries": entries(lesson, "PRESENT", "PRESENT")},
        "a1",
    )
    audit = CalendarAudit.objects.filter(lesson=lesson).first()
    revision = AttendanceRevision.objects.first()
    for row in (audit, revision):
        with pytest.raises(ValidationError):
            row.save()
        with pytest.raises(ValidationError):
            row.delete()
    with pytest.raises(ValidationError):
        CalendarAudit.objects.all().update(reason="x")
    with pytest.raises(ValidationError):
        AttendanceRevision.objects.all().delete()
