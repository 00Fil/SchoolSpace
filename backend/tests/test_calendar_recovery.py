"""GAP-E03 (s2-calendario): RecoveryObligation, makeup, riapertura (T40)."""

from datetime import timedelta

import pytest
from apps.calendar.models import (
    CalendarAudit,
    LessonOccurrence,
    RecoveryObligation,
)
from apps.calendar.services import change_lesson
from apps.communications.models import OutboxEvent
from apps.scheduling.source import compile_source
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import post, week_lessons


def cancelled(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    change_lesson(
        center[0],
        lesson.id,
        "cancel",
        {"expected_version": 1, "reason": "Chiusura"},
        "cancel",
    )
    lesson.refresh_from_db()
    return lesson


def recovery_body(lesson, **extra):
    return {
        "expected_version": lesson.version,
        "cause": "CENTER_CANCELLATION",
        "participant_ids": [
            str(s) for s in lesson.participants.values_list("student_id", flat=True)
        ],
        "reason": "Recupero dovuto",
        **extra,
    }


def makeup_body(obligation, origin, start_at, **extra):
    return {
        "expected_version": obligation["version"],
        "start_at": start_at.isoformat(),
        "tutor_id": str(origin.tutor_id),
        "mode": origin.mode,
        "location": origin.location,
        "space_id": str(origin.space_id),
        "video_id": None,
        "reason": "Recupero",
        **extra,
    }


def test_t40_full_cycle_same_obligation(center):
    lesson = cancelled(center)
    client = center[2]
    url = f"/api/v1/occurrences/{lesson.id}/recovery/"
    created = post(client, url, recovery_body(lesson), "r1")
    assert created.status_code == 200, created.data
    obligation = created.data
    assert obligation["state"] == "OPEN" and obligation["created"] is True
    assert obligation["canonical_key"] == f"recovery:lesson:{lesson.id}"
    # Stesso comando con altra chiave: nessun secondo obbligo.
    again = post(client, url, recovery_body(lesson), "r2")
    assert again.data["id"] == obligation["id"] and again.data["created"] is False
    # L'unità recuperata non viene ripianificata dal piano settimanale.
    data, _ = compile_source(center[1], WEEK, "STRICT")
    assert all(u["locked_assignment"] for u in data["units"])
    start = lesson.start_at + timedelta(days=7)
    mk_url = f"/api/v1/recovery-obligations/{obligation['id']}/makeup/"
    made = post(client, mk_url, makeup_body(obligation, lesson, start), "m1")
    assert made.status_code == 200, made.data
    makeup = LessonOccurrence.objects.get(pk=made.data["lesson"]["id"])
    assert makeup.recovery_id is not None and makeup.start_at == start
    assert made.data["recovery"]["state"] == "SCHEDULED"
    assert OutboxEvent.objects.filter(event_type="lesson.makeup_scheduled").exists()
    # Un secondo makeup per lo stesso obbligo è rifiutato.
    second = post(
        client, mk_url, makeup_body(made.data["recovery"], lesson, start), "m2"
    )
    assert second.data["code"] == "RECOVERY_NOT_OPEN"
    # Cancellare il recupero riapre lo stesso obbligo (T40).
    change_lesson(
        center[0],
        makeup.id,
        "cancel",
        {"expected_version": makeup.version, "reason": "Assenza tutor"},
        "cancel-makeup",
    )
    row = RecoveryObligation.objects.get()
    assert str(row.id) == obligation["id"] and row.state == "OPEN"
    assert CalendarAudit.objects.filter(operation="RECOVERY_REOPENED").count() == 1
    nested = post(
        client,
        f"/api/v1/occurrences/{makeup.id}/recovery/",
        recovery_body(LessonOccurrence.objects.get(pk=makeup.id)),
        "r3",
    )
    assert nested.data["code"] == "RECOVERY_OF_RECOVERY"
    redo = post(
        client,
        mk_url,
        makeup_body({"version": row.version}, lesson, start + timedelta(hours=0)),
        "m3",
    )
    assert redo.status_code == 200, redo.data
    assert RecoveryObligation.objects.count() == 1
    assert LessonOccurrence.objects.filter(recovery=row, state="PUBLISHED").count() == 1


def test_partial_group_recovery(center):
    lesson = cancelled(center)
    student = lesson.participants.values_list("student_id", flat=True).first()
    body = recovery_body(lesson, participant_ids=[str(student)])
    obligation = post(
        center[2], f"/api/v1/occurrences/{lesson.id}/recovery/", body, "r1"
    ).data
    assert obligation["participants"] == [str(student)]
    made = post(
        center[2],
        f"/api/v1/recovery-obligations/{obligation['id']}/makeup/",
        makeup_body(obligation, lesson, lesson.start_at + timedelta(days=7)),
        "m1",
    )
    assert made.status_code == 200, made.data
    makeup = LessonOccurrence.objects.get(pk=made.data["lesson"]["id"])
    assert list(makeup.participants.values_list("student_id", flat=True)) == [student]


@pytest.mark.parametrize(
    "extra,code",
    [
        (
            {"participant_ids": ["00000000-0000-0000-0000-000000000001"]},
            "RECOVERY_PARTICIPANTS_INVALID",
        ),
        ({"minutes": 75}, "RECOVERY_MINUTES_INVALID"),
        ({"minutes": 90}, "RECOVERY_MINUTES_INVALID"),
    ],
)
def test_invalid_recovery_requests(center, extra, code):
    lesson = cancelled(center)
    response = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/recovery/",
        recovery_body(lesson, **extra),
        "bad",
    )
    assert response.data["code"] == code and not RecoveryObligation.objects.exists()


def test_published_lesson_is_not_a_recovery_origin(center):
    publish(center)
    lesson = week_lessons(WEEK).first()
    response = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/recovery/",
        recovery_body(lesson),
        "bad",
    )
    assert response.data["code"] == "RECOVERY_ORIGIN_INVALID"


def test_waive_open_obligation(center):
    lesson = cancelled(center)
    obligation = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/recovery/",
        recovery_body(lesson),
        "r1",
    ).data
    url = f"/api/v1/recovery-obligations/{obligation['id']}/waive/"
    body = {"expected_version": 1, "reason": "Famiglia rinuncia"}
    waived = post(center[2], url, body, "w1")
    assert waived.status_code == 200 and waived.data["state"] == "WAIVED"
    assert post(center[2], url, body, "w1").data == waived.data
    assert (
        post(center[2], url, {**body, "expected_version": 2}, "w2").data["code"]
        == "RECOVERY_NOT_OPEN"
    )
    listed = center[2].get("/api/v1/recovery-obligations/?state=WAIVED").data
    assert [r["id"] for r in listed["results"]] == [obligation["id"]]
    assert OutboxEvent.objects.filter(event_type="recovery.waived").exists()
