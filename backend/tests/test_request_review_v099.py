"""v0.9.9: ricalcolo automatico del motore a ogni richiesta inserita/approvata, verifica
delle lezioni proposte (elenco + incongruenze) prima del completamento, lezioni di gruppo."""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.calendar.models import LessonOccurrence
from apps.education.models import (
    Family,
    GuardianLink,
    Resource,
    Student,
    Subject,
    TeachingRequest,
    Tutor,
)
from apps.identity.models import Account, RoleGrant
from apps.scheduling.autoplan import ROME
from apps.scheduling.models import (
    AutoPlan,
    AutoPlanLesson,
    Commitment,
    OpeningHours,
    TutorSkill,
)

pytestmark = pytest.mark.django_db


def monday_in(weeks):
    """Lunedì della settimana ``weeks - 2`` a partire dal primo lunedì di un mese futuro:
    le serie dei test (≤ 3 settimane) restano nello stesso mese, su cui lavora il motore."""
    today = timezone.now().astimezone(ROME).date()
    first = date(today.year + (today.month + 1) // 12, (today.month + 1) % 12 + 1, 1)
    base = first + timedelta(days=(7 - first.weekday()) % 7)
    return base + timedelta(weeks=weeks - 2)


@pytest.fixture
def world(settings):
    settings.AUTOPLAN_REQUEST_TIME_LIMIT_SECONDS = 4
    settings.AUTOPLAN_WORKERS = 4
    center = Account.objects.create_superuser(
        username="rv-center",
        email="rv-center@example.invalid",
        password="x-Test-pass-1",
    )
    client = APIClient()
    client.force_authenticate(center)
    family = Family.objects.create(reference="RV-FAM")
    students = [
        Student.objects.create(display_name=f"Studente {n}", family=family)
        for n in "ABC"
    ]
    tutors = [Tutor.objects.create(display_name=f"Tutor {n}") for n in "XY"]
    subject = Subject.objects.create(name="Fisica RV")
    for t in tutors:
        TutorSkill.objects.create(
            tutor=t,
            subject=subject,
            level="",
            mode="IN_PERSON",
            valid_from=date(2026, 1, 1),
            valid_until=date(2030, 6, 30),
            approved=True,
        )
    Resource.objects.create(name="Aula RV", kind="SPACE", student_capacity=6)
    for wd in range(5):
        OpeningHours.objects.create(weekday=wd, start_time=time(15), end_time=time(19))
    return {
        "center": center,
        "client": client,
        "students": students,
        "tutors": tutors,
        "subject": subject,
    }


def series(w, weeks=3, **extra):
    start = monday_in(2)
    body = {
        "student": str(w["students"][0].id),
        "subject": str(w["subject"].id),
        "kind": "SERIES",
        "mode": "IN_PERSON",
        "duration_minutes": 60,
        "sessions_per_week": 1,
        "period_start": start.isoformat(),
        "period_end": (start + timedelta(days=7 * weeks - 1)).isoformat(),
        "preferred_tutor_ids": [str(w["tutors"][0].id)],
    }
    body.update(extra)
    return body


def test_center_request_triggers_engine_and_needs_review(world):
    w, c = world, world["client"]
    r = c.post("/api/v1/teaching-requests/", series(w), format="json")
    assert r.status_code == 201, r.data
    assert r.data["status"] == "APPROVED" and r.data["planning_state"] == "REVIEW"
    rid = r.data["id"]
    plan = AutoPlan.objects.get(request_id=rid, state="DRAFT")
    assert plan.lessons.count() == 3
    # la verifica elenca le lezioni e nessuna incongruenza
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert (
        len(v["lessons"]) == 3
        and v["missing"] == 0
        and v["conflicts"] == 0
        and v["can_complete"]
    )
    assert {l["tutor"]["id"] for l in v["lessons"]} == {str(w["tutors"][0].id)}
    # il calendario mensile non ripianifica una richiesta in verifica
    from apps.scheduling import autoplan

    month = autoplan.plan_month(monday_in(2), w["center"])
    assert not month.lessons.filter(request_id=rid).exists()
    # conferma: la richiesta è completata e le lezioni entrano nella bozza del mese
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["planning_state"] == "DONE" and r.data["result"]["draft"] is True
    assert LessonOccurrence.objects.filter(demand__request_id=rid).count() == 0
    assert TeachingRequest.objects.get(pk=rid).completed_at is not None
    ym = monday_in(2).isoformat()[:7]
    m = c.get(f"/api/v1/planner/calendar-months/{ym}").data
    assert m["state"] == "DRAFT" and m["pending"] == 1 and len(m["corrections"][0]["lessons"]) == 3
    # il gestore pubblica le rettifiche del mese: lezioni in calendario, un solo calendario pubblico
    m = c.post(f"/api/v1/planner/calendar-months/{ym}/publish", {}, format="json").data
    assert m["result"]["applied"] == 1 and not m["result"]["failed"], m["result"]
    assert LessonOccurrence.objects.filter(demand__request_id=rid).count() == 3
    assert m["state"] == "PUBLISHED" and m["pending"] == 0
    assert AutoPlan.objects.filter(month=monday_in(2).replace(day=1), state="PUBLISHED").count() == 1


def test_family_request_planned_on_approval_and_cancelled_on_reject(world):
    w = world
    s = w["students"][0]
    guardian = Account.objects.create_user(
        username="rv-guardian", email="rv-g@example.invalid"
    )
    RoleGrant.objects.create(
        account=guardian, role="GUARDIAN", valid_from=timezone.now() - timedelta(days=1)
    )
    GuardianLink.objects.create(
        account=guardian,
        student=s,
        verified=True,
        can_view=True,
        can_manage_availability=True,
        valid_from=timezone.now() - timedelta(days=1),
    )
    fam = APIClient()
    fam.force_authenticate(guardian)
    day = monday_in(2) + timedelta(days=1)
    r = fam.post(
        "/api/v1/teaching-requests/",
        {
            "student": str(s.id),
            "subject": str(w["subject"].id),
            "kind": "SINGLE",
            "mode": "IN_PERSON",
            "duration_minutes": 60,
            "period_start": day.isoformat(),
        },
        format="json",
    )
    assert (
        r.status_code == 201
        and r.data["status"] == "PENDING"
        and r.data["planning_state"] == ""
    )
    rid = r.data["id"]
    assert not AutoPlan.objects.filter(request_id=rid).exists()
    r = w["client"].post(f"/api/v1/teaching-requests/{rid}/approve/", {}, format="json")
    assert r.data["planning_state"] == "REVIEW"
    assert (
        AutoPlanLesson.objects.filter(plan__request_id=rid, state="PROPOSED").count()
        == 1
    )
    r = w["client"].post(f"/api/v1/teaching-requests/{rid}/reject/", {}, format="json")
    assert r.data["planning_state"] == ""
    assert not AutoPlanLesson.objects.filter(
        plan__request_id=rid, state="PROPOSED"
    ).exists()


def test_missing_lessons_must_be_handled_before_completion(world):
    w, c = world, world["client"]
    # il tutor ha impegni che coprono tutta la seconda settimana
    second = monday_in(3)
    for wd in range(5):
        Commitment.objects.create(
            tutor=w["tutors"][0],
            kind="ONE_OFF",
            date=second + timedelta(days=wd),
            start_time=time(14),
            end_time=time(20),
            label="Esami",
        )
    r = c.post("/api/v1/teaching-requests/", series(w), format="json")
    rid = r.data["id"]
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert len(v["lessons"]) == 2 and v["missing"] == 1
    miss = [i for i in v["issues"] if i["kind"] == "MISSING"]
    assert (
        miss
        and miss[0]["weeks"] == [second.isoformat()]
        and miss[0]["reason"] == "TUTOR_BUSY"
    )
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {}, format="json")
    assert r.status_code == 409 and r.data["code"] == "MISSING_LESSONS"
    # gli orari liberi della settimana scoperta non esistono con quel tutor: si sposta il periodo
    opts = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/options",
        {
            "date_from": second.isoformat(),
            "date_to": (second + timedelta(days=6)).isoformat(),
        },
        format="json",
    ).data
    assert opts["options"] == []
    # togliere una lezione la rimette tra le mancanti; poi la si aggiunge a mano in un altro orario
    lesson = v["lessons"][0]
    v = c.post(
        f"/api/v1/planner/request-lessons/{lesson['id']}/remove", {}, format="json"
    ).data
    assert v["missing"] == 2 and len(v["lessons"]) == 1
    day = datetime.fromisoformat(lesson["start_at"]).astimezone(ROME).date()
    opts = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/options",
        {"date_from": day.isoformat(), "date_to": day.isoformat()},
        format="json",
    ).data
    assert opts["options"]
    pick = opts["options"][0]
    r = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/lessons",
        {"start_at": pick["start_at"], "tutor_id": pick["tutor_id"]},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["missing"] == 1 and len(r.data["lessons"]) == 2
    r = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/complete",
        {"accept_missing": True},
        format="json",
    )
    assert r.status_code == 200 and r.data["planning_state"] == "DONE"


