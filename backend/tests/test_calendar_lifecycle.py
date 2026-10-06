"""GAP-E07 + GAP-E06 (s2-calendario): stato del piano e proposta dell'orizzonte."""

from io import StringIO

import pytest
from django.core.management import call_command
from apps.calendar.models import ConflictCase, HorizonProposal, PlanReview
from apps.education.path_services import DomainError
from apps.scheduling.models import SchedulePlan
from apps.scheduling.revision import bump_revision
from tests.test_calendar import center, plan_for, publish, WEEK, pytestmark  # noqa: F401
from tests.calendar_helpers import post, revision, week_lessons
from tests.test_calendar_conflicts import block_tutor


def validate(center, plan, key="v1", expected=None):
    return post(
        center[2],
        f"/api/v1/schedule-plans/{plan.id}/validate/",
        {"expected_revision": revision() if expected is None else expected},
        key,
    )


def lifecycle(center, plan):
    return center[2].get(f"/api/v1/schedule-plans/{plan.id}/lifecycle/").data


def test_validate_then_publish(center):
    plan = plan_for(center)
    assert lifecycle(center, plan)["state"] == "DRAFT"
    response = validate(center, plan)
    assert response.status_code == 200, response.data
    assert response.data["state"] == "VALIDATED"
    assert response.data["report"]["code"] == "PASSED"
    assert response.data["report"]["new_assignments"] == 6
    assert validate(center, plan).data == response.data
    assert not SchedulePlan.objects.filter(pk=plan.id, run__isnull=True).exists()
    publish(center, plan)
    info = lifecycle(center, plan)
    assert info["state"] == "PUBLISHED" and info["stored_state"] == "PUBLISHED"
    assert [h["operation"] for h in info["history"]][:1] == ["PLAN_VALIDATED"]


def test_stale_after_input_change(center):
    plan = plan_for(center)
    validate(center, plan)
    bump_revision()
    assert lifecycle(center, plan)["state"] == "STALE"
    response = validate(center, plan, "v2")
    assert response.data["state"] == "STALE"
    assert response.data["report"]["code"] == "STALE_INPUT"
    with pytest.raises(DomainError):
        publish(center, plan, "late")
    assert not week_lessons(WEEK).exists()


def test_reject_blocks_publication(center):
    plan = plan_for(center)
    version = lifecycle(center, plan)["version"]
    body = {"expected_version": version, "reason": "Non convince"}
    rejected = post(center[2], f"/api/v1/schedule-plans/{plan.id}/reject/", body, "r1")
    assert rejected.status_code == 200, rejected.data
    assert rejected.data["state"] == "REJECTED"
    with pytest.raises(DomainError) as error:
        publish(center, plan, "after-reject")
    assert error.value.detail["code"] == "PLAN_STATE_INVALID"
    again = validate(center, plan, "v3")
    assert again.data["code"] == "PLAN_STATE_INVALID"


def test_failed_validation_rejects_with_report(center, monkeypatch):
    plan = plan_for(center)

    def broken(plan, revision):
        raise DomainError(
            "CALENDAR_VALIDATION_FAILED", "Sintetico", violations=["TUTOR_UNAVAILABLE"]
        )

    monkeypatch.setattr("apps.calendar.lifecycle.verify_plan", broken)
    response = validate(center, plan)
    assert response.data["state"] == "REJECTED"
    assert response.data["report"]["violations"] == ["TUTOR_UNAVAILABLE"]


def test_explicit_validation_setting(center, settings):
    settings.CALENDAR_REQUIRE_EXPLICIT_VALIDATION = True
    plan = plan_for(center)
    with pytest.raises(DomainError) as error:
        publish(center, plan, "p0")
    assert error.value.detail["code"] == "EXPLICIT_VALIDATION_REQUIRED"
    validate(center, plan)
    publish(center, plan, "p1")
    assert PlanReview.objects.get(plan=plan).state == "PUBLISHED"


def horizon(center, key, weeks=2):
    return post(
        center[2],
        "/api/v1/calendar/horizon/",
        {"weeks": weeks, "policy_id": str(center[1].id)},
        key,
    )


def test_horizon_proposes_idempotently_and_never_publishes(center):
    first = horizon(center, "h1")
    assert first.status_code == 200, first.data
    states = [p["state"] for p in first.data["proposals"]]
    assert states == ["PROPOSED", "PROPOSED"] and first.data["published"] is False
    assert [p["week_start"] for p in first.data["proposals"]] == [
        "2026-10-05",
        "2026-10-12",
    ]
    again = horizon(center, "h2")
    assert [p["run_id"] for p in again.data["proposals"]] == [
        p["run_id"] for p in first.data["proposals"]
    ]
    assert HorizonProposal.objects.count() == 2
    assert not week_lessons(WEEK).exists()


def test_horizon_covered_and_blocked_by_open_conflicts(center):
    publish(center)
    covered = horizon(center, "h1", weeks=1)
    assert covered.data["proposals"][0]["state"] == "COVERED"
    block_tutor(week_lessons(WEEK, state="PUBLISHED").first())
    assert ConflictCase.objects.filter(state="OPEN").exists()
    blocked = horizon(center, "h2")
    assert [p["state"] for p in blocked.data["proposals"]] == ["BLOCKED", "BLOCKED"]
    assert blocked.data["proposals"][1]["blocking"][0]["kind"] == "VALIDATION"


def test_horizon_management_command(center):
    out = StringIO()
    call_command(
        "propose_calendar_horizon",
        actor=center[0].username,
        policy=str(center[1].id),
        weeks=1,
        stdout=out,
    )
    assert "2026-10-05" in out.getvalue() and "PROPOSED" in out.getvalue()
    detect = StringIO()
    call_command("detect_calendar_conflicts", stdout=detect)
    assert ConflictCase.objects.count() == 0


def test_periodic_tasks_gated(center, settings):
    from apps.calendar.tasks import detect_conflicts_task, propose_horizon_task

    settings.CALENDAR_HORIZON_ACTOR = ""
    assert propose_horizon_task() == "DISABLED"
    settings.CALENDAR_HORIZON_ACTOR = "inesistente"
    assert propose_horizon_task() == "ACTOR_INVALID"
    assert detect_conflicts_task() == 0
    assert not HorizonProposal.objects.exists()


def test_month_weeks_cover_next_month():
    """D06: l'orizzonte mensile copre tutte le settimane del mese successivo."""
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from apps.calendar.lifecycle import month_weeks

    weeks = month_weeks(datetime(2026, 10, 15, 12, tzinfo=ZoneInfo("Europe/Rome")))
    assert weeks[0] == date(2026, 10, 26)  # settimana che contiene il 1/11
    assert weeks[-1] == date(2026, 11, 30)
    assert all(w.weekday() == 0 for w in weeks)
