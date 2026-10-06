"""DB bridge with contract 0.5: multi-week horizon, LessonSeries, local replanning."""

from datetime import date, datetime, time, timezone as tz
from io import StringIO
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.education.path_services import DomainError
from apps.scheduling.models import (
    DemandUnit,
    LessonSeries,
    PlanningAudit,
    PlanningPolicy,
    PlanningRevision,
    SchedulePlan,
)
from apps.scheduling.runs import submit_run, process_run
from apps.scheduling.series import derive_series_from_plan
from apps.scheduling.source import compile_source, DataNotReady

pytestmark = pytest.mark.django_db
WEEK = date(2026, 10, 5)


@pytest.fixture
def center(settings, monkeypatch):
    settings.DEBUG = True
    settings.EXPERIMENTAL_DB_PLANNING = True
    settings.EXPERIMENTAL_CALENDAR = True
    monkeypatch.setattr("apps.scheduling.runs.dispatch_one", lambda run_id: False)
    monkeypatch.setattr(
        "apps.calendar.services.now", lambda: datetime(2026, 9, 30, tzinfo=tz.utc)
    )
    actor = Account.objects.create_superuser(
        username="v05-center",
        email="v05-center@example.invalid",
        password="synthetic-test-password",
    )
    call_command(
        "seed_planning_demo", actor=actor.username, days="0", stdout=StringIO()
    )
    client = APIClient()
    client.force_authenticate(actor)
    return actor, PlanningPolicy.objects.get(), client


def revision():
    return PlanningRevision.objects.get(pk=1).revision


def run_plan(actor, policy, key, mode="STRICT", **extra):
    response = submit_run(actor, policy.id, WEEK, revision(), mode, key, **extra)
    assert process_run(response["run_id"]) == "SUCCEEDED"
    return SchedulePlan.objects.get(run_id=response["run_id"])


def test_default_policy_keeps_contract_04(center):
    data, specs = compile_source(center[1], WEEK, "STRICT")
    assert data["schema_version"] == "0.4" and len(specs) == 6


def test_two_week_horizon_materialises_both_weeks(center):
    actor, policy, _ = center
    policy.horizon_weeks = 2
    policy.recurring_stability = "PREFERRED"
    policy.objective_order = ["P0", "P1", "P2", "F", "R"]
    policy.save()
    data, specs = compile_source(policy, WEEK, "STRICT")
    assert data["schema_version"] == "0.5" and data["horizon_days"] == 14
    assert len(specs) == 12 and {s[3] for s in specs} == {WEEK, date(2026, 10, 12)}
    assert data["fairness_policy"]["approval_status"] == "PENDING_APPROVAL"
    assert len(data["series"]) == 6 and all(
        len(s["units"]) == 2 for s in data["series"]
    )
    plan = run_plan(actor, policy, "two-weeks")
    assert DemandUnit.objects.filter(week_start=date(2026, 10, 12)).count() == 6
    result = plan.run.result
    assert result["validation"]["status"] == "PASSED" and len(plan.assignments) == 12
    assert result["policy_approvals"] == {"fairness": "PENDING_APPROVAL"}
    assert plan.run.snapshot.horizon_end == date(2026, 10, 19)


def test_series_derived_from_previous_plan_become_preferred_slots(center):
    actor, policy, _ = center
    policy.objective_order = ["P0", "P1", "P2", "R"]
    policy.save()
    plan = run_plan(actor, policy, "first")
    rows, _ = derive_series_from_plan(plan, actor)
    assert len(rows) == 6 and all(r.source == "PREVIOUS_PLAN" for r in rows)
    assert PlanningAudit.objects.filter(operation="derive_series").count() == 1
    data, _ = compile_source(PlanningPolicy.objects.get(), WEEK, "STRICT")
    slots = [s["preferred_slot"] for s in data["series"]]
    assert all(s and s["source"] == "PREVIOUS_PLAN" for s in slots)
    second = run_plan(actor, PlanningPolicy.objects.get(), "second")
    assert second.run.result["objective_values"]["R"] == 0
    with pytest.raises(DomainError):
        derive_series_from_plan(plan, actor)  # stale after the series write