def test_conflict_appearing_later_blocks_completion_until_moved(world):
    w, c = world, world["client"]
    rid = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data[
        "id"
    ]
    lesson = AutoPlanLesson.objects.get(plan__request_id=rid, state="PROPOSED")
    local = lesson.start_at.astimezone(ROME)
    # nel frattempo lo studente inserisce un impegno proprio in quell'orario
    Commitment.objects.create(
        student=w["students"][0],
        kind="ONE_OFF",
        date=local.date(),
        start_time=local.time(),
        end_time=(local + timedelta(hours=1)).time(),
        label="Dentista",
    )
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert v["conflicts"] == 1 and not v["can_complete"]
    assert v["issues"][0]["kind"] == "CONFLICT"
    r = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/complete",
        {"accept_missing": True},
        format="json",
    )
    assert r.status_code == 409 and r.data["code"] == "UNRESOLVED_CONFLICTS"
    # spostamento su un orario non libero: rifiutato
    r = c.post(
        f"/api/v1/planner/request-lessons/{lesson.id}/move",
        {"start_at": lesson.start_at.isoformat()},
        format="json",
    )
    assert r.status_code == 409 and r.data["code"] == "SLOT_NOT_FREE"
    opts = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/options",
        {
            "lesson_id": str(lesson.id),
            "date_from": local.date().isoformat(),
            "date_to": local.date().isoformat(),
        },
        format="json",
    ).data
    pick = opts["options"][0]
    v = c.post(
        f"/api/v1/planner/request-lessons/{lesson.id}/move",
        {"start_at": pick["start_at"]},
        format="json",
    ).data
    assert v["conflicts"] == 0 and v["can_complete"]


