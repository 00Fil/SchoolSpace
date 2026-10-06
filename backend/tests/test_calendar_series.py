"""GAP-E01 (s2-calendario): LessonSeries, proiezione, EXDATE, override, split (T12–T14)."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.calendar.models import CalendarAudit, LessonOccurrence, LessonSeries
from apps.education.path_services import DomainError
from apps.calendar import series as series_ops
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import WEEK2, add_weekday, post, publish_week, week_lessons

ROME = ZoneInfo("Europe/Rome")


def single_lesson(week=WEEK):
    """Lezione della richiesta 1/settimana (la prima trovata nella settimana)."""
    for lesson in week_lessons(week, state="PUBLISHED").select_related("demand"):
        request = lesson.demand.request
        if request.sessions_per_week == 1:
            return lesson, request
    raise AssertionError("demo senza richiesta 1/settimana")


def body_for(lesson, request, **extra):
    local = lesson.start_at.astimezone(ROME)
    return {
        "request_id": str(request.id),
        "start_date": "2026-10-12",
        "start_time": local.strftime("%H:%M"),
        "rrule": "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261102",
        "tutor_id": str(lesson.tutor_id),
        "mode": lesson.mode,
        "location": lesson.location,
        "space_id": str(lesson.space_id),
        "video_id": None,
        "reason": "Serie sintetica",
        **extra,
    }


def republish(center, week, key):
    """Rigenera e ripubblica: nessuna nuova lezione se tutto è già materializzato."""
    with pytest.raises(DomainError) as error:
        publish_week(center, week, key)
    return error.value.detail["code"]


@pytest.fixture
def seeded(center):
    publish(center)
    lesson, request = single_lesson()
    response = post(
        center[2], "/api/v1/lesson-series/", body_for(lesson, request), "s1"
    )
    assert response.status_code == 200, response.data
    return center, lesson, request, response.data


def test_create_series_idempotent_and_audited(seeded):
    center, lesson, request, data = seeded
    again = post(center[2], "/api/v1/lesson-series/", body_for(lesson, request), "s1")
    assert again.data == data and LessonSeries.objects.count() == 1
    assert CalendarAudit.objects.filter(operation="SERIES_CREATE").count() == 1
    assert data["until_date"] == "2026-11-02" and data["root_id"] == data["id"]
    detail = center[2].get(f"/api/v1/lesson-series/{data['id']}/").data
    assert [o["status"] for o in detail["occurrences"]] == ["PROJECTED"] * 4


@pytest.mark.parametrize(
    "change,code",
    [
        ({"rrule": "FREQ=WEEKLY;BYDAY=MO;COUNT=2;UNTIL=20261102"}, "RRULE_UNSUPPORTED"),
        ({"rrule": "FREQ=WEEKLY;BYDAY=MO"}, "RRULE_UNBOUNDED"),
        ({"rrule": "FREQ=WEEKLY;BYDAY=MO,TU;UNTIL=20261102"}, "SERIES_EXCEEDS_DEMAND"),
        ({"start_date": "2026-10-13"}, "DTSTART_NOT_IN_BYDAY"),
        ({"rrule": "FREQ=WEEKLY;BYDAY=MO;UNTIL=20270801"}, "SERIES_OUTSIDE_REQUEST"),
        ({"mode": "ONLINE", "location": "REMOTE"}, "SERIES_MODE_MISMATCH"),
        ({"space_id": None}, "SPACE_REQUIRED"),
        ({"exdates": ["2026-10-13"]}, "EXDATE_NOT_IN_SERIES"),
    ],
)
def test_create_series_rejections(center, change, code):
    publish(center)
    lesson, request = single_lesson()
    response = post(
        center[2], "/api/v1/lesson-series/", body_for(lesson, request, **change), "bad"
    )
    assert response.status_code == 422 and response.data["code"] == code
    assert LessonSeries.objects.count() == 0


def test_second_series_cannot_duplicate_demand(seeded):
    center, lesson, request, _ = seeded
    body = body_for(lesson, request, start_date="2026-10-19")
    response = post(center[2], "/api/v1/lesson-series/", body, "s2")
    assert response.data["code"] == "SERIES_EXCEEDS_DEMAND"


def test_projection_publish_links_and_rerun_has_no_duplicates(seeded):
    """T13: rigenerare/ripubblicare non duplica le occorrenze della serie."""
    center, lesson, request, data = seeded
    publish_week(center, WEEK2, "p2")
    linked = LessonOccurrence.objects.get(series_id=data["id"])
    assert linked.recurrence_key == f"series:{data['id']}/2026-10-12"
    local = lesson.start_at.astimezone(ROME).time()
    assert linked.start_at.astimezone(ROME).time() == local
    assert (linked.tutor_id, linked.space_id) == (lesson.tutor_id, lesson.space_id)
    count = week_lessons(WEEK2).count()
    assert republish(center, WEEK2, "p3") == "NO_NEW_ASSIGNMENTS"
    assert week_lessons(WEEK2).count() == count == 6
    assert LessonOccurrence.objects.filter(series_id=data["id"]).count() == 1
    detail = center[2].get(f"/api/v1/lesson-series/{data['id']}/").data
    assert detail["occurrences"][0]["status"] == "MATERIALIZED"


def test_exdate_cancels_materialized_and_skips_projection(seeded):
    center, _, _, data = seeded
    publish_week(center, WEEK2, "p2")
    url = f"/api/v1/lesson-series/{data['id']}/exdate/"
    body = {"expected_version": 1, "date": "2026-10-12", "reason": "Festa"}
    response = post(center[2], url, body, "x1")
    assert response.status_code == 200, response.data
    cancelled = LessonOccurrence.objects.get(pk=response.data["cancelled_lesson_id"])
    assert cancelled.state == "CANCELLED" and not cancelled.bookings.exists()
    assert post(center[2], url, body, "x1").data == response.data
    body2 = {**body, "expected_version": 2, "date": "2026-10-19"}
    second = post(center[2], url, body2, "x2")
    assert second.data["exdates"] == ["2026-10-12", "2026-10-19"]
    publish_week(center, date(2026, 10, 19), "p4")
    assert not LessonOccurrence.objects.filter(
        recurrence_key=f"series:{data['id']}/2026-10-19"
    ).exists()
    stale = post(center[2], url, {**body, "date": "2026-10-26"}, "x3")
    assert stale.status_code == 409


def test_override_only_this_unmaterialized(seeded):
    center, lesson, _, data = seeded
    url = f"/api/v1/lesson-series/{data['id']}/override/"
    local = lesson.start_at.astimezone(ROME)
    body = {
        "expected_version": 1,
        "date": "2026-10-26",
        "local_start": f"2026-10-26T{local.hour:02d}:{local.minute:02d}",
        "reason": "Solo questa",
    }
    wrong = post(center[2], url, {**body, "local_start": "2026-11-03T10:00"}, "o0")
    assert wrong.data["code"] == "OVERRIDE_INVALID"
    response = post(center[2], url, body, "o1")
    assert response.status_code == 200, response.data
    occ = center[2].get(f"/api/v1/lesson-series/{data['id']}/").data["occurrences"]
    days = ("10-12", "10-19", "10-26", "11-02")
    assert [o["key"] for o in occ] == [f"series:{data['id']}/2026-{d}" for d in days]
    assert [o["overridden"] for o in occ] == [False, False, True, False]
    publish_week(center, WEEK2, "p2")
    again = {
        **body,
        "expected_version": 2,
        "date": "2026-10-12",
        "local_start": "2026-10-12T11:00",
    }
    assert post(center[2], url, again, "o2").data["code"] == "OCCURRENCE_MATERIALIZED"


def test_split_this_and_following_t14(seeded):
    """T14: da un'istanza in poi il giorno cambia; le passate restano, chiavi stabili."""
    center, lesson, _, data = seeded
    publish_week(center, WEEK2, "p2")
    add_weekday(1)
    first = LessonOccurrence.objects.get(series_id=data["id"])
    url = f"/api/v1/lesson-series/{data['id']}/split/"
    body = {
        "expected_version": 1,
        "from_date": "2026-10-12",
        "changes": {"rrule": "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261103"},
        "reason": "Cambio giorno",
    }
    response = post(center[2], url, body, "sp1")
    assert response.status_code == 200, response.data
    assert response.data["closed"]["state"] == "CLOSED"
    nxt = response.data["next"]
    assert nxt["root_id"] == data["id"] and nxt["start_date"] == "2026-10-13"
    assert nxt["carried"] == {"2026-10-13": f"series:{data['id']}/2026-10-12"}
    first.refresh_from_db()
    assert str(first.series_id) == nxt["id"]
    assert first.start_at.astimezone(ROME).date() == date(2026, 10, 13)
    assert first.recurrence_key == f"series:{data['id']}/2026-10-12"
    assert first.bookings.count() == lesson.bookings.count()
    count = week_lessons(WEEK2).count()
    assert republish(center, WEEK2, "p3") == "NO_NEW_ASSIGNMENTS"
    assert week_lessons(WEEK2).count() == count  # nessun duplicato del 13
    publish_week(center, date(2026, 10, 19), "p4")
    moved = LessonOccurrence.objects.get(
        recurrence_key=f"series:{data['id']}/2026-10-20"
    )
    assert moved.start_at.astimezone(ROME).weekday() == 1
    assert post(center[2], url, body, "sp1").data == response.data
    closed = post(center[2], url, {**body, "expected_version": 2}, "sp2")
    assert closed.data["code"] == "SERIES_CLOSED"


