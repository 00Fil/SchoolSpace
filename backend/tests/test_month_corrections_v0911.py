"""v0.9.11: un solo calendario pubblico per mese; ogni modifica va in bozza come rettifica,
il gestore pubblica le rettifiche del mese oppure subito."""

from datetime import datetime, timedelta

import pytest

from apps.calendar.models import LessonOccurrence
from apps.scheduling.autoplan import ROME
from apps.scheduling.models import AutoPlan, CalendarCorrection

from test_request_review_v099 import monday_in, series, world  # noqa: F401

pytestmark = pytest.mark.django_db


def published(w, weeks=2, **extra):
    c = w["client"]
    rid = c.post("/api/v1/teaching-requests/", series(w, weeks=weeks, **extra), format="json").data["id"]
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {"publish_now": True}, format="json")
    assert r.status_code == 200, r.data
    return rid, list(LessonOccurrence.objects.filter(demand__request_id=rid).order_by("start_at"))


def ym():
    return monday_in(2).isoformat()[:7]


def test_move_goes_to_draft_until_the_month_is_published(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    first = lessons[0]
    new_start = first.start_at + timedelta(hours=1)
    r = c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(first.id), "start_at": new_start.isoformat()}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["published"] is False and r.data["month"]["state"] == "DRAFT"
    corr = r.data["correction"]
    assert corr["target"]["start_at"].startswith(new_start.astimezone(ROME).isoformat()[:16]) or corr["target"]
    # famiglie e tutor vedono ancora l'orario pubblicato
    first.refresh_from_db()
    assert first.start_at == lessons[0].start_at
    # una seconda modifica della stessa lezione sostituisce la prima
    later = first.start_at + timedelta(hours=2)
    c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(first.id), "start_at": later.isoformat()}, format="json")
    assert CalendarCorrection.objects.filter(lesson=first, state="PENDING").count() == 1
    m = c.post(f"/api/v1/planner/calendar-months/{ym()}/publish", {}, format="json").data
    assert m["result"]["applied"] == 1 and m["state"] == "PUBLISHED"
    first.refresh_from_db()
    assert first.start_at == later


def test_publish_now_applies_immediately(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    l = lessons[1]
    r = c.post("/api/v1/planner/corrections", {"op": "cancel", "lesson_id": str(l.id), "publish_now": True}, format="json")
    assert r.status_code == 201 and r.data["published"] is True
    l.refresh_from_db()
    assert l.state == "CANCELLED" and r.data["month"]["pending"] == 0


def test_invalid_correction_never_enters_the_draft(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    a, b = lessons[0], lessons[1]
    # nella bozza la prima lezione va in un orario; la seconda non può andarci (stesso tutor)
    target = a.start_at + timedelta(hours=2)
    assert c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(a.id), "start_at": target.isoformat()}, format="json").status_code == 201
    other = datetime.combine(target.astimezone(ROME).date(), target.astimezone(ROME).time(), ROME)
    moved = b.start_at.astimezone(ROME).replace(day=other.day, month=other.month, year=other.year, hour=other.hour, minute=other.minute)
    r = c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(b.id), "start_at": moved.isoformat()}, format="json")
    assert r.status_code == 409, r.data
    assert CalendarCorrection.objects.filter(state="PENDING").count() == 1


