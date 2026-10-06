"""GAP-E02 (s2-calendario): spostamento tra settimane, modifica, scambio atomico."""

from datetime import timedelta

import pytest
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.calendar.models import CalendarAudit, LessonOccurrence, ResourceBooking
from apps.communications.models import OutboxEvent
from apps.education.models import Resource
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import WEEK2, post, publish_week, week_lessons


def lessons():
    return list(week_lessons(WEEK, state="PUBLISHED"))


def move_body(lesson, start_at, **extra):
    return {
        "expected_version": lesson.version,
        "start_at": start_at.isoformat(),
        "reason": "Spostamento sintetico",
        **extra,
    }


def test_cross_week_move_keeps_identity_and_survives_next_publish(center):
    publish(center)
    lesson = lessons()[0]
    bookings = lesson.bookings.count()
    target = lesson.start_at + timedelta(days=7)
    url = f"/api/v1/occurrences/{lesson.id}/move/"
    response = post(center[2], url, move_body(lesson, target), "mv1")
    assert response.status_code == 200, response.data
    assert post(center[2], url, move_body(lesson, target), "mv1").data == response.data
    lesson.refresh_from_db()
    assert lesson.start_at == target and lesson.version == 2
    assert lesson.bookings.count() == bookings
    assert CalendarAudit.objects.filter(lesson=lesson, operation="MOVE").count() == 1
    assert OutboxEvent.objects.filter(
        event_type="lesson.rescheduled", subject_ref=f"lesson:{lesson.id}"
    ).exists()
    # La settimana di arrivo si pianifica attorno alla lezione spostata, senza
    # duplicare la domanda della settimana d'origine.
    publish_week(center, WEEK2, "p2")
    lesson.refresh_from_db()
    assert lesson.start_at == target and lesson.state == "PUBLISHED"
    week2 = week_lessons(WEEK2, state="PUBLISHED")
    assert week2.count() == 7
    assert week2.filter(demand=lesson.demand).count() == 1
    # La settimana d'origine ha una sola unità scoperta (quella spostata).
    assert week_lessons(WEEK, state="PUBLISHED").count() == 5


def test_cross_week_move_rejected_outside_availability(center):
    publish(center)
    lesson = lessons()[0]
    target = lesson.start_at + timedelta(days=8)  # martedì: nessuna disponibilità
    url = f"/api/v1/occurrences/{lesson.id}/move/"
    response = post(center[2], url, move_body(lesson, target), "mv2")
    assert response.status_code == 422
    assert response.data["code"] == "CALENDAR_VALIDATION_FAILED"
    lesson.refresh_from_db()
    assert lesson.version == 1 and lesson.start_at != target


def test_modify_tutor_and_space(center):
    publish(center)
    items = lessons()
    # Il piano dipende dagli obiettivi del solver: si cerca, in ordine deterministico,
    # una lezione, un altro tutor del piano e un'aula libera nell'intervallo per cui la
    # modifica sia valida. Ogni rifiuto deve lasciare la lezione invariata.
    spaces = list(Resource.objects.filter(kind="SPACE").order_by("id"))
    candidates = []
    for first in items:
        busy = {
            other.space_id
            for other in items
            if other.start_at < first.end_at and first.start_at < other.end_at
        }
        tutors = sorted({o.tutor_id for o in items if o.tutor_id != first.tutor_id})
        for tutor_id in tutors:
            for space in spaces:
                if space.id not in busy:
                    candidates.append((first, tutor_id, space))
    assert candidates
    response = None
    for n, (first, tutor_id, free_space) in enumerate(candidates):
        url = f"/api/v1/occurrences/{first.id}/modify/"
        body = {
            "expected_version": 1,
            "changes": {"tutor_id": str(tutor_id), "space_id": str(free_space.id)},
            "reason": "Cambio tutor e aula",
        }
        response = post(center[2], url, body, f"md1-{n}")
        if response.status_code == 200:
            break
        assert response.status_code == 422, response.data
        first.refresh_from_db()
        assert first.version == 1
    assert response is not None and response.status_code == 200, response.data
    first.refresh_from_db()
    assert (first.tutor_id, first.space_id) == (tutor_id, free_space.id)
    assert ResourceBooking.objects.filter(
        lesson=first, resource__resource=free_space
    ).exists()
    noop = post(center[2], url, {**body, "expected_version": 2}, "md2")
    assert noop.data["code"] == "NO_CHANGES"


