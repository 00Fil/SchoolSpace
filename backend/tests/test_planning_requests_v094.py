"""v0.9.4: richieste delle famiglie con approvazione, tutor preferito/obbligatorio,
profilo di calcolo accurato e panoramica della pianificazione."""

from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from apps.identity.models import Account, RoleGrant
from apps.education.models import GuardianLink, LearningPath, TeachingRequest, Tutor
from apps.scheduling.models import PlanningPolicy, PlanningRevision, ScheduleRun
from apps.scheduling.objectives import PREFERRED_TUTOR_WEIGHT, evaluate
from apps.scheduling.runs import dispatch_one, process_run, run_limits, submit_run, LEASE_SECONDS
from apps.scheduling.solver import simulate
from apps.scheduling.source import DataNotReady, compile_source
from tests.test_database_planning import demo, WEEK  # noqa: F401

pytestmark = pytest.mark.django_db


def setup(demo):  # noqa: F811
    actor, policy, client = demo
    path = LearningPath.objects.get(title__startswith="DEMO SINTETICO")
    enrollment = path.enrollments.select_related("student").first()
    student = enrollment.student
    if student.level != path.level:
        student.level = path.level
        student.save()
    subject = path.required_subjects.order_by("name").first()
    tutors = list(Tutor.objects.filter(display_name__startswith="Tutor pianificazione"))
    return actor, policy, client, student, subject, sorted(tutors, key=lambda t: t.display_name)


def body(student, subject, **extra):
    return {
        "student": str(student.id),
        "subject": str(subject.id),
        "mode": "IN_PERSON",
        "duration_minutes": 60,
        "sessions_per_week": 1,
        "period_start": str(WEEK),
        "period_end": str(WEEK + timedelta(days=6)),
        **extra,
    }


def guardian_for(student):
    account = Account.objects.create_user(
        username="req-guardian", email="req-guardian@example.invalid"
    )
    RoleGrant.objects.create(account=account, role="GUARDIAN", valid_from=timezone.now())
    GuardianLink.objects.create(
        account=account,
        student=student,
        verified=True,
        can_view=True,
        valid_from=timezone.now(),
    )
    c = APIClient()
    c.force_authenticate(account)
    return account, c