def test_required_series_incompatible_week_is_reported(center):
    actor, policy, _ = center
    data, specs = compile_source(policy, WEEK, "STRICT")
    request = specs[0][0]
    LessonSeries.objects.create(
        request=request,
        serial=1,
        weekday=6,
        local_start_time=time(23, 0),
        stability="REQUIRED",
        source="DECLARED",
    )
    data, _ = compile_source(PlanningPolicy.objects.get(), WEEK, "STRICT")
    assert data["schema_version"] == "0.5"
    response = submit_run(actor, policy.id, WEEK, revision(), "STRICT", "required")
    process_run(response["run_id"])
    from apps.scheduling.models import ScheduleRun

    result = ScheduleRun.objects.get(pk=response["run_id"]).result
    assert result["solver_status"] == "INFEASIBLE"
    reasons = {
        d["demand_key"]: d["reason_codes"] for d in result["empty_domain_diagnostics"]
    }
    assert any("RECURRING_SLOT_REQUIRED" in r for r in reasons.values())


def test_authorised_local_replan_unlocks_only_requested_lesson(center):
    from apps.calendar.services import publish_plan
    from apps.calendar.models import LessonOccurrence

    actor, policy, _ = center
    plan = run_plan(actor, policy, "base")
    publish_plan(
        actor,
        plan.id,
        {
            "expected_version": 1,
            "expected_revision": plan.run.snapshot.revision,
            "accept_unassigned_demand_keys": [],
            "reason": "Synthetic publication",
            "confirm_experimental": True,
        },
        "publish",
    )
    lesson = (
        LessonOccurrence.objects.filter(state="PUBLISHED").order_by("start_at").first()
    )
    response = submit_run(
        actor,
        policy.id,
        WEEK,
        revision(),
        "STRICT",
        "replan",
        unlock=[{"lesson_id": lesson.id, "reason": "Assenza tutor sintetica"}],
        propose_scope_expansion=True,
    )
    from apps.scheduling.models import ScheduleRun, PlanningSnapshot

    snapshot = PlanningSnapshot.objects.get(pk=response["snapshot_id"])
    data = snapshot.data
    assert data["schema_version"] == "0.5" and data["replanning"]["scope"] == "LOCAL"
    unlocked = [u for u in data["units"] if u.get("previous_assignment")]
    assert [u["demand_key"] for u in unlocked] == [lesson.demand.demand_key]
    assert sum(1 for u in data["units"] if u["locked_assignment"]) == 5
    audit = PlanningAudit.objects.get(operation="authorize_unlock")
    assert data["replanning"]["unlocked"][0]["authorization_id"] == f"audit:{audit.id}"
    assert process_run(response["run_id"]) == "SUCCEEDED"
    assert (
        ScheduleRun.objects.get(pk=response["run_id"]).result["validation"]["status"]
        == "PASSED"
    )
    with pytest.raises(DataNotReady):
        compile_source(
            policy,
            WEEK,
            "STRICT",
            replanning={
                "authorizations": {"00000000-0000-0000-0000-000000000000": "audit:x"},
                "propose_scope_expansion": False,
            },
        )


def test_api_validates_v05_policy_and_run_command(center):
    actor, policy, client = center
    url = f"/api/v1/planning-policies/{policy.id}/"
    bad = client.patch(
        url,
        {"objective_order": ["P1", "P0", "P2"], "expected_version": policy.version},
        format="json",
    )
    assert bad.status_code == 400 and "Ordine obiettivi" in str(bad.data)
    good = client.patch(
        url,
        {
            "objective_order": ["P0", "P1", "P2", "F"],
            "horizon_weeks": 2,
            "expected_version": policy.version,
        },
        format="json",
    )
    assert good.status_code == 200, good.data
    assert good.data["horizon_weeks"] == 2
    body = {
        "policy_id": str(policy.id),
        "horizon_start": "2026-10-05",
        "expected_revision": revision(),
        "mode": "STRICT",
    }
    extra = client.post(
        "/api/v1/schedule-runs",
        {**body, "extra": 1},
        format="json",
        HTTP_IDEMPOTENCY_KEY="k1",
    )
    assert extra.status_code == 400
    lonely = client.post(
        "/api/v1/schedule-runs",
        {**body, "propose_scope_expansion": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY="k2",
    )
    assert lonely.status_code == 400
    ok = client.post(
        "/api/v1/schedule-runs", body, format="json", HTTP_IDEMPOTENCY_KEY="k3"
    )
    assert ok.status_code == 202
