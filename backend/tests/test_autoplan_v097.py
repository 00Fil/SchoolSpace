"""v0.9.7: pianificatore mensile con orari del centro rigidi, impegni di studenti e
tutor rispettati con tolleranza di 30 minuti (e conferma), ricorrenze e buchi."""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.calendar.models import LessonOccurrence
from apps.communications.models import Delivery, OutboxEvent
from apps.education.models import Family, GuardianLink, Resource, Student, Subject, TeachingRequest, Tutor
from apps.identity.models import Account, RoleGrant
from apps.scheduling import autoplan
from apps.scheduling.autoplan import ROME
from apps.scheduling.models import AutoPlanConfirmation, Closure, Commitment, OpeningHours, TutorSkill

pytestmark = pytest.mark.django_db

MONTH = date(2026, 11, 1)  # novembre 2026: lunedì 2 è il primo lunedì
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=ROME)


@pytest.fixture
def world(settings):
    settings.AUTOPLAN_TIME_LIMIT_SECONDS = 8
    settings.AUTOPLAN_WORKERS = 4
    center = Account.objects.create_superuser(username="ap-center", email="ap-center@example.invalid", password="x-Test-pass-1")
    client = APIClient()
    client.force_authenticate(center)
    family = Family.objects.create(reference="AP-FAM")
    students = [Student.objects.create(display_name=f"Studente {n}", family=family) for n in "AB"]
    tutor_accounts = [Account.objects.create_user(username=f"ap-tutor{i}", email=f"ap-tutor{i}@example.invalid") for i in range(2)]
    for a in tutor_accounts:
        RoleGrant.objects.create(account=a, role="TUTOR", valid_from=timezone.now() - timedelta(days=1))
    tutors = [Tutor.objects.create(display_name=f"Tutor {n}", account=a) for n, a in zip("XY", tutor_accounts)]
    subject = Subject.objects.create(name="Matematica AP")
    for t in tutors:
        TutorSkill.objects.create(tutor=t, subject=subject, level="", mode="IN_PERSON", valid_from=date(2026, 9, 1), valid_until=date(2027, 6, 30), approved=True)
    Resource.objects.create(name="Aula AP", kind="SPACE", student_capacity=4)
    for wd in range(5):  # lun–ven 15:00–19:00
        OpeningHours.objects.create(weekday=wd, start_time=time(15), end_time=time(19))
    return {"center": center, "client": client, "students": students, "tutors": tutors, "subject": subject}


def request(w, student, **extra):
    data = dict(
        student=student, subject=w["subject"], mode="IN_PERSON", duration_minutes=60, sessions_per_week=1,
        period_start=MONTH, period_end=date(2026, 11, 30), kind="WEEKLY", status="APPROVED",
    )
    data.update(extra)
    tutor = data.pop("tutor", None)
    req = TeachingRequest.objects.create(**data)
    if tutor:
        req.preferred_tutors.add(tutor)
    return req


def local(dt):
    return dt.astimezone(ROME)


def plan(w):
    return autoplan.plan_month(MONTH, w["center"], now=NOW)


def test_opening_hours_and_closures_are_hard(world):
    w = world
    request(w, w["students"][0], sessions_per_week=2, period_end=date(2026, 11, 29))
    # ferie: tutta la settimana del 9 novembre
    Closure.objects.create(start_at=datetime(2026, 11, 9, tzinfo=ROME), end_at=datetime(2026, 11, 16, tzinfo=ROME), mode="ALL", reason="Ferie")
    p = plan(w)
    lessons = list(p.lessons.all())
    assert lessons, p.unplaced
    for l in lessons:
        a, b = local(l.start_at), local(l.end_at)
        assert a.weekday() < 5 and a.time() >= time(15) and b.time() <= time(19)
        assert not (date(2026, 11, 9) <= a.date() <= date(2026, 11, 15))
    weeks = {local(l.start_at).date() - timedelta(days=local(l.start_at).weekday()) for l in lessons}
    assert date(2026, 11, 9) not in weeks
    count = lambda wk: sum(1 for l in lessons if local(l.start_at).date() - timedelta(days=local(l.start_at).weekday()) == wk)  # noqa: E731
    assert [count(date(2026, 11, d)) for d in (2, 16, 23, 30)] == [2, 2, 2, 0]
    [u] = p.unplaced
    assert u["reason"] == "CLOSED" and u["weeks"] == ["2026-11-09"] and u["missing"] == 2