def test_guardian_request_is_pending_until_center_approves(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    before = len(compile_source(policy, WEEK, "STRICT")[1])
    _, family = guardian_for(student)
    r = family.post(
        "/api/v1/teaching-requests/",
        body(student, subject, priority="P0", mandatory=True),
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["status"] == "PENDING" and r.data["origin"] == "GUARDIAN"
    # La famiglia non decide priorità e obbligatorietà.
    assert r.data["priority"] == "P1" and r.data["mandatory"] is False
    assert len(compile_source(policy, WEEK, "STRICT")[1]) == before
    assert family.post(f"/api/v1/teaching-requests/{r.data['id']}/approve/").status_code == 403
    ok = client.post(f"/api/v1/teaching-requests/{r.data['id']}/approve/")
    assert ok.status_code == 200 and ok.data["status"] == "APPROVED"
    assert len(compile_source(policy, WEEK, "STRICT")[1]) == before + 1
    options = family.get("/api/v1/teaching-requests/options/").data["subjects"]
    assert any(s["id"] == str(subject.id) and s["tutors"] for s in options)
    assert "levels" not in str(options)


def test_guardian_cannot_request_for_other_children(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    other = (
        LearningPath.objects.get(title__startswith="DEMO SINTETICO")
        .enrollments.exclude(student=student)
        .first()
        .student
    )
    _, family = guardian_for(student)
    r = family.post("/api/v1/teaching-requests/", body(other, subject), format="json")
    assert r.status_code == 403


def test_required_tutor_is_a_hard_constraint(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    r = client.post(
        "/api/v1/teaching-requests/",
        body(
            student,
            subject,
            tutor_choice="REQUIRED",
            preferred_tutor_ids=[str(tutors[1].id)],
        ),
        format="json",
    )
    assert r.status_code == 201 and r.data["status"] == "APPROVED"
    data, specs = compile_source(policy, WEEK, "STRICT")
    unit = next(u for u in data["units"] if r.data["id"] in u["demand_key"])
    assert unit["allowed_tutors"] == [str(tutors[1].id)]
    result = simulate(data)
    assert result["validation"]["status"] == "PASSED"
    placed = [a for a in result["assignments"] if a["demand_key"] == unit["demand_key"]]
    assert all(a["tutor_id"] == str(tutors[1].id) for a in placed)
    # Un tutor obbligatorio senza competenza blocca, senza rilassare il vincolo.
    stranger = Tutor.objects.create(display_name="Tutor senza competenze")
    patch = client.patch(
        f"/api/v1/teaching-requests/{r.data['id']}/",
        {"preferred_tutor_ids": [str(stranger.id)]},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    with pytest.raises(DataNotReady) as error:
        compile_source(policy, WEEK, "STRICT")
    assert error.value.code == "REQUIRED_TUTOR_UNAVAILABLE"
    assert error.value.ref == r.data["id"]


def test_preferred_tutor_is_a_soft_objective_term(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    rev = PlanningRevision.objects.get(pk=1).revision
    r = client.post(
        "/api/v1/teaching-requests/",
        body(
            student,
            subject,
            tutor_choice="PREFERRED",
            preferred_tutor_ids=[str(tutors[0].id)],
        ),
        format="json",
    )
    assert r.status_code == 201
    assert PlanningRevision.objects.get(pk=1).revision > rev
    data, _ = compile_source(policy, WEEK, "STRICT")
    assert data["schema_version"] == "0.5" and "P" in data["objective_order"]
    unit = next(u for u in data["units"] if r.data["id"] in u["demand_key"])
    assert unit["preferred_tutors"] == [str(tutors[0].id)]
    assert len(unit["allowed_tutors"]) == 2
    result = simulate(data)
    assert result["validation"]["status"] == "PASSED"
    placed = next(a for a in result["assignments"] if a["demand_key"] == unit["demand_key"])
    assert placed["tutor_id"] == str(tutors[0].id)
    # Valutatore indipendente: stesso costo del modello.
    moved = [dict(a) for a in result["assignments"]]
    for a in moved:
        if a["demand_key"] == unit["demand_key"]:
            a["tutor_id"] = str(tutors[1].id)
    assert evaluate(data, moved)["P"] - evaluate(data, result["assignments"])["P"] == PREFERRED_TUTOR_WEIGHT


def test_thorough_effort_scales_limits_and_keeps_invariants(demo, settings):  # noqa: F811
    actor, policy, client, *_ = setup(demo)
    settings.PLANNING_THOROUGH_BUDGET_SECONDS = 4
    response = submit_run(
        actor,
        policy.id,
        WEEK,
        PlanningRevision.objects.get(pk=1).revision,
        "STRICT",
        "thorough-key",
        effort="THOROUGH",
    )
    run = ScheduleRun.objects.get(pk=response["run_id"])
    assert response["effort"] == "THOROUGH"
    assert run.snapshot.data["budget_seconds"] == 4
    assert run.snapshot.data["search_workers"] == settings.PLANNING_THOROUGH_WORKERS
    assert process_run(run.id) == "SUCCEEDED"
    assert run_limits(3) == (60, 90, LEASE_SECONDS)
    for budget in (31, 3600, 6 * 3600, 43200):
        soft, hard, lease = run_limits(budget)
        assert budget < soft < hard < lease


def test_overview_reports_options_per_request(demo):  # noqa: F811
    actor, policy, client, student, subject, tutors = setup(demo)
    _, family = guardian_for(student)
    family.post("/api/v1/teaching-requests/", body(student, subject), format="json")
    r = client.get(f"/api/v1/planning/overview?horizon_start={WEEK}&policy_id={policy.id}")
    assert r.status_code == 200, r.data
    assert r.data["ready"] is True and r.data["counts"]["PENDING"] == 1
    approved = [q for q in r.data["requests"] if q["status"] == "APPROVED"]
    assert approved and all(q["competent_tutors"] for q in approved)
    analysis = r.data["analysis"]
    assert analysis["units"] == 6
    assert all(row["placeable_units"] == row["units"] for row in analysis["requests"].values())
    assert {t["id"] for t in analysis["tutors"]} == {str(t.id) for t in tutors}
    assert family.get(f"/api/v1/planning/overview?horizon_start={WEEK}").status_code == 403


def test_thorough_runs_use_dedicated_queue_and_scaled_limits(demo, settings, monkeypatch):  # noqa: F811
    actor, policy, *_ = setup(demo)
    settings.PLANNING_THOROUGH_BUDGET_SECONDS = 3600
    settings.PLANNING_THOROUGH_QUEUE = "solver_long"
    sent = []
    monkeypatch.setattr(
        "apps.scheduling.tasks.execute.apply_async", lambda **kw: sent.append(kw)
    )
    rev = PlanningRevision.objects.get(pk=1).revision
    quick = submit_run(actor, policy.id, WEEK, rev, "STRICT", "q-key")
    slow = submit_run(actor, policy.id, WEEK, rev, "STRICT", "s-key", effort="THOROUGH")
    assert dispatch_one(quick["run_id"]) and dispatch_one(slow["run_id"])
    assert sent[0]["queue"] == "solver" and "time_limit" not in sent[0]
    soft, hard, _ = run_limits(3600)
    assert sent[1] == {
        "args": [slow["run_id"]],
        "queue": "solver_long",
        "retry": False,
        "soft_time_limit": soft,
        "time_limit": hard,
    }


def test_long_search_watchdog_heartbeats_and_cancels(monkeypatch):
    import threading
    from apps.scheduling import solver as engine

    monkeypatch.setattr(engine, "WATCH_INTERVAL_SECONDS", 0.05)

    class Fake:
        def __init__(self):
            self.stopped = threading.Event()

        def solve(self, model):
            assert self.stopped.wait(5), "stop_search mai chiamato"
            return "STOPPED"

        def stop_search(self):
            self.stopped.set()

    beats = []

    def progress(phase):
        beats.append(phase)
        if len(beats) >= 3:
            raise InterruptedError("CANCELLED")

    with pytest.raises(InterruptedError):
        engine.solve_watched(Fake(), None, progress, remaining=3600)
    assert beats == ["SEARCH"] * 3
    # Ricerche brevi (<= 30 s): nessun thread, comportamento invariato.
    quick = Fake()
    quick.stopped.set()
    assert engine.solve_watched(quick, None, progress, remaining=10) == "STOPPED"
