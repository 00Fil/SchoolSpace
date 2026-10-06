from datetime import date, timedelta
from io import StringIO
import uuid
import pytest
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.education.models import Student, TeachingRequest, LearningPath
from apps.availability.models import (
    AvailabilityRule,
    AvailabilityDeclaration,
    AvailabilityConflict,
)
from apps.scheduling.models import *
from apps.scheduling.source import compile_source, DataNotReady
from apps.scheduling.runs import (
    submit_run,
    process_run,
    cancel_run,
    reconcile_runs,
    dispatch_one,
)
from apps.education.path_services import Conflict, DomainError

pytestmark = pytest.mark.django_db
WEEK = date(2026, 10, 5)


@pytest.fixture
def demo(settings, monkeypatch):
    settings.DEBUG = True
    settings.EXPERIMENTAL_DB_PLANNING = True
    actor = Account.objects.create_superuser(
        username="db-center",
        email="db-center@example.invalid",
        password="synthetic-test-password",
    )
    call_command(
        "seed_planning_demo", actor=actor.username, days="0", stdout=StringIO()
    )
    monkeypatch.setattr("apps.scheduling.runs.dispatch_one", lambda run_id: False)
    client = APIClient()
    client.force_authenticate(actor)
    return actor, PlanningPolicy.objects.get(), client


def queue(demo, key="test-key"):
    actor, policy, _ = demo
    response = submit_run(
        actor,
        policy.id,
        WEEK,
        PlanningRevision.objects.get(pk=1).revision,
        "STRICT",
        key,
    )
    return ScheduleRun.objects.get(pk=response["run_id"])


def test_bridge_materializes_six_minimized_units(demo):
    actor, policy, _ = demo
    data, specs = compile_source(policy, WEEK, "STRICT")
    assert len(specs) == 6 and data["horizon_minutes"] == 10080
    assert "example.invalid" not in str(data) and "display_name" not in str(data)
    assert DemandUnit.objects.count() == 0  # readiness does not write demand
    run = queue(demo)
    assert DemandUnit.objects.count() == 6
    assert run.snapshot.environment["application"] == "0.7.0"
    assert process_run(run.id) == "SUCCEEDED"
    run.refresh_from_db()
    assert run.result["validation"]["status"] == "PASSED"
    assert len(run.plan.assignments) == 6 and run.result["publishable"] is False


@pytest.mark.parametrize(
    "model,changes,code",
    [
        (PlanningPolicy, {"approved_for_exploration": False}, "POLICY_NOT_APPROVED"),
        (
            PlanningPolicy,
            {"unsupported_constraints": ["FAMILY_SYNC"]},
            "UNSUPPORTED_CONSTRAINT",
        ),
        (AvailabilityDeclaration, {"state": "UNKNOWN"}, "MISSING_AVAILABILITY"),
        (AvailabilityRule, {"status": "DRAFT"}, "AVAILABILITY_PENDING"),
        (Student, {"active": False}, "CURRICULUM_NOT_READY"),
        (TutorSkill, {"approved": False}, "TUTOR_SKILLS_MISSING"),
    ],
)
def test_no_silent_relaxation(demo, model, changes, code):
    model.objects.all().update(**changes)
    policy = PlanningPolicy.objects.get()
    with pytest.raises(DataNotReady) as error:
        compile_source(policy, WEEK, "STRICT")
    assert error.value.code == code
    assert PlanningSnapshot.objects.count() == 0


@pytest.mark.parametrize(
    "model,code",
    [
        (ServiceWindow, "SERVICE_WINDOWS_MISSING"),
        (TutorOperatingPolicy, "TUTOR_LIMITS_MISSING"),
        (ResourceTiming, "RESOURCE_POLICY_MISSING"),
    ],
)
def test_required_configuration_missing(demo, model, code):
    model.objects.all().delete()
    with pytest.raises(DataNotReady) as error:
        compile_source(PlanningPolicy.objects.get(), WEEK, "STRICT")
    assert error.value.code == code


def test_conflicting_family_data_blocks(demo):
    AvailabilityConflict.objects.create(
        student=Student.objects.first(),
        reason="Synthetic incompatible declarations",
        open=True,
    )
    with pytest.raises(DataNotReady) as error:
        compile_source(demo[1], WEEK, "STRICT")
    assert error.value.code == "AVAILABILITY_CONFLICT"


def test_monday_required(demo):
    with pytest.raises(DataNotReady) as error:
        compile_source(demo[1], date(2026, 10, 6), "STRICT")
    assert error.value.code == "MONDAY_REQUIRED"