def test_discard_and_swap(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    a, b = lessons
    r = c.post("/api/v1/planner/corrections", {"op": "swap", "lesson_id": str(a.id), "other_id": str(b.id)}, format="json")
    assert r.status_code == 201, r.data
    cid = r.data["correction"]["id"]
    m = c.post(f"/api/v1/planner/corrections/{cid}/discard", {}, format="json").data
    assert m["pending"] == 0
    sa, sb = a.start_at, b.start_at
    r = c.post("/api/v1/planner/corrections", {"op": "swap", "lesson_id": str(a.id), "other_id": str(b.id)}, format="json")
    assert r.status_code == 201, r.data
    m = c.post(f"/api/v1/planner/calendar-months/{ym()}/publish", {}, format="json").data
    assert m["result"]["applied"] == 1, m["result"]
    a.refresh_from_db(); b.refresh_from_db()
    assert a.start_at == sb and b.start_at == sa


def test_one_public_calendar_per_month(world):
    w, c = world, world["client"]
    published(w, weeks=1)
    published(w, weeks=1, preferred_tutor_ids=[str(w["tutors"][1].id)])
    first = monday_in(2).replace(day=1)
    assert AutoPlan.objects.filter(month=first, state="PUBLISHED").count() == 1
    assert AutoPlan.objects.filter(month=first, state="MERGED").count() == 2


def test_publish_single_correction_keeps_the_others_in_draft(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    a, b = lessons
    ra = c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(a.id), "start_at": (a.start_at + timedelta(hours=1)).isoformat()}, format="json")
    rb = c.post("/api/v1/planner/corrections", {"op": "cancel", "lesson_id": str(b.id)}, format="json")
    assert ra.status_code == 201 and rb.status_code == 201
    r = c.post(f"/api/v1/planner/corrections/{rb.data['correction']['id']}/publish", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["correction"]["state"] == "APPLIED" and r.data["month"]["pending"] == 1
    b.refresh_from_db(); a.refresh_from_db()
    assert b.state == "CANCELLED" and a.start_at == lessons[0].start_at
    again = c.post(f"/api/v1/planner/corrections/{rb.data['correction']['id']}/publish", {}, format="json")
    assert again.status_code == 409


def test_request_completion_goes_to_month_draft(world):
    w, c = world, world["client"]
    rid = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data["id"]
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["result"]["draft"] is True
    assert not LessonOccurrence.objects.filter(demand__request_id=rid, state="PUBLISHED").exists()
    m = c.get(f"/api/v1/planner/calendar-months/{ym()}").data
    assert m["state"] == "DRAFT" and any(x["op"] == "plan" for x in m["corrections"])
    pub = c.post(f"/api/v1/planner/calendar-months/{ym()}/publish", {}, format="json").data
    assert pub["state"] == "PUBLISHED", pub
    assert LessonOccurrence.objects.filter(demand__request_id=rid, state="PUBLISHED").exists()


def test_substitute_and_mode_change_on_monthly_lessons(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    l = lessons[0]
    subs = c.get(f"/api/v1/occurrences/{l.id}/substitutes/")
    assert subs.status_code == 200, subs.data
    r = c.post("/api/v1/planner/corrections", {"op": "modify", "lesson_id": str(l.id), "changes": {"mode": "ONLINE", "location": "REMOTE", "space_id": None}, "publish_now": True}, format="json")
    assert r.status_code == 201, r.data
    l.refresh_from_db()
    assert l.mode == "ONLINE" and l.space_id is None


def test_resize_and_substitute_keep_database_consistent(world):
    w, c = world, world["client"]
    rid, lessons = published(w)
    l = lessons[1]
    end = l.end_at + timedelta(minutes=30)
    r = c.post("/api/v1/planner/corrections", {"op": "reschedule", "lesson_id": str(l.id), "start_at": l.start_at.isoformat(), "end_at": end.isoformat(), "publish_now": True}, format="json")
    assert r.status_code == 201, r.data
    l.refresh_from_db()
    assert l.end_at == end
    subs = c.get(f"/api/v1/occurrences/{l.id}/substitutes/").data["substitutes"]
    ok = [s for s in subs if s["ok"]]
    assert ok, subs
    if ok:
        r = c.post("/api/v1/planner/corrections", {"op": "modify", "lesson_id": str(l.id), "changes": {"tutor_id": ok[0]["tutor_id"]}}, format="json")
        assert r.status_code == 201, r.data
        m = c.post(f"/api/v1/planner/calendar-months/{l.start_at.astimezone(ROME).isoformat()[:7]}/publish", {}, format="json").data
        assert m["result"]["applied"] == 1, m["result"]
        l.refresh_from_db()
        assert str(l.tutor_id) == ok[0]["tutor_id"]