def test_rerun_keeps_other_reviews_reserved(world):
    w, c = world, world["client"]
    a = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data[
        "id"
    ]
    # seconda richiesta, stesso tutor e stesso studente: non può prendere gli stessi orari
    b = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data[
        "id"
    ]
    la = AutoPlanLesson.objects.get(plan__request_id=a, state="PROPOSED")
    lb = AutoPlanLesson.objects.get(plan__request_id=b, state="PROPOSED")
    assert la.start_at >= lb.end_at or lb.start_at >= la.end_at
    r = c.post(f"/api/v1/teaching-requests/{a}/planning/rerun", {}, format="json")
    assert r.status_code == 200 and len(r.data["lessons"]) == 1
    assert AutoPlan.objects.filter(request_id=a, state="DRAFT").count() == 1


def test_group_lesson_request(world):
    w, c = world, world["client"]
    ids = [str(s.id) for s in w["students"][:3]]
    r = c.post(
        "/api/v1/teaching-requests/",
        series(
            w, weeks=2, student=None, participant_ids=ids, group_label="Gruppo verifica"
        ),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert (
        r.data["target_type"] == "GROUP" and r.data["group_label"] == "Gruppo verifica"
    )
    assert (
        sorted(r.data["participant_ids"]) == sorted(ids)
        and len(r.data["participant_names"]) == 3
    )
    v = c.get(f"/api/v1/teaching-requests/{r.data['id']}/planning").data
    assert len(v["lessons"]) == 2
    assert all(len(l["students"]) == 3 for l in v["lessons"])
    c.post(
        f"/api/v1/teaching-requests/{r.data['id']}/planning/complete", {"publish_now": True}, format="json"
    )
    occ = LessonOccurrence.objects.filter(demand__request_id=r.data["id"]).first()
    assert occ.participants.count() == 3


def test_group_lesson_respects_every_participant(world):
    w, c = world, world["client"]
    first = monday_in(2)
    # il terzo studente è impegnato tutti i pomeriggi tranne il giovedì
    for wd in (0, 1, 2, 4):
        Commitment.objects.create(
            student=w["students"][2],
            kind="WEEKLY",
            weekday=wd,
            start_time=time(14),
            end_time=time(20),
            label="Sport",
        )
    ids = [str(s.id) for s in w["students"]]
    r = c.post(
        "/api/v1/teaching-requests/",
        series(w, weeks=1, student=None, participant_ids=ids),
        format="json",
    )
    assert r.data["group_label"].startswith("Gruppo:")
    [lesson] = AutoPlanLesson.objects.filter(
        plan__request_id=r.data["id"], state="PROPOSED"
    )
    assert lesson.start_at.astimezone(ROME).weekday() == 3
    assert first <= lesson.start_at.astimezone(ROME).date()


def test_family_cannot_create_group_lessons(world):
    w = world
    guardian = Account.objects.create_user(
        username="rv-g2", email="rv-g2@example.invalid"
    )
    RoleGrant.objects.create(
        account=guardian, role="GUARDIAN", valid_from=timezone.now() - timedelta(days=1)
    )
    for s in w["students"][:2]:
        GuardianLink.objects.create(
            account=guardian,
            student=s,
            verified=True,
            can_view=True,
            valid_from=timezone.now() - timedelta(days=1),
        )
    fam = APIClient()
    fam.force_authenticate(guardian)
    body = series(
        w,
        student=None,
        participant_ids=[str(s.id) for s in w["students"][:2]],
        preferred_tutor_ids=[],
    )
    assert (
        fam.post("/api/v1/teaching-requests/", body, format="json").status_code == 403
    )


# --- v0.9.10: il motore lavora sul mese, mai errori 500 alla conferma -------------------


def test_request_engine_works_on_one_month(world):
    w, c = world, world["client"]
    # serie di 10 settimane: il motore colloca solo le lezioni del primo mese
    r = c.post("/api/v1/teaching-requests/", series(w, weeks=10), format="json")
    rid = r.data["id"]
    start = monday_in(2)
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert v["month"] == start.isoformat()[:7] and len(v["months"]) >= 2
    days = [datetime.fromisoformat(l["start_at"]).astimezone(ROME).date() for l in v["lessons"]]
    assert days and all(d.month == start.month for d in days)
    assert AutoPlan.objects.get(request_id=rid, state="DRAFT").stats["months"] == [v["month"]]
    # fuori dal mese non si aggiunge nulla a mano
    later = start + timedelta(weeks=6)
    r = c.post(
        f"/api/v1/teaching-requests/{rid}/planning/lessons",
        {"start_at": datetime.combine(later, time(16), ROME).isoformat(), "tutor_id": str(w["tutors"][0].id)},
        format="json",
    )
    assert r.status_code == 422 and r.data["code"] == "OUT_OF_MONTH"
    # si può ricalcolare un altro mese della richiesta
    nxt = v["months"][1]
    v = c.post(f"/api/v1/teaching-requests/{rid}/planning/rerun", {"month": nxt}, format="json").data
    assert v["month"] == nxt
    assert all(l["start_at"] and datetime.fromisoformat(l["start_at"]).astimezone(ROME).date().isoformat()[:7] == nxt for l in v["lessons"])
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {"accept_missing": True}, format="json")
    assert r.status_code == 200, r.data