def test_autumn_dst_week_is_169_hours(demo):
    data, _ = compile_source(demo[1], date(2026, 10, 19), "STRICT")
    # DST transition is Sunday 25 October within week starting 19 October.
    assert data["horizon_minutes"] == 10140


@pytest.mark.parametrize("operation", ["save", "update", "bulk", "m2m"])
def test_revision_tracks_source_mutations(demo, operation):
    before = PlanningRevision.objects.get(pk=1).revision
    if operation == "save":
        obj = Student.objects.first()
        old = obj.version
        obj.display_name = "Synthetic revised"
        obj.save()
        assert obj.version > old
    elif operation == "update":
        Student.objects.all().update(display_name="Synthetic changed")
    elif operation == "bulk":
        students = list(Student.objects.all())
        students[0].display_name = "Synthetic bulk"
        Student.objects.bulk_update(students, ["display_name"])
    else:
        LearningPath.objects.first().required_subjects.clear()
    assert PlanningRevision.objects.get(pk=1).revision > before


@pytest.mark.parametrize(
    "operation", ["save", "update", "delete", "bulk_update", "bulk_create", "reused_pk"]
)
def test_snapshot_immutable(demo, operation):
    snap = queue(demo).snapshot
    with pytest.raises(ValidationError):
        if operation == "save":
            snap.save()
        elif operation == "update":
            PlanningSnapshot.objects.filter(pk=snap.pk).update(revision=999)
        elif operation == "delete":
            snap.delete()
        elif operation == "bulk_update":
            PlanningSnapshot.objects.bulk_update([snap], ["revision"])
        elif operation == "bulk_create":
            PlanningSnapshot.objects.bulk_create([snap])
        else:
            snap._state.adding = True
            snap.save(force_update=True)


def test_replay_returns_same_run_without_duplicate_demand(demo):
    run = queue(demo)
    assert queue(demo).id == run.id
    assert ScheduleRun.objects.count() == PlanningSnapshot.objects.count() == 1
    queue(demo, "another-key")
    assert DemandUnit.objects.count() == 6 and ScheduleRun.objects.count() == 2


def test_key_body_mismatch(demo):
    queue(demo)
    with pytest.raises(Conflict):
        submit_run(
            demo[0],
            demo[1].id,
            WEEK,
            PlanningRevision.objects.get(pk=1).revision,
            "COVERAGE",
            "test-key",
        )


@pytest.mark.parametrize("key", ["", "has space", "x" * 256])
def test_invalid_idempotency_key(demo, key):
    with pytest.raises(DomainError):
        queue(demo, key)
    assert ScheduleRun.objects.count() == 0


def test_expected_revision_rejected_before_writes(demo):
    with pytest.raises(Conflict):
        submit_run(demo[0], demo[1].id, WEEK, 0, "STRICT", "fresh")
    assert DemandUnit.objects.count() == PlanningSnapshot.objects.count() == 0


def test_stale_queued_job_never_solves(demo, monkeypatch):
    run = queue(demo)
    Student.objects.all().update(display_name="Changed")
    monkeypatch.setattr(
        "apps.scheduling.runs.simulate",
        lambda *a, **k: pytest.fail("stale input must not solve"),
    )
    assert process_run(run.id) == "FAILED"
    run.refresh_from_db()
    assert run.error_code == "STALE_INPUT" and SchedulePlan.objects.count() == 0


def test_change_during_search_returns_stale_plan(demo, monkeypatch):
    from apps.scheduling.solver import simulate

    run = queue(demo)

    def changing(dto, progress):
        result = simulate(dto, progress=progress)
        Student.objects.all().update(display_name="Changed during search")
        return result

    monkeypatch.setattr("apps.scheduling.runs.simulate", changing)
    assert (
        process_run(run.id) == "SUCCEEDED"
        and SchedulePlan.objects.get().state == "STALE"
    )


def test_duplicate_worker_delivery_single_attempt(demo):
    run = queue(demo)
    process_run(run.id)
    process_run(run.id)
    run.refresh_from_db()
    assert run.attempts == 1 and SchedulePlan.objects.count() == 1


def test_cancel_queued_job_idempotent(demo):
    run = queue(demo)
    cancel_run(run.id, demo[0])
    cancel_run(run.id, demo[0])
    assert process_run(run.id) == "CANCELLED"
    assert PlanningAudit.objects.filter(operation="cancel_run").count() == 1
    assert SchedulePlan.objects.count() == 0


def test_cancel_running_discards_result(demo, monkeypatch):
    from apps.scheduling.solver import simulate

    run = queue(demo)

    def cancelled(dto, progress):
        cancel_run(run.id, demo[0])
        return simulate(dto, progress=progress)

    monkeypatch.setattr("apps.scheduling.runs.simulate", cancelled)
    assert process_run(run.id) == "CANCELLED" and SchedulePlan.objects.count() == 0