def test_recurring_series_keeps_same_tutor_and_weekly_pattern(world):
    w = world
    request(w, w["students"][0], kind="SERIES", tutor=w["tutors"][1], tutor_choice="REQUIRED", sessions_per_week=1)
    p = plan(w)
    lessons = list(p.lessons.all())
    assert len(lessons) == 4  # 2, 9, 16, 23 nov (la settimana del 30 continua a dicembre)
    assert {l.tutor_id for l in lessons} == {w["tutors"][1].id}
    assert len({(local(l.start_at).weekday(), local(l.start_at).time()) for l in lessons}) == 1


def test_commitments_respected_with_30_minutes_tolerance_and_confirmation(world):
    w = world
    s = w["students"][0]
    # Lo studente è impegnato tutti i giorni 15:00–17:30: resta solo 17:30–19:00 (90 min).
    for wd in range(5):
        Commitment.objects.create(student=s, label="Sport", kind="WEEKLY", weekday=wd, start_time=time(15), end_time=time(17, 30))
    req = request(w, s, kind="SINGLE", duration_minutes=120, period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    p = plan(w)
    [l] = p.lessons.all()
    assert local(l.start_at).time() == time(17) and local(l.end_at).time() == time(19)
    assert l.overflow_minutes == 30
    [c] = l.confirmations.all()
    assert c.party == "STUDENT" and c.minutes == 30 and c.labels == ["Sport"] and c.status == "DRAFT"
    # Oltre i 30 minuti non si colloca.
    Commitment.objects.filter(student=s).update(start_time=time(15), end_time=time(17, 45))
    p2 = plan(w)
    assert not p2.lessons.exists()
    [u] = p2.unplaced
    assert u["request_id"] == str(req.id) and u["reason"] == "STUDENT_BUSY"


def test_tutor_commitments_and_existing_overlaps(world):
    w = world
    a, b = w["students"]
    x = w["tutors"][0]
    Commitment.objects.create(tutor=x, label="Università", kind="ONE_OFF", date=date(2026, 11, 4), start_time=time(15), end_time=time(17, 30))
    r1 = request(w, a, kind="SINGLE", tutor=x, tutor_choice="REQUIRED", period_start=date(2026, 11, 4), period_end=date(2026, 11, 4))
    r2 = request(w, b, kind="SINGLE", tutor=x, tutor_choice="REQUIRED", period_start=date(2026, 11, 4), period_end=date(2026, 11, 4))
    p = plan(w)
    lessons = list(p.lessons.order_by("start_at"))
    # Libero 17:30–19:00: la seconda lezione entra solo sforando di 30 minuti (17:00–18:00).
    assert len(lessons) == 2
    assert local(lessons[0].start_at).time() == time(17) and lessons[0].overflow_minutes == 30
    assert local(lessons[1].start_at).time() == time(18) and lessons[1].overflow_minutes == 0
    assert lessons[0].confirmations.get().party == "TUTOR"
    assert {r1.id, r2.id} == {l.request_id for l in lessons}


def test_gaps_are_minimized_for_tutor_days(world):
    w = world
    a, b = w["students"]
    x = w["tutors"][0]
    for s in (a, b):
        request(w, s, kind="SINGLE", tutor=x, tutor_choice="REQUIRED", period_start=date(2026, 11, 5), period_end=date(2026, 11, 5))
    p = plan(w)
    l1, l2 = p.lessons.order_by("start_at")
    assert l1.end_at == l2.start_at  # lezioni attaccate, nessun buco


def test_publish_and_confirmation_flow_api(world):
    w = world
    s = w["students"][0]
    guardian = Account.objects.create_user(username="ap-guardian", email="ap-guardian@example.invalid")
    guardian.email_verified = True
    guardian.save()
    RoleGrant.objects.create(account=guardian, role="GUARDIAN", valid_from=timezone.now() - timedelta(days=1))
    GuardianLink.objects.create(account=guardian, student=s, verified=True, can_view=True, can_manage_availability=True, valid_from=timezone.now() - timedelta(days=1))
    family = APIClient()
    family.force_authenticate(guardian)
    # Il genitore inserisce gli impegni dalla sua area (più giorni insieme).
    r = family.post("/api/v1/commitments", {"student": str(s.id), "label": "Piscina", "weekdays": [0, 1, 2, 3, 4], "start_time": "15:00", "end_time": "17:30"}, format="json")
    assert r.status_code == 201, r.data
    assert len(r.data) == 5
    other = Student.objects.create(display_name="Estraneo", family=Family.objects.create(reference="AP-ALTRA"))
    assert family.post("/api/v1/commitments", {"student": str(other.id), "label": "x", "weekday": 0, "start_time": "15:00", "end_time": "16:00"}, format="json").status_code == 404
    request(w, s, kind="SINGLE", duration_minutes=120, period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    request(w, w["students"][1], kind="SINGLE", period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    c = w["client"]
    assert c.put("/api/v1/planner/opening-hours", {"slots": [{"weekday": wd, "start": 900, "end": 1140} for wd in range(5)]}, format="json").status_code == 200
    import apps.scheduling.autoplan as engine
    real = engine.timezone.now
    engine.timezone.now = lambda: NOW
    try:
        r = c.post("/api/v1/planner/plans", {"month": "2026-11"}, format="json")
    finally:
        engine.timezone.now = real
    assert r.status_code == 201, r.data
    assert r.data["stats"]["placed"] == 2 and r.data["stats"]["overflow"] == 1
    plan_id = r.data["id"]
    r = c.post(f"/api/v1/planner/plans/{plan_id}/publish", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["published"] == 1 and r.data["awaiting"] == 1 and r.data["confirmations_sent"] == 1
    assert LessonOccurrence.objects.count() == 1
    event = OutboxEvent.objects.get(event_type="autoplan.confirmation_requested")
    channels = set(Delivery.objects.filter(event=event, recipient=guardian).values_list("channel", flat=True))
    assert channels == {"IN_APP", "EMAIL"}
    # La famiglia vede la richiesta nella sua area e accetta: la lezione viene pubblicata.
    mine = family.get("/api/v1/planner/confirmations").data
    assert len(mine) == 1 and mine[0]["status"] == "PENDING" and mine[0]["minutes"] == 30
    deferred()  # nuova richiesta HTTP = nuova transazione (vincoli differiti)
    r = family.post(f"/api/v1/planner/confirmations/{mine[0]['id']}/answer", {"accept": True}, format="json")
    assert r.status_code == 200 and r.data["lesson_state"] == "PUBLISHED", r.data
    assert LessonOccurrence.objects.count() == 2
    assert family.post(f"/api/v1/planner/confirmations/{mine[0]['id']}/answer", {"accept": True}, format="json").status_code == 409


def test_rejection_frees_slot_and_new_plan_only_fills_missing(world):
    w = world
    s = w["students"][0]
    Commitment.objects.create(student=s, label="Scuola", kind="ONE_OFF", date=date(2026, 11, 3), start_time=time(15), end_time=time(17, 30))
    request(w, s, kind="SINGLE", duration_minutes=120, period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    p = plan(w)
    from apps.scheduling import autoplan_publish

    autoplan_publish.publish(p.id, w["center"])
    conf = AutoPlanConfirmation.objects.get()
    out = autoplan_publish.answer(conf.id, w["center"], False, "Non riusciamo")
    assert out["lesson_state"] == "REJECTED"
    assert not LessonOccurrence.objects.exists()
    # Una nuova generazione ripropone la richiesta (lo slot è di nuovo libero).
    p2 = plan(w)
    assert p2.lessons.count() == 1


def test_readiness_and_center_only(world):
    w = world
    r = w["client"].get("/api/v1/planner/plans", {"month": "2026-11"})
    assert r.status_code == 200
    items = {i["key"]: i for i in r.data["readiness"]["items"]}
    assert items["hours"]["ok"] and r.data["readiness"]["can_generate"] is False  # nessuna richiesta
    OpeningHours.objects.all().delete()
    request(w, w["students"][0])
    r = w["client"].post("/api/v1/planner/plans", {"month": "2026-11"}, format="json")
    assert r.status_code == 409 and r.data["code"] == "NOT_READY"
    anon = APIClient()
    assert anon.get("/api/v1/planner/setup").status_code in (401, 403)


def deferred():
    """In produzione ogni richiesta apre una transazione nuova (vincoli DEFERRED);
    nei test l'intera funzione è una transazione sola e la pubblicazione li ha resi IMMEDIATE."""
    from django.db import connection

    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL DEFERRED")


def test_monthly_lesson_can_be_moved_from_agenda(world):
    """Bug v0.9.7: spostare una lezione del pianificatore mensile dava errore 500."""
    from apps.calendar import services
    from apps.scheduling import autoplan_publish

    w = world
    s = w["students"][0]
    request(w, s, kind="SINGLE", period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    Commitment.objects.create(tutor=w["tutors"][0], label="", kind="WEEKLY", weekday=2, start_time=time(15), end_time=time(19))
    Commitment.objects.create(tutor=w["tutors"][1], label="", kind="WEEKLY", weekday=2, start_time=time(15), end_time=time(19))
    autoplan_publish.publish(plan(w).id, w["center"])
    lesson = LessonOccurrence.objects.get()
    assert autoplan.is_monthly_lesson(lesson)
    # Le proposte del mensile non compaiono tra quelle del motore settimanale (pagina bianca).
    from apps.scheduling.models import SchedulePlan

    assert SchedulePlan.objects.exists()
    for path in ("/api/v1/schedule-plans/", "/api/v1/schedule-runs/"):
        r = w["client"].get(path)
        assert r.status_code == 200 and not (r.data.get("results", r.data) if isinstance(r.data, dict) else r.data)
    day = date(2026, 11, 4)  # mercoledì: il tutor della lezione è impegnato
    out = services.reschedule_options(w["center"], lesson.id, day)
    by_time = {local(datetime.fromisoformat(o["start_at"])).strftime("%H:%M"): o["codes"] for o in out["options"]}
    assert by_time["10:00"] == ["SERVICE_CLOSED"]
    assert "TUTOR_AVAILABILITY" in by_time["16:00"]
    # Giovedì alle 16 il centro è aperto e il tutor libero: lo spostamento riesce.
    target = datetime(2026, 11, 5, 16, tzinfo=ROME)
    deferred()
    assert services.reschedule_options(w["center"], lesson.id, target.date())["options"][64]["ok"]
    r = w["client"].post(
        f"/api/v1/occurrences/{lesson.id}/reschedule/",
        {"expected_version": lesson.version, "start_at": target.isoformat()},
        format="json",
        HTTP_IDEMPOTENCY_KEY="move-monthly",
    )
    assert r.status_code == 200, r.content
    lesson.refresh_from_db()
    assert lesson.start_at == target
    # Fuori orario di apertura lo spostamento è rifiutato con un errore leggibile (non 500).
    from apps.calendar.services import DomainError

    with pytest.raises(DomainError) as error:
        services.change_lesson(
            w["center"], lesson.id, "reschedule", {"expected_version": lesson.version, "start_at": datetime(2026, 11, 5, 9, tzinfo=ROME)}, "move-closed"
        )
    assert "SERVICE_CLOSED" in str(error.value.detail)


def test_commitments_of_same_person_cannot_overlap(world):
    w, c = world, world["client"]
    s = w["students"][0]
    url = "/api/v1/commitments"
    first = c.post(url, {"student": str(s.id), "label": "Scuola", "weekdays": [0], "start_time": "08:00", "end_time": "13:00"}, format="json")
    assert first.status_code == 201
    clash = c.post(url, {"student": str(s.id), "label": "", "weekdays": [0, 1], "start_time": "12:30", "end_time": "14:00"}, format="json")
    assert clash.status_code == 409 and clash.data["code"] == "COMMITMENT_OVERLAP"
    assert Commitment.objects.filter(student=s).count() == 1  # nessun effetto parziale (anche il martedì)
    # Adiacente: ammesso. Altro giorno o altra persona: ammesso.
    assert c.post(url, {"student": str(s.id), "label": "", "weekdays": [0], "start_time": "13:00", "end_time": "14:00"}, format="json").status_code == 201
    assert c.post(url, {"student": str(w["students"][1].id), "label": "", "weekdays": [0], "start_time": "09:00", "end_time": "10:00"}, format="json").status_code == 201
    later = c.post(url, {"student": str(s.id), "label": "", "weekdays": [2], "start_time": "09:00", "end_time": "10:00"}, format="json").data[0]
    # Spostare sopra un impegno esistente è rifiutato.
    moved = c.patch(f"{url}/{later['id']}", {"weekday": 0, "start_time": "09:00", "end_time": "10:00"}, format="json")
    assert moved.status_code == 409 and moved.data["code"] == "COMMITMENT_OVERLAP"
    # Periodi di validità disgiunti: ammesso.
    ok = c.post(url, {"student": str(s.id), "label": "Estivo", "kind": "WEEKLY", "weekday": 2, "start_time": "09:30", "end_time": "11:00", "valid_from": "2027-07-01", "valid_until": "2027-08-31"}, format="json")
    assert ok.status_code == 409  # l'impegno del mercoledì non ha scadenza: si sovrappone
    c.patch(f"{url}/{later['id']}", {"valid_until": "2027-06-30"}, format="json")
    assert c.post(url, {"student": str(s.id), "label": "Estivo", "kind": "WEEKLY", "weekday": 2, "start_time": "09:30", "end_time": "11:00", "valid_from": "2027-07-01", "valid_until": "2027-08-31"}, format="json").status_code == 201
    # Occasionali: stessa data sovrapposta rifiutata.
    assert c.post(url, {"student": str(s.id), "label": "Gita", "kind": "ONE_OFF", "date": "2026-11-10", "start_time": "08:00", "end_time": "24:00"}, format="json").status_code == 201
    assert c.post(url, {"student": str(s.id), "label": "Visita", "kind": "ONE_OFF", "date": "2026-11-10", "start_time": "15:00", "end_time": "16:00"}, format="json").status_code == 409


def test_drag_change_needs_confirmation_or_center_override(world):
    """Agenda: spostamento/durata via drag → in attesa di tutor e famiglia; il centro può confermare subito."""
    from apps.calendar.models import LessonChange
    from apps.scheduling import autoplan_publish

    w, c = world, world["client"]
    s = w["students"][0]
    guardian = Account.objects.create_user(username="ap-guardian2", email="ap-guardian2@example.invalid")
    RoleGrant.objects.create(account=guardian, role="GUARDIAN", valid_from=timezone.now() - timedelta(days=1))
    GuardianLink.objects.create(account=guardian, student=s, verified=True, can_view=True, valid_from=timezone.now() - timedelta(days=1))
    family = APIClient()
    family.force_authenticate(guardian)
    request(w, s, kind="SINGLE", period_start=date(2026, 11, 3), period_end=date(2026, 11, 3))
    autoplan_publish.publish(plan(w).id, w["center"])
    deferred()
    lesson = LessonOccurrence.objects.get()
    tutor = APIClient()
    tutor.force_authenticate(lesson.tutor.account)
    start = datetime(2026, 11, 5, 16, tzinfo=ROME)
    url = f"/api/v1/occurrences/{lesson.id}/propose-change/"
    body = {"expected_version": lesson.version, "start_at": start.isoformat(), "end_at": (start + timedelta(minutes=90)).isoformat()}
    r = c.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="drag-1")
    assert r.status_code == 200, r.content
    assert r.data["applied"] is False and {a["party"] for a in r.data["change"]["answers"]} == {"TUTOR", "STUDENT"}
    lesson.refresh_from_db()
    assert local(lesson.start_at).day == 3  # la lezione non cambia finché non confermano
    assert OutboxEvent.objects.filter(event_type="lesson.change_requested").count() == 1
    # La lezione in Agenda mostra la modifica in attesa.
    week = c.get("/api/v1/calendar/", {"from": "2026-11-02", "until": "2026-11-09"})
    assert week.status_code == 200, week.content
    pending = week.data["results"][0]["time_change"]
    assert datetime.fromisoformat(pending["start_at"]) == start and len(pending["answers"]) == 2
    change = r.data["change"]["id"]
    # Fuori orario di apertura: rifiutato con un errore leggibile.
    late = datetime(2026, 11, 5, 18, 30, tzinfo=ROME)
    bad = c.post(url, {**body, "start_at": late.isoformat(), "end_at": (late + timedelta(hours=1)).isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="drag-bad")
    assert bad.status_code == 422 and "SERVICE_CLOSED" in str(bad.data)
    # Tutor e famiglia vedono la richiesta; un estraneo no.
    assert [x["id"] for x in tutor.get("/api/v1/lesson-changes/").data] == [change]
    mine = family.get("/api/v1/lesson-changes/").data
    assert mine[0]["answers"] and any(a["mine"] for a in mine[0]["answers"])
    r = tutor.post(f"/api/v1/lesson-changes/{change}/answer/", {"accept": True}, format="json")
    assert r.status_code == 200 and r.data["state"] == "PENDING"
    r = family.post(f"/api/v1/lesson-changes/{change}/answer/", {"accept": True}, format="json")
    assert r.status_code == 200 and r.data["state"] == "APPLIED", r.data
    lesson.refresh_from_db()
    assert lesson.start_at == start and lesson.end_at - lesson.start_at == timedelta(minutes=90)
    assert OutboxEvent.objects.filter(event_type="lesson.change_answered").count() == 1
    # Secondo drag: rifiuto della famiglia → la lezione resta dov'è.
    deferred()
    body2 = {"expected_version": lesson.version, "start_at": (start + timedelta(minutes=30)).isoformat(), "end_at": (start + timedelta(minutes=90)).isoformat()}
    r = c.post(url, body2, format="json", HTTP_IDEMPOTENCY_KEY="drag-2")
    assert r.status_code == 200, r.content
    second = r.data["change"]["id"]
    r = family.post(f"/api/v1/lesson-changes/{second}/answer/", {"accept": False, "note": "Non riusciamo"}, format="json")
    assert r.data["state"] == "REJECTED"
    lesson.refresh_from_db()
    assert lesson.start_at == start
    # Terzo drag con override del centro: applicato subito, senza conferme.
    deferred()
    r = c.post(url, {**body2, "expected_version": lesson.version}, format="json", HTTP_IDEMPOTENCY_KEY="drag-3")
    third = r.data["change"]["id"]
    deferred()
    r = c.post(f"/api/v1/lesson-changes/{third}/confirm/", {}, format="json")
    assert r.status_code == 200 and r.data["state"] == "APPLIED", r.content
    lesson.refresh_from_db()
    assert lesson.start_at == start + timedelta(minutes=30) and lesson.end_at == start + timedelta(minutes=90)
    # confirm_now direttamente dal drag; una nuova proposta sostituisce quella in attesa.
    deferred()
    r = c.post(url, {"expected_version": lesson.version, "start_at": start.isoformat(), "end_at": (start + timedelta(hours=1)).isoformat(), "confirm_now": True}, format="json", HTTP_IDEMPOTENCY_KEY="drag-4")
    assert r.status_code == 200 and r.data["applied"] is True, r.content
    lesson.refresh_from_db()
    assert lesson.start_at == start and lesson.end_at == start + timedelta(hours=1)
    assert not LessonChange.objects.filter(state="PENDING").exists()
    # La famiglia non può confermare al posto del centro.
    assert family.post(f"/api/v1/lesson-changes/{third}/confirm/", {}, format="json").status_code in (403, 404)
