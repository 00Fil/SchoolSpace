"""P6 · Presa visione dell'informativa (C04) e destinatari dell'export (richiede PostgreSQL)."""

import pytest

from tests.test_calendar import center, pytestmark  # noqa: F401


def _guardian(center):
    from tests.test_calendar_conflicts import guardian_of
    from tests.test_p4_operativita import WEEK, client_for, publish, week_lessons

    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = guardian_of(student)
    return guardian, client_for(guardian), student


def test_notice_must_be_acknowledged_once_per_version(center):
    from api.my_data import NOTICE_VERSION

    guardian, client, _ = _guardian(center)
    assert client.get("/api/v1/me").json()["notice_pending"] is True
    assert client.get("/api/v1/me/data").json()["notice_acknowledged"] is False
    old = client.post("/api/v1/me/notice/acknowledge", {"version": "1999-01"}, format="json")
    assert old.status_code == 409 and old.json()["current"] == NOTICE_VERSION
    ok = client.post("/api/v1/me/notice/acknowledge", {"version": NOTICE_VERSION}, format="json")
    assert ok.status_code == 200, ok.content
    again = client.post("/api/v1/me/notice/acknowledge", {"version": NOTICE_VERSION}, format="json")
    assert again.status_code == 200  # idempotente
    assert client.get("/api/v1/me").json()["notice_pending"] is False


def test_center_never_has_notice_pending(center):
    assert center[2].get("/api/v1/me").json()["notice_pending"] is False


def test_audiences_list_active_guardians_and_are_center_only(center):
    guardian, client, student = _guardian(center)
    res = client.post("/api/v1/me/data/requests", {"kind": "ACCESS", "subject_type": "STUDENT", "subject_id": str(student)}, format="json")
    assert res.status_code == 201, res.content
    pk = res.json()["id"]
    assert client.get(f"/api/v1/privacy/requests/{pk}/audiences").status_code == 403
    ids = [r["id"] for r in center[2].get(f"/api/v1/privacy/requests/{pk}/audiences").json()["results"]]
    assert str(guardian.pk) in ids