def test_actor_revoked(demo):
    run = queue(demo)
    Account.objects.filter(pk=demo[0].id).update(is_active=False)
    assert process_run(run.id) == "CANCELLED"
    run.refresh_from_db()
    assert run.error_code == "ACTOR_ACCESS_REVOKED"


def test_broker_failure_leaves_durable_pending(demo, monkeypatch):
    run = queue(demo)

    def fail(**kwargs):
        raise ConnectionError("secret-redis-url-must-not-appear")

    monkeypatch.setattr("apps.scheduling.tasks.execute.apply_async", fail)
    assert dispatch_one(run.id) is False
    dispatch = RunDispatch.objects.get(run=run)
    assert dispatch.status == "PENDING" and dispatch.error_code == "BROKER_UNAVAILABLE"
    assert ScheduleRun.objects.get(pk=run.id).status == "QUEUED"


@pytest.mark.parametrize("attempts,status", [(1, "QUEUED"), (3, "FAILED")])
def test_lease_reconciliation(demo, attempts, status):
    run = queue(demo)
    ScheduleRun.objects.filter(pk=run.id).update(
        status="RUNNING",
        attempts=attempts,
        claim_token=uuid.uuid4(),
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    reconcile_runs()
    run.refresh_from_db()
    assert run.status == status
    if status == "QUEUED":
        assert run.claim_token is None


def test_technical_failure_does_not_expose_exception(demo, monkeypatch):
    run = queue(demo)

    def fail(*a, **k):
        raise RuntimeError("sensitive-secret")

    monkeypatch.setattr("apps.scheduling.runs.simulate", fail)
    assert process_run(run.id) == "FAILED"
    run.refresh_from_db()
    assert run.error_code == "EXECUTION_FAILED" and "sensitive" not in str(run.result)


@pytest.mark.parametrize("outcome", ["UNKNOWN", "INFEASIBLE"])
def test_successful_job_is_not_mathematical_success(demo, monkeypatch, outcome):
    run = queue(demo)
    monkeypatch.setattr(
        "apps.scheduling.runs.simulate",
        lambda *a, **k: {
            "solver_status": outcome,
            "validation": {"status": "NOT_RUN"},
            "assignments": [],
            "publishable": False,
        },
    )
    assert process_run(run.id) == "SUCCEEDED" and SchedulePlan.objects.count() == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/schedule-runs/",
        "/api/v1/schedule-plans/",
        "/api/v1/planning-policies/",
        "/api/v1/planning/data-readiness",
    ],
)
def test_family_denied(demo, endpoint):
    user = Account.objects.create_user(
        username="family", email="family@example.invalid"
    )
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(endpoint).status_code == 403


def test_api_run_poll_and_readiness(demo):
    actor, policy, client = demo
    url = f"/api/v1/planning/data-readiness?policy_id={policy.id}&horizon_start={WEEK}&mode=STRICT"
    ready = client.get(url)
    assert ready.status_code == 200 and ready.data["ready"]
    body = {
        "policy_id": str(policy.id),
        "horizon_start": str(WEEK),
        "expected_revision": ready.data["revision"],
        "mode": "STRICT",
    }
    response = client.post(
        "/api/v1/schedule-runs", body, format="json", HTTP_IDEMPOTENCY_KEY="api-key"
    )
    assert response.status_code == 202, response.data
    poll = client.get(response.data["poll_url"])
    assert poll.data["status"] == "QUEUED" and "claim_token" not in poll.data
    process_run(response.data["run_id"])
    poll = client.get(response.data["poll_url"])
    assert poll.data["status"] == "SUCCEEDED" and not poll.data["publishable"]
    Student.objects.all().update(display_name="Changed")
    plans = client.get("/api/v1/schedule-plans/")
    assert plans.data["results"][0]["state"] == "STALE"


def test_config_version_guard(demo):
    actor, policy, client = demo
    url = f"/api/v1/planning-policies/{policy.id}/"
    assert client.patch(url, {"name": "Changed"}, format="json").status_code == 400
    assert (
        client.patch(
            url, {"name": "Changed", "expected_version": 0}, format="json"
        ).status_code
        == 409
    )
    response = client.patch(
        url, {"name": "Changed", "expected_version": policy.version}, format="json"
    )
    assert response.status_code == 200 and response.data["version"] > policy.version


