"""Protezioni PostgreSQL s2-calendario (migrazione 0005): trigger estesi e append-only.

Saltati su SQLite, come i test GiST/trigger esistenti in tests/test_calendar.py."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction, DatabaseError
from apps.calendar.models import (
    AttendanceRevision,
    CalendarAudit,
    LessonOccurrence,
    LessonParticipant,
)
from apps.calendar.services import change_lesson
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import post, set_now, week_lessons
from tests.test_calendar_recovery import makeup_body, recovery_body
from tests.test_calendar_attendance import entries

pg_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires actual PostgreSQL triggers (migration 0005)",
)


def scheduled_makeup(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    change_lesson(
        center[0], lesson.id, "cancel", {"expected_version": 1, "reason": "x"}, "c"
    )
    lesson.refresh_from_db()
    student = lesson.participants.values_list("student_id", flat=True).first()
    obligation = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/recovery/",
        recovery_body(lesson, participant_ids=[str(student)]),
        "r",
    ).data
    made = post(
        center[2],
        f"/api/v1/recovery-obligations/{obligation['id']}/makeup/",
        makeup_body(obligation, lesson, lesson.start_at + timedelta(days=7)),
        "m",
    )
    assert made.status_code == 200, made.data
    return lesson, LessonOccurrence.objects.get(pk=made.data["lesson"]["id"])


@pg_only
def test_trigger_rejects_makeup_participant_outside_obligation(center):
    origin, makeup = scheduled_makeup(center)
    outsider = (
        origin.participants.exclude(
            student_id__in=makeup.participants.values("student_id")
        )
        .values_list("student_id", flat=True)
        .first()
    )
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            LessonParticipant.objects.create(lesson=makeup, student_id=outsider)
    assert error.value.__cause__.sqlstate == "23514"


@pg_only
def test_trigger_rejects_makeup_duration_change(center):
    _, makeup = scheduled_makeup(center)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LessonOccurrence.objects.filter(pk=makeup.pk).update(
                end_at=makeup.end_at + timedelta(minutes=30)
            )


@pg_only
def test_completed_lesson_is_immutable(center, monkeypatch):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    set_now(monkeypatch, lesson.end_at + timedelta(minutes=5))
    url = f"/api/v1/occurrences/{lesson.id}/attendance/"
    rows = entries(lesson, "PRESENT", "PRESENT")
    post(center[2], url, {"expected_version": 1, "entries": rows}, "a")
    done = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/complete/",
        {"expected_version": 1},
        "c",
    )
    assert done.status_code == 200, done.data
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LessonOccurrence.objects.filter(pk=lesson.pk).update(
                start_at=lesson.start_at + timedelta(minutes=30),
                end_at=lesson.end_at + timedelta(minutes=30),
            )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LessonOccurrence.objects.filter(pk=lesson.pk).update(state="PUBLISHED")


@pg_only
def test_audit_and_revisions_append_only_in_database(center, monkeypatch):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    set_now(monkeypatch, lesson.end_at + timedelta(minutes=5))
    post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/attendance/",
        {"expected_version": 1, "entries": entries(lesson, "PRESENT", "ABSENT")},
        "a",
    )
    for table in (
        CalendarAudit._meta.db_table,
        AttendanceRevision._meta.db_table,
    ):
        for sql in (f"UPDATE {table} SET reason = 'x'", f"DELETE FROM {table}"):
            with pytest.raises(DatabaseError):
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql)
    assert CalendarAudit.objects.exists() and AttendanceRevision.objects.count() == 2