def test_group_needs_room_with_enough_seats(world):
    w, c = world, world["client"]
    Resource.objects.filter(name="Aula RV").update(student_capacity=2)
    ids = [str(s.id) for s in w["students"][:3]]
    r = c.post(
        "/api/v1/teaching-requests/",
        series(w, weeks=1, student=None, participant_ids=ids, group_label="Troppi"),
        format="json",
    )
    rid = r.data["id"]
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert v["lessons"] == [] and v["missing"] == 1
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {"accept_missing": True}, format="json")
    assert r.status_code == 200, r.data


def test_lesson_without_room_is_a_conflict_not_a_server_error(world):
    w, c = world, world["client"]
    rid = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data["id"]
    plan = AutoPlan.objects.get(request_id=rid, state="DRAFT")
    plan.lessons.update(space=None)
    v = c.get(f"/api/v1/teaching-requests/{rid}/planning").data
    assert v["conflicts"] == 1 and not v["can_complete"]
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {}, format="json")
    assert r.status_code == 409 and r.data["code"] == "UNRESOLVED_CONFLICTS"


def test_database_rejection_on_publish_is_reported(world, monkeypatch):
    from django.db import IntegrityError

    from apps.scheduling import autoplan_publish

    w, c = world, world["client"]
    rid = c.post("/api/v1/teaching-requests/", series(w, weeks=1), format="json").data["id"]

    def boom(*a, **k):
        raise IntegrityError("Space capacity exceeded")

    monkeypatch.setattr(autoplan_publish, "materialize", boom)
    r = c.post(f"/api/v1/teaching-requests/{rid}/planning/complete", {}, format="json")
    assert r.status_code == 409 and r.data["code"] == "PLAN_INVALID"
    assert TeachingRequest.objects.get(pk=rid).planning_state == "REVIEW"


def test_single_lesson_rejected_when_center_closed(world):
    w, c = world, world["client"]
    day = monday_in(2)
    body = {
        "student": str(w["students"][0].id),
        "subject": str(w["subject"].id),
        "kind": "SINGLE",
        "mode": "IN_PERSON",
        "duration_minutes": 60,
        "period_start": day.isoformat(),
        "fixed_time": "19:00",  # il centro chiude alle 19
        "preferred_tutor_ids": [str(w["tutors"][0].id)],
        "tutor_choice": "REQUIRED",
    }
    r = c.post("/api/v1/teaching-requests/", body, format="json")
    assert r.status_code == 400 and "chiuso" in str(r.data["fixed_time"])
    body["fixed_time"] = "18:30"  # finirebbe alle 19:30
    assert c.post("/api/v1/teaching-requests/", body, format="json").status_code == 400
    body["fixed_time"] = "17:00"
    r = c.post("/api/v1/teaching-requests/", body, format="json")
    assert r.status_code == 201, r.data