def test_availability_approval_version_and_author(demo):
    actor, policy, client = demo
    rule = AvailabilityRule.objects.first()
    rule.status = "DRAFT"
    rule.save()
    url = f"/api/v1/availability-rules/{rule.id}/approve/"
    assert (
        client.post(
            url, {"expected_version": 0, "reason": "Synthetic approval"}, format="json"
        ).status_code
        == 409
    )
    response = client.post(
        url,
        {"expected_version": rule.version, "reason": "Synthetic approval"},
        format="json",
    )
    assert response.status_code == 200, response.data
    rule.refresh_from_db()
    assert rule.status == "APPROVED" and rule.approved_by == actor


@pytest.mark.parametrize(
    "field,value",
    [
        ("budget_seconds", True),
        ("budget_seconds", 31),  # v0.5: budget ammesso fino a 30 s (NFR04)
        ("unsupported_constraints", "not-a-list"),
    ],
)
def test_config_strict_fields(demo, field, value):
    _, policy, client = demo
    response = client.patch(
        f"/api/v1/planning-policies/{policy.id}/",
        {"expected_version": policy.version, field: value},
        format="json",
    )
    assert response.status_code == 400


def test_development_flag_blocks_new_jobs(demo, settings):
    settings.FEATURE_PLANNING = False
    assert demo[2].post("/api/v1/schedule-runs", {}, format="json").status_code == 503
    assert ScheduleRun.objects.count() == 0


@pytest.mark.parametrize(
    "kind,code",
    [("hash", "SNAPSHOT_HASH_MISMATCH"), ("environment", "ENVIRONMENT_CHANGED")],
)
def test_snapshot_integrity_checked_before_search(demo, monkeypatch, kind, code):
    run = queue(demo)
    if kind == "hash":
        monkeypatch.setattr(
            "apps.scheduling.runs.input_hash", lambda value: "incorrect"
        )
    else:
        monkeypatch.setattr(
            "apps.scheduling.runs.runtime_environment",
            lambda: {"application": "changed"},
        )
    assert process_run(run.id) == "FAILED"
    run.refresh_from_db()
    assert run.error_code == code


def test_draft_rule_approval_unblocks_bridge(demo):
    rule = AvailabilityRule.objects.first()
    rule.status = "DRAFT"
    rule.save()
    url = f"/api/v1/planning/data-readiness?policy_id={demo[1].id}&horizon_start={WEEK}&mode=STRICT"
    assert demo[2].get(url).data["issues"][0]["code"] == "AVAILABILITY_PENDING"
    response = demo[2].post(
        f"/api/v1/availability-rules/{rule.id}/approve/",
        {"expected_version": rule.version, "reason": "Synthetic verification"},
        format="json",
    )
    assert response.status_code == 200 and demo[2].get(url).data["ready"]


def test_spring_dst_week_is_167_hours(demo):
    data, _ = compile_source(demo[1], date(2027, 3, 22), "STRICT")
    assert data["horizon_minutes"] == 10020


@pytest.mark.parametrize(
    "timestamp", ["2026-10-05T10:00:00", "2026-10-05T10:00:15+02:00"]
)
def test_closure_requires_explicit_offset_and_minute(demo, timestamp):
    response = demo[2].post(
        "/api/v1/closures/",
        {
            "start_at": timestamp,
            "end_at": "2026-10-05T11:00:00+02:00",
            "mode": "ALL",
            "resource": None,
            "reason": "Synthetic",
        },
        format="json",
    )
    assert response.status_code == 400


def test_configuration_root_array_rejected(demo):
    assert (
        demo[2].post("/api/v1/planning-policies/", [], format="json").status_code == 400
    )


def test_source_readiness_is_not_gate_approval(demo):
    assert demo[2].get("/api/v1/planning/readiness").data["ready"] is False


def test_seed_default_week_is_multi_day_and_idempotent(settings):
    settings.DEBUG = True
    settings.EXPERIMENTAL_DB_PLANNING = True
    actor = Account.objects.create_superuser(
        username="db-center-week",
        email="db-center-week@example.invalid",
        password="synthetic-test-password",
    )
    for _ in range(2):
        call_command("seed_planning_demo", actor=actor.username, stdout=StringIO())
    assert sorted(ServiceWindow.objects.values_list("weekday", flat=True)) == [0, 2, 3]
    tutors = AvailabilityRule.objects.filter(tutor__isnull=False)
    assert sorted(set(tutors.values_list("weekday", flat=True))) == [0, 2, 3]
    assert tutors.count() == 6
    data = compile_source(PlanningPolicy.objects.get(), WEEK, "STRICT")[0]
    assert len(data["units"]) == 6
    with pytest.raises(Exception):
        call_command(
            "seed_planning_demo", actor=actor.username, days="7", stdout=StringIO()
        )
