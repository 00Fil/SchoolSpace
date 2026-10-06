"""v0.9.6: tipi di richiesta (lezione singola, percorso con lo stesso tutor),
canale di arrivo e pagina Materie."""

from datetime import timedelta
import pytest
from apps.education.models import Subject, TeachingRequest
from apps.scheduling.solver import simulate
from apps.scheduling.source import compile_source
from tests.test_database_planning import demo, WEEK  # noqa: F401
from tests.test_planning_requests_v094 import body, guardian_for, setup

pytestmark = pytest.mark.django_db


def units_of(data, request_id):
    return [u for u in data["units"] if request_id in u["demand_key"]]


def test_single_lesson_fixed_day_and_time_is_placed_there(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    r = client.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SINGLE", fixed_time="11:00", period_end=None),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["kind"] == "SINGLE" and r.data["period_end"] == str(WEEK)
    assert r.data["fixed_time"] == "11:00:00" and r.data["sessions_per_week"] == 1
    data, _ = compile_source(policy, WEEK, "STRICT")
    [unit] = units_of(data, r.data["id"])
    assert unit["latest_end"] - unit["earliest_start"] == 60
    result = simulate(data)
    assert result["validation"]["status"] == "PASSED"
    placed = next(a for a in result["assignments"] if a["demand_key"] == unit["demand_key"])
    assert placed["start"] == unit["earliest_start"]


def test_single_lesson_in_a_week_is_one_unit(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    r = client.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SINGLE", sessions_per_week=3),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["sessions_per_week"] == 1
    data, _ = compile_source(policy, WEEK, "STRICT")
    assert len(units_of(data, r.data["id"])) == 1
    # Una lezione singola non può coprire più settimane.
    bad = client.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SINGLE", period_end=str(WEEK + timedelta(days=9))),
        format="json",
    )
    assert bad.status_code == 400 and "period_end" in bad.data


def test_recurring_has_weekly_lessons_and_one_required_tutor(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    # Il centro deve scegliere il tutor delle lezioni ricorrenti.
    missing = client.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SERIES", sessions_per_week=2),
        format="json",
    )
    assert missing.status_code == 400 and "preferred_tutor_ids" in missing.data
    r = client.post(
        "/api/v1/teaching-requests/",
        body(
            student,
            subject,
            kind="SERIES",
            sessions_per_week=2,
            period_start=str(WEEK + timedelta(days=2)),  # mercoledì: prima settimana parziale
            period_end=str(WEEK + timedelta(days=60)),
            preferred_tutor_ids=[str(tutors[1].id)],
        ),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["tutor_choice"] == "REQUIRED" and "total_lessons" not in r.data
    data, _ = compile_source(policy, WEEK, "STRICT")
    units = units_of(data, r.data["id"])
    assert len(units) == 2
    assert all(u["allowed_tutors"] == [str(tutors[1].id)] for u in units)
    p = client.patch(
        f"/api/v1/teaching-requests/{r.data['id']}/", {"sessions_per_week": 1}, format="json"
    )
    assert p.status_code == 200, p.data
    assert p.data["sessions_per_week"] == 1 and p.data["tutor_choice"] == "REQUIRED"
    no_end = client.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SERIES", period_end=None, preferred_tutor_ids=[str(tutors[1].id)]),
        format="json",
    )
    assert no_end.status_code == 400 and "period_end" in no_end.data


def test_guardian_recurring_without_tutor_needs_one_at_approval(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    _, family = guardian_for(student)
    r = family.post(
        "/api/v1/teaching-requests/",
        body(student, subject, kind="SERIES"),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["status"] == "PENDING" and r.data["origin"] == "GUARDIAN"
    assert r.data["tutor_choice"] == "ANY"
    url = f"/api/v1/teaching-requests/{r.data['id']}/approve/"
    no = client.post(url, {}, format="json")
    assert no.status_code == 400 and no.data["code"] == "TUTOR_REQUIRED"
    ok = client.post(url, {"tutor_id": str(tutors[0].id)}, format="json")
    assert ok.status_code == 200, ok.data
    assert ok.data["status"] == "APPROVED" and ok.data["tutor_choice"] == "REQUIRED"
    assert [t["id"] for t in ok.data["preferred_tutors"]] == [str(tutors[0].id)]


def test_center_request_is_approved_and_internal(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    r = client.post("/api/v1/teaching-requests/", body(student, subject, kind="SINGLE"), format="json")
    assert r.status_code == 201, r.data
    assert r.data["origin"] == "CENTER" and r.data["status"] == "APPROVED"
    assert "channel" not in r.data
    legacy = client.post("/api/v1/teaching-requests/", body(student, subject), format="json")
    assert legacy.data["kind"] == "WEEKLY"


def test_subjects_page_edit_archive_delete(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    overview = client.get("/api/v1/subjects/overview/")
    assert overview.status_code == 200
    row = next(s for s in overview.data["results"] if s["id"] == str(subject.id))
    assert row["tutors"] and row["paths"] >= 1 and row["deletable"] is False
    # Rinomina e descrizione.
    p = client.patch(
        f"/api/v1/subjects/{subject.id}/",
        {"name": "Matematica avanzata", "description": "Programma liceo"},
        format="json",
    )
    assert p.status_code == 200, p.data
    assert p.data["name"] == "Matematica avanzata" and p.data["version"] == 2
    # Nome duplicato (senza distinzione di maiuscole).
    other = Subject.objects.create(name="Chimica")
    dup = client.patch(f"/api/v1/subjects/{other.id}/", {"name": "matematica AVANZATA"}, format="json")
    assert dup.status_code == 400
    # In uso: niente eliminazione, si archivia.
    assert client.delete(f"/api/v1/subjects/{subject.id}/").status_code == 409
    a = client.patch(f"/api/v1/subjects/{subject.id}/", {"active": False}, format="json")
    assert a.status_code == 200 and a.data["active"] is False
    options = client.get("/api/v1/teaching-requests/options/").data["subjects"]
    assert str(subject.id) not in {s["id"] for s in options}
    blocked = client.post("/api/v1/teaching-requests/", body(student, subject), format="json")
    assert blocked.status_code == 400 and "subject" in blocked.data
    # Mai usata: si elimina.
    assert client.delete(f"/api/v1/subjects/{other.id}/").status_code == 204
    assert not Subject.objects.filter(pk=other.id).exists()
    # Le famiglie non gestiscono le materie.
    _, family = guardian_for(student)
    assert family.get("/api/v1/subjects/overview/").status_code == 403
    assert family.patch(f"/api/v1/subjects/{subject.id}/", {"active": True}, format="json").status_code in (403, 404)
    assert TeachingRequest.objects.filter(subject=subject).exists()