def test_modify_mode_not_allowed_by_request(center):
    publish(center)
    lesson = lessons()[0]
    body = {
        "expected_version": 1,
        "changes": {"mode": "ONLINE", "location": "REMOTE", "space_id": None},
        "reason": "Online",
    }
    response = post(center[2], f"/api/v1/occurrences/{lesson.id}/modify/", body, "md3")
    assert response.status_code == 422
    lesson.refresh_from_db()
    assert lesson.mode == "IN_PERSON" and lesson.version == 1


def test_swap_is_atomic(center):
    publish(center)
    items = lessons()
    # Il piano dipende dagli obiettivi del solver: si cerca, in ordine deterministico,
    # una coppia di pari durata il cui scambio sia valido. Ogni rifiuto deve essere
    # atomico (nessuna delle due lezioni cambia versione).
    pairs = [
        (a, b)
        for i, a in enumerate(items)
        for b in items[i + 1 :]
        if a.end_at - a.start_at == b.end_at - b.start_at and a.start_at != b.start_at
    ]
    response = None
    for n, (first, second) in enumerate(pairs):
        body = {
            "first_id": str(first.id),
            "first_version": 1,
            "second_id": str(second.id),
            "second_version": 1,
            "reason": "Scambio",
        }
        response = post(center[2], "/api/v1/occurrences/swap/", body, f"sw1-{n}")
        if response.status_code == 200:
            break
        assert response.status_code == 422, response.data
        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.version, second.version) == (1, 1)
    assert response is not None and response.status_code == 200, response.data
    a, b = first.start_at, second.start_at
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.start_at, second.start_at) == (b, a)
    assert CalendarAudit.objects.filter(operation="SWAP").count() == 2


def test_swap_rollback_on_conflict(center):
    publish(center)
    items = lessons()
    first, second = items[0], items[1]  # stesso tutor: scambio valido o rifiuto atomico
    body = {
        "first_id": str(first.id),
        "first_version": 1,
        "second_id": str(second.id),
        "second_version": 2,  # versione obsoleta
        "reason": "Scambio",
    }
    response = post(center[2], "/api/v1/occurrences/swap/", body, "sw2")
    assert response.status_code == 409
    same = post(
        center[2],
        "/api/v1/occurrences/swap/",
        {**body, "second_id": str(first.id), "second_version": 1},
        "sw3",
    )
    assert same.data["code"] == "SWAP_SAME_LESSON"
    assert all(
        l.version == 1
        for l in LessonOccurrence.objects.filter(pk__in=[first.id, second.id])
    )
    assert not CalendarAudit.objects.filter(operation="SWAP").exists()


@pytest.mark.parametrize("path", ["move", "modify"])
def test_closed_body_and_family_forbidden(center, path):
    publish(center)
    lesson = lessons()[0]
    url = f"/api/v1/occurrences/{lesson.id}/{path}/"
    bad = post(center[2], url, {"expected_version": 1, "reason": "x", "extra": 1}, "c1")
    assert bad.status_code == 400
    family = APIClient()
    family.force_authenticate(
        Account.objects.create_user(username="fam", email="fam@example.invalid")
    )
    body = move_body(lesson, lesson.start_at + timedelta(days=7))
    assert post(family, url, body, "c2").status_code == 403
    lesson.refresh_from_db()
    assert lesson.version == 1
