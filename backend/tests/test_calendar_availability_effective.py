"""GAP-C07 (s2-calendario): /availability/effective con diagnostica e scope."""

from datetime import timedelta

from apps.availability.models import (
    AvailabilityDeclaration,
    AvailabilityException,
    AvailabilityRule,
)
from apps.education.models import Tutor
from tests.test_calendar import center, pytestmark  # noqa: F401
from tests.test_calendar_conflicts import client_for, guardian_of
from tests.test_calendar_attendance import tutor_client
from tests.calendar_helpers import utc

URL = "/api/v1/availability/effective"


def tutors():
    return list(Tutor.objects.order_by("id"))


def codes(data):
    return {d["code"] for d in data["diagnostics"]}


def get(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"{URL}?{query}")


def test_tutor_windows_local_and_dst(center):
    tutor = AvailabilityRule.objects.filter(tutor__isnull=False).first().tutor
    data = get(
        center[2], tutor=tutor.id, **{"from": "2026-10-19", "until": "2026-11-02"}
    )
    assert data.status_code == 200, data.data
    data = data.data
    starts = [(w["start_at"], w["local_start"]) for w in data["windows"]]
    assert ("2026-10-19T08:00:00+00:00", "2026-10-19T10:00:00+02:00") in starts
    assert ("2026-10-26T09:00:00+00:00", "2026-10-26T10:00:00+01:00") in starts
    assert data["ready"] is True and data["declaration_state"] == "APPROVED"
    assert "OUTSIDE_SERVICE_WINDOWS" not in codes(data)


def test_exception_and_pending_rule_diagnostics(center):
    rule = AvailabilityRule.objects.filter(tutor__isnull=False).first()
    tutor = rule.tutor
    AvailabilityException.objects.create(
        tutor=tutor,
        start_at=utc(2026, 10, 5, 9),
        end_at=utc(2026, 10, 5, 10),
        mode=rule.mode,
        location=rule.location,
        kind="REMOVE_AVAILABLE",
    )
    week = {"from": "2026-10-05", "until": "2026-10-12"}
    data = get(center[2], tutor=tutor.id, **week).data
    windows = [w for w in data["windows"] if w["mode"] == rule.mode]
    assert [w["local_start"][11:16] for w in windows] == ["10:00", "12:00"]
    assert len(data["exceptions"]) == 1
    AvailabilityRule.objects.create(
        tutor=tutor,
        weekday=2,
        start_time=rule.start_time,
        end_time=rule.end_time,
        mode=rule.mode,
        location=rule.location,
        period_start=rule.period_start,
        period_end=rule.period_end,
        status="DRAFT",
        author=center[0],
    )
    pending = get(center[2], tutor=tutor.id, **week).data
    assert "AVAILABILITY_PENDING" in codes(pending) and pending["ready"] is False


def test_unknown_declaration_blocks(center):
    declaration = AvailabilityDeclaration.objects.filter(tutor__isnull=False).first()
    declaration.state = "UNKNOWN"
    declaration.save()
    data = get(
        center[2],
        tutor=declaration.tutor_id,
        **{"from": "2026-10-05", "until": "2026-10-12"},
    ).data
    assert "DECLARATION_UNKNOWN" in codes(data)
    assert data["windows"] == [] and data["ready"] is False


def test_scope_and_validation(center):
    rule = AvailabilityRule.objects.filter(tutor__isnull=False).first()
    own = rule.tutor
    other = next(t for t in tutors() if t.id != own.id)
    week = {"from": "2026-10-05", "until": "2026-10-12"}
    lesson_like = type("L", (), {"tutor": own})()
    assert own.account_id is not None
    tutor = tutor_client(lesson_like)
    assert get(tutor, tutor=own.id, **week).status_code == 200
    assert get(tutor, tutor=other.id, **week).status_code == 404
    student_rule = AvailabilityRule.objects.filter(student__isnull=False).first()
    guardian = client_for(guardian_of(student_rule.student_id))
    assert get(guardian, student=student_rule.student_id, **week).status_code == 200
    stranger = (
        AvailabilityRule.objects.filter(student__isnull=False)
        .exclude(student_id=student_rule.student_id)
        .first()
    )
    assert get(guardian, student=stranger.student_id, **week).status_code == 404
    assert get(guardian, tutor=own.id, **week).status_code == 404
    assert get(guardian, student="not-a-uuid", **week).status_code == 404
    assert get(center[2], **week).status_code == 400
    wide = {
        "from": "2026-10-05",
        "until": str(utc(2026, 10, 5).date() + timedelta(days=70)),
    }
    assert get(center[2], tutor=own.id, **wide).status_code == 400