def test_split_requires_changes(seeded):
    center, _, _, data = seeded
    with pytest.raises(DomainError) as error:
        series_ops.split_series(
            center[0],
            data["id"],
            {
                "expected_version": 1,
                "from_date": date(2026, 10, 19),
                "changes": {},
                "reason": "x",
            },
            "sp-x",
        )
    assert error.value.detail["code"] == "NO_CHANGES"


def test_series_dst_keeps_local_time(seeded):
    """La serie attraversa il cambio d'ora del 25/10: ora locale invariata, UTC +1."""
    center, _, _, data = seeded
    occ = center[2].get(f"/api/v1/lesson-series/{data['id']}/").data["occurrences"]
    hours = {o["nominal_date"]: int(o["start_at"][11:13]) for o in occ}
    assert hours["2026-10-26"] - hours["2026-10-19"] == 1


def test_series_commands_center_only(seeded):
    center, lesson, request, _ = seeded
    client = APIClient()
    client.force_authenticate(
        Account.objects.create_user(username="fam", email="fam@example.invalid")
    )
    assert client.get("/api/v1/lesson-series/").status_code == 403
    body = body_for(lesson, request)
    assert post(client, "/api/v1/lesson-series/", body, "f").status_code == 403
    bad = post(center[2], "/api/v1/lesson-series/", {**body, "x": 1}, "y")
    assert bad.status_code == 400 and LessonSeries.objects.count() == 1


def test_series_link_existing_lesson(center):
    """Una lezione pubblicata può diventare la prima istanza di una serie."""
    publish(center)
    publish_week(center, WEEK2, "p2")
    lesson, request = single_lesson(WEEK2)
    body = body_for(lesson, request, origin_lesson_id=str(lesson.id))
    response = post(center[2], "/api/v1/lesson-series/", body, "link")
    assert response.status_code == 200, response.data
    lesson.refresh_from_db()
    assert response.data["linked_lesson_id"] == str(lesson.id)
    assert lesson.recurrence_key == f"series:{response.data['id']}/2026-10-12"
    assert republish(center, WEEK2, "p3") == "NO_NEW_ASSIGNMENTS"
    assert LessonOccurrence.objects.filter(series_id=response.data["id"]).count() == 1
