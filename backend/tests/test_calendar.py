from datetime import date, datetime, timedelta, timezone as tz
from io import StringIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from django.core.management import call_command
from django.db import connection, connections, transaction, IntegrityError
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.education.models import Student
from apps.availability.models import AvailabilityRule
from apps.education.path_services import DomainError, Conflict
from apps.scheduling.models import (
    PlanningPolicy,
    PlanningRevision,
    ScheduleRun,
    SchedulePlan,
    PlanningSnapshot,
    DemandUnit,
)
from apps.scheduling.runs import submit_run, process_run
from apps.scheduling.source import compile_source, DataNotReady
from apps.calendar.models import *
from apps.calendar.services import publish_plan, change_lesson

pytestmark = pytest.mark.django_db(transaction=True)
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
        username="calendar-center",
        email="calendar-center@example.invalid",
        password="synthetic-test-password",
    )
    call_command(
        "seed_planning_demo", actor=actor.username, days="0", stdout=StringIO()
    )
    client = APIClient()
    client.force_authenticate(actor)
    return actor, PlanningPolicy.objects.get(), client


def plan_for(center, key="run", mode="STRICT"):
    actor, policy, _ = center
    response = submit_run(
        actor, policy.id, WEEK, PlanningRevision.objects.get(pk=1).revision, mode, key
    )
    assert process_run(response["run_id"]) == "SUCCEEDED"
    return SchedulePlan.objects.get(run_id=response["run_id"])


def command_for(plan, **changes):
    return {
        "expected_version": 1,
        "expected_revision": plan.run.snapshot.revision,
        "accept_unassigned_demand_keys": [],
        "reason": "Synthetic publication",
        "confirm_experimental": True,
        **changes,
    }


def publish(center, plan=None, key="publish"):
    plan = plan or plan_for(center)
    return publish_plan(center[0], plan.id, command_for(plan), key)


def test_atomic_six_lessons_all_bookings(center):
    plan = plan_for(center)
    before = PlanningRevision.objects.get(pk=1).revision
    result = publish(center, plan)
    assert len(result["created_lesson_ids"]) == 6 and result["revision"] == before + 1
    assert (
        LessonOccurrence.objects.count() == 6
        and LessonParticipant.objects.count() == 12
    )
    assert ResourceBooking.objects.count() == 24 and CalendarEvent.objects.count() == 6
    assert CalendarAudit.objects.count() == 6 and Publication.objects.count() == 1
    assert result["notifications_sent"] is False


def test_replay_exact_response_single_effect(center):
    plan = plan_for(center)
    first = publish(center, plan)
    assert publish(center, plan) == first and Publication.objects.count() == 1
    assert CalendarEvent.objects.count() == 6


def test_same_key_different_body_rejected(center):
    plan = plan_for(center)
    publish(center, plan)
    with pytest.raises(Conflict):
        publish_plan(
            center[0], plan.id, command_for(plan, reason="Different"), "publish"
        )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"expected_revision": 0}, "STALE_INPUT"),
        ({"expected_version": 2}, "VERSION_CONFLICT"),
        (
            {"accept_unassigned_demand_keys": ["unassigned-invented"]},
            "PARTIAL_ACCEPTANCE_REQUIRED",
        ),
    ],
)
def test_publish_guards_no_writes(center, changes, code):
    plan = plan_for(center)
    with pytest.raises(DomainError) as error:
        publish_plan(center[0], plan.id, command_for(plan, **changes), "guard")
    assert error.value.detail["code"] == code
    assert (
        LessonOccurrence.objects.count()
        == CalendarEvent.objects.count()
        == Publication.objects.count()
        == 0
    )


def test_stale_plan_after_input_change(center):
    plan = plan_for(center)
    Student.objects.all().update(display_name="Synthetic change")
    with pytest.raises(Conflict):
        publish(center, plan)
    assert ResourceBooking.objects.count() == 0


def test_snapshot_revalidated_not_trusting_assignment_status(center, monkeypatch):
    plan = plan_for(center)
    monkeypatch.setattr("apps.calendar.services.input_hash", lambda value: "tampered")
    with pytest.raises(Conflict):
        publish(center, plan)
    assert LessonOccurrence.objects.count() == 0


def test_plan_result_integrity(center):
    plan = plan_for(center)
    plan.run.result["assignments"][0]["end"] += 15
    plan.run.save()
    with pytest.raises(DomainError) as error:
        publish(center, plan)
    assert error.value.detail["code"] == "PLAN_HASH_MISMATCH"


def test_failure_mid_batch_rolls_back_all_effects(center, monkeypatch):
    from apps.calendar.services import save_bookings

    plan = plan_for(center)
    before = PlanningRevision.objects.get(pk=1).revision
    calls = []

    def fail(lesson):
        calls.append(lesson.id)
        if len(calls) == 3:
            raise RuntimeError("Synthetic failure")
        return save_bookings(lesson)

    monkeypatch.setattr("apps.calendar.services.save_bookings", fail)
    with pytest.raises(RuntimeError):
        publish(center, plan)
    assert (
        LessonOccurrence.objects.count()
        == ResourceBooking.objects.count()
        == CalendarAudit.objects.count()
        == CalendarEvent.objects.count()
        == Publication.objects.count()
        == 0
    )
    assert PlanningRevision.objects.get(pk=1).revision == before


def test_independent_validator_rejects_before_creation(center, monkeypatch):
    plan = plan_for(center)
    monkeypatch.setattr(
        "apps.calendar.services.validate_assignments",
        lambda *a, **k: {"status": "FAILED", "violations": []},
    )
    with pytest.raises(DomainError) as error:
        publish(center, plan)
    assert (
        error.value.detail["code"] == "CALENDAR_VALIDATION_FAILED"
        and Publication.objects.count() == 0
    )


def test_second_plan_same_revision_becomes_stale(center):
    first = plan_for(center, "first")
    second = plan_for(center, "second")
    publish(center, first)
    with pytest.raises(Conflict):
        publish(center, second, "publish-second")
    assert LessonOccurrence.objects.count() == 6


def test_published_lessons_reconciled_locked_not_duplicated(center):
    publish(center)
    data, _ = compile_source(center[1], WEEK, "STRICT")
    assert len(data["units"]) == 6 and all(
        u["locked_assignment"] for u in data["units"]
    )
    plan = plan_for(center, "with-calendar")
    with pytest.raises(DomainError) as error:
        publish(center, plan, "again")
    assert error.value.detail["code"] == "NO_NEW_ASSIGNMENTS"
    assert DemandUnit.objects.count() == 6 and LessonOccurrence.objects.count() == 6


def test_unavailable_published_lesson_never_disappears(center):
    publish(center)
    AvailabilityRule.objects.all().update(status="REVOKED")
    with pytest.raises(DataNotReady):
        compile_source(center[1], WEEK, "STRICT")
    assert (
        LessonOccurrence.objects.filter(state="PUBLISHED").count() == 6
        and ResourceBooking.objects.count() == 24
    )


def test_cancel_frees_only_own_bookings_retains_history(center):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    key = "cancel"
    body = {"expected_version": lesson.version, "reason": "Synthetic cancellation"}
    response = change_lesson(center[0], lesson.id, "cancel", body, key)
    assert response["state"] == "CANCELLED" and response["recovery_created"] is False
    assert (
        ResourceBooking.objects.count() == 20
        and LessonParticipant.objects.count() == 12
    )
    assert change_lesson(center[0], lesson.id, "cancel", body, key) == response
    assert CalendarEvent.objects.count() == 7


def test_cancel_reopens_same_canonical_unit(center):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    change_lesson(
        center[0],
        lesson.id,
        "cancel",
        {"expected_version": 1, "reason": "Synthetic"},
        "cancel",
    )
    data, _ = compile_source(center[1], WEEK, "STRICT")
    assert sum(not u["locked_assignment"] for u in data["units"]) == 1
    plan = plan_for(center, "after-cancel")
    result = publish(center, plan, "replacement")
    assert (
        len(result["created_lesson_ids"]) == 1 and len(result["kept_lesson_ids"]) == 5
    )
    assert (
        DemandUnit.objects.count() == 6
        and LessonOccurrence.objects.count() == 7
        and ResourceBooking.objects.count() == 24
    )


def test_move_keeps_identity_and_moves_bookings_atomically(center):
    publish(center)
    # Build extra approved Tuesday windows to guarantee a free, valid move.
    from apps.scheduling.models import ServiceWindow
    from django.db.models import QuerySet

    for rule in list(AvailabilityRule.objects.filter(weekday=0)):
        rule.pk = None
        rule._state.adding = True
        rule.weekday = 1
        rule.version = 1
        rule.save()
    row = ServiceWindow.objects.get(weekday=0)
    row.pk = None
    row._state.adding = True
    row.weekday = 1
    row.version = 1
    row.save()
    lesson = LessonOccurrence.objects.order_by("start_at").first()
    old = lesson.start_at
    target = old + timedelta(days=1)
    response = change_lesson(
        center[0],
        lesson.id,
        "reschedule",
        {"expected_version": 1, "reason": "Synthetic move", "start_at": target},
        "move",
    )
    lesson.refresh_from_db()
    assert lesson.id == response["id"] or str(lesson.id) == response["id"]
    assert lesson.start_at == target and lesson.version == 2
    assert (
        all(b.start_at == target for b in lesson.bookings.all())
        and ResourceBooking.objects.count() == 24
    )
    assert (
        CalendarAudit.objects.filter(lesson=lesson, operation="RESCHEDULE").count() == 1
    )


@pytest.mark.parametrize(
    "operation,body,code",
    [
        ("cancel", {"expected_version": 0, "reason": "Synthetic"}, "VERSION_CONFLICT"),
        (
            "reschedule",
            {
                "expected_version": 1,
                "reason": "Synthetic",
                "start_at": datetime(2026, 10, 13, 10, tzinfo=tz.utc),
            },
            "SAME_WEEK_REQUIRED",
        ),
        (
            "reschedule",
            {
                "expected_version": 1,
                "reason": "Synthetic",
                "start_at": datetime(2026, 9, 1, 10, tzinfo=tz.utc),
            },
            "PAST_LESSON",
        ),
    ],
)
def test_invalid_change_rollback(center, operation, body, code):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    before = (lesson.start_at, lesson.version, CalendarEvent.objects.count())
    with pytest.raises(DomainError) as error:
        change_lesson(center[0], lesson.id, operation, body, "change")
    assert error.value.detail["code"] == code
    lesson.refresh_from_db()
    assert (lesson.start_at, lesson.version, CalendarEvent.objects.count()) == before
    assert ResourceBooking.objects.count() == 24


def test_move_collision_never_changes_calendar(center):
    publish(center)
    lessons = list(LessonOccurrence.objects.order_by("start_at"))
    first, other = next(
        (a, b)
        for a in lessons
        for b in lessons
        if a.id != b.id and a.tutor_id == b.tutor_id
    )
    before = first.start_at
    with pytest.raises(DomainError):
        change_lesson(
            center[0],
            first.id,
            "reschedule",
            {"expected_version": 1, "reason": "Conflict", "start_at": other.start_at},
            "move-conflict",
        )
    first.refresh_from_db()
    assert first.start_at == before and first.version == 1


def test_move_rejection_reports_specific_codes(center):
    publish(center)
    lessons = list(LessonOccurrence.objects.order_by("start_at"))
    first, other = next(
        (a, b)
        for a in lessons
        for b in lessons
        if a.id != b.id and a.tutor_id == b.tutor_id
    )
    with pytest.raises(DomainError) as error:
        change_lesson(
            center[0],
            first.id,
            "reschedule",
            {"expected_version": 1, "reason": "Conflict", "start_at": other.start_at},
            "move-overlap",
        )
    assert error.value.detail["code"] == "CALENDAR_VALIDATION_FAILED"
    assert "RESOURCE_OVERLAP" in error.value.detail["violations"]
    with pytest.raises(DomainError) as error:
        change_lesson(
            center[0],
            first.id,
            "reschedule",
            {
                "expected_version": 1,
                "reason": "Tuesday",
                "start_at": first.start_at + timedelta(days=1),
            },
            "move-tuesday",
        )
    codes = error.value.detail["violations"]
    assert {"TUTOR_AVAILABILITY", "SERVICE_CLOSED"} <= set(codes)
    assert "RESOURCE_OVERLAP" not in codes


def test_reschedule_options_read_only(center):
    publish(center)
    lesson = LessonOccurrence.objects.order_by("start_at").first()
    client = center[2]
    before = (
        PlanningRevision.objects.get(pk=1).revision,
        CalendarEvent.objects.count(),
        CommandReceiptCount(),
    )
    url = f"/api/v1/occurrences/{lesson.id}/reschedule-options/"
    same = client.get(url + "?date=2026-10-05")
    assert same.status_code == 200 and len(same.data["options"]) == 96
    by_start = {datetime.fromisoformat(o["start_at"]): o for o in same.data["options"]}
    assert by_start[lesson.start_at]["ok"] is True
    early = by_start[datetime(2026, 10, 5, 6, tzinfo=tz.utc)]  # 08:00 locali
    assert not early["ok"] and "TUTOR_AVAILABILITY" in early["codes"]
    tuesday = client.get(url + "?date=2026-10-06").data["options"]
    assert not any(o["ok"] for o in tuesday)
    outside = client.get(url + "?date=2026-10-12").data["options"]
    assert all(o["codes"] == ["SAME_WEEK_REQUIRED"] for o in outside)
    assert client.get(url + "?date=ieri").status_code == 400
    lesson.refresh_from_db()
    assert lesson.version == 1
    assert (
        PlanningRevision.objects.get(pk=1).revision,
        CalendarEvent.objects.count(),
        CommandReceiptCount(),
    ) == before
    family = Account.objects.create_user(
        username="options-family", email="options-family@example.invalid"
    )
    other = APIClient()
    other.force_authenticate(family)
    assert other.get(url + "?date=2026-10-05").status_code == 403


def CommandReceiptCount():
    from apps.governance.models import CommandReceipt

    return CommandReceipt.objects.count()


def test_existing_lesson_started_cannot_be_changed(center, monkeypatch):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    monkeypatch.setattr(
        "apps.calendar.services.now", lambda: lesson.start_at + timedelta(minutes=1)
    )
    with pytest.raises(DomainError):
        change_lesson(
            center[0],
            lesson.id,
            "cancel",
            {"expected_version": 1, "reason": "Synthetic"},
            "past",
        )
    assert ResourceBooking.objects.count() == 24


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/calendar/capabilities",
        "/api/v1/calendar/?from=2026-10-05&until=2026-10-12",
    ],
)
def test_family_cannot_read_experimental_calendar(center, endpoint):
    family = Account.objects.create_user(
        username="calendar-family", email="family@example.invalid"
    )
    client = APIClient()
    client.force_authenticate(family)
    assert client.get(endpoint).status_code == 403


def test_calendar_api_range_and_revision(center):
    publish(center)
    client = center[2]
    assert client.get("/api/v1/calendar/").status_code == 400
    result = client.get("/api/v1/calendar/?from=2026-10-05&until=2026-10-12")
    assert result.status_code == 200 and len(result.data["results"]) == 6
    assert (
        result.data["experimental"]
        and result.data["revision"] == PlanningRevision.objects.get(pk=1).revision
    )
    assert len(result.data["results"][0]["participants"]) == 2


def test_api_publish_replay_and_plan_state(center):
    plan = plan_for(center)
    client = center[2]
    url = f"/api/v1/schedule-plans/{plan.id}/publish/"
    body = command_for(plan)
    response = client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="api-publish")
    assert response.status_code == 200, response.data
    assert (
        client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="api-publish").data
        == response.data
    )
    plans = client.get("/api/v1/schedule-plans/").data["results"]
    assert (
        plans[0]["state"] == "PUBLISHED"
        and plans[0]["publishable"] is False
    )


@pytest.mark.parametrize(
    "change",
    [{"unexpected": "extra"}, {"expected_version": True}, {"expected_revision": True}],
)
def test_api_publish_closed_payload(center, change):
    plan = plan_for(center)
    body = {**command_for(plan), **change}
    result = center[2].post(
        f"/api/v1/schedule-plans/{plan.id}/publish/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="bad",
    )
    assert result.status_code == 400 and Publication.objects.count() == 0


def test_api_missing_publish_key(center):
    plan = plan_for(center)
    result = center[2].post(
        f"/api/v1/schedule-plans/{plan.id}/publish/", command_for(plan), format="json"
    )
    assert result.status_code == 422 and Publication.objects.count() == 0


def test_normal_sqlite_publication_disabled(center, settings, monkeypatch):
    plan = plan_for(center)
    settings.CALENDAR_ALLOW_SQLITE_TESTS = False
    monkeypatch.setattr("apps.calendar.services.supported", lambda: False)
    monkeypatch.setattr("api.calendar.supported", lambda: False)
    assert center[2].get("/api/v1/calendar/capabilities").data["enabled"] is False
    assert (
        center[2]
        .post(
            f"/api/v1/schedule-plans/{plan.id}/publish/",
            command_for(plan),
            format="json",
        )
        .status_code
        == 503
    )


def test_production_calendar_guard(center, settings):
    # P0: il calendario dipende dal flag di funzione, non da DEBUG.
    settings.DEBUG = False
    settings.FEATURE_CALENDAR = False
    assert (
        center[2].get("/api/v1/calendar/?from=2026-10-05&until=2026-10-12").status_code
        == 503
    )
    assert (
        center[2].get("/api/v1/calendar/capabilities").data["production_enabled"]
        is False
    )


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires actual PostgreSQL GiST/constraint triggers",
)
def test_postgres_exclusion_rejects_raw_collision(center):
    publish(center)
    booking = ResourceBooking.objects.filter(resource__kind="TUTOR").first()
    other = LessonOccurrence.objects.exclude(tutor_id=booking.resource.tutor_id).first()
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            ResourceBooking.objects.create(
                lesson=other,
                resource=booking.resource,
                start_at=booking.start_at,
                end_at=booking.end_at,
            )
    assert error.value.__cause__.sqlstate == "23P01"


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires actual PostgreSQL deferred trigger",
)
@pytest.mark.parametrize(
    "corruption",
    [
        "missing_booking",
        "participant_deleted",
        "wrong_buffer",
        "wrong_booking_end",
        "resource_rebound",
    ],
)
def test_postgres_trigger_rejects_corruption(center, corruption):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            if corruption == "missing_booking":
                lesson.bookings.first().delete()
            elif corruption == "participant_deleted":
                lesson.participants.first().delete()
            elif corruption == "wrong_buffer":
                LessonOccurrence.objects.filter(pk=lesson.pk).update(
                    tutor_occupied_until=lesson.end_at + timedelta(minutes=1)
                )
            elif corruption == "wrong_booking_end":
                row = lesson.bookings.filter(resource__kind="STUDENT").first()
                ResourceBooking.objects.filter(pk=row.pk).update(
                    end_at=row.end_at - timedelta(minutes=1)
                )
            else:
                from apps.education.models import Tutor

                booked = lesson.bookings.filter(resource__kind="TUTOR").first().resource
                other = Tutor.objects.exclude(pk=booked.tutor_id).first()
                CalendarResource.objects.filter(pk=booked.pk).update(tutor_id=other.pk)
    assert error.value.__cause__.sqlstate == "23514"
    assert (
        ResourceBooking.objects.count() == 24
        and LessonParticipant.objects.count() == 12
    )


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires independent PostgreSQL connections and real row locks",
)
def test_concurrent_publications_single_commit(center):
    first = plan_for(center, "race1")
    second = plan_for(center, "race2")

    barrier = Barrier(2)

    def worker(plan_id, body, key):
        try:
            actor = Account.objects.get(pk=center[0].pk)
            barrier.wait(timeout=10)
            publish_plan(actor, plan_id, body, key)
            return "OK"
        except DomainError as error:
            return str(error.detail["code"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(worker, first.id, command_for(first), "pubrace1"),
                executor.submit(worker, second.id, command_for(second), "pubrace2"),
            ]
        ]
    assert sorted(results) == ["OK", "STALE_INPUT"]
    assert (
        Publication.objects.count() == 1
        and LessonOccurrence.objects.count() == 6
        and ResourceBooking.objects.count() == 24
    )


def partial_plan(center):
    from apps.education.models import TeachingRequest, LearningPath
    from apps.availability.models import AvailabilityDeclaration

    path = LearningPath.objects.first()
    other = Student.objects.first()
    student = Student.objects.create(
        display_name="Optional synthetic student",
        family=other.family,
        level=path.level,
        active=True,
    )
    AvailabilityDeclaration.objects.create(student=student, state="DECLARED_NONE")
    TeachingRequest.objects.create(
        student=student,
        subject=path.required_subjects.first(),
        duration_minutes=120,
        sessions_per_week=1,
        period_start=path.period_start,
        period_end=path.period_end,
        priority="P2",
        mandatory=False,
        mode="IN_PERSON",
    )
    return plan_for(center, "partial", "COVERAGE")


def test_partial_requires_exact_acceptance(center):
    plan = partial_plan(center)
    assigned = {a["demand_key"] for a in plan.assignments}
    missing = [
        u["demand_key"]
        for u in plan.run.snapshot.data["units"]
        if u["demand_key"] not in assigned
    ]
    assert missing
    with pytest.raises(DomainError) as error:
        publish_plan(center[0], plan.id, command_for(plan), "bad-partial")
    assert error.value.detail["code"] == "PARTIAL_ACCEPTANCE_REQUIRED"
    result = publish_plan(
        center[0],
        plan.id,
        command_for(
            plan,
            accept_unassigned_demand_keys=missing,
            reason="Synthetic partial accepted",
        ),
        "partial-publish",
    )
    assert (
        len(result["created_lesson_ids"]) == len(assigned)
        and Publication.objects.get().accepted_unassigned == missing
    )


def test_partial_acceptance_cannot_override_mandatory(center):
    import json, hashlib

    response = submit_run(
        center[0],
        center[1].id,
        WEEK,
        PlanningRevision.objects.get(pk=1).revision,
        "COVERAGE",
        "malicious-proposal",
    )
    run = ScheduleRun.objects.get(pk=response["run_id"])
    from apps.scheduling.solver import simulate

    result = simulate(run.snapshot.data)
    removed = result["assignments"].pop()
    result["is_complete"] = False
    run.result = result
    run.status = "SUCCEEDED"
    run.save()
    plan = SchedulePlan.objects.create(
        run=run,
        state="VALIDATED",
        assignments=result["assignments"],
        result_hash=hashlib.sha256(
            json.dumps(result, sort_keys=True).encode()
        ).hexdigest(),
    )
    with pytest.raises(DomainError) as error:
        publish_plan(
            center[0],
            plan.id,
            command_for(plan, accept_unassigned_demand_keys=[removed["demand_key"]]),
            "mandatory-override",
        )
    assert (
        error.value.detail["code"] == "CALENDAR_VALIDATION_FAILED"
        and LessonOccurrence.objects.count() == 0
    )


def test_stale_actor_object_cannot_cancel_after_revocation(center):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    actor = center[0]
    Account.objects.filter(pk=actor.pk).update(is_active=False)
    with pytest.raises(DomainError) as error:
        change_lesson(
            actor,
            lesson.id,
            "cancel",
            {"expected_version": 1, "reason": "Synthetic"},
            "revoked",
        )
    assert (
        error.value.detail["code"] == "FORBIDDEN"
        and ResourceBooking.objects.count() == 24
    )


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Requires real PostgreSQL locks and separate connections",
)
def test_concurrent_cancellation_single_version_change(center):
    publish(center)
    lesson = LessonOccurrence.objects.first()
    barrier = Barrier(2)

    def worker(key):
        try:
            actor = Account.objects.get(pk=center[0].pk)
            barrier.wait(timeout=10)
            change_lesson(
                actor,
                lesson.id,
                "cancel",
                {"expected_version": 1, "reason": "Concurrent synthetic cancellation"},
                key,
            )
            return "OK"
        except DomainError as error:
            return str(error.detail["code"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(worker, "race-cancel-a"),
                executor.submit(worker, "race-cancel-b"),
            ]
        ]
    assert sorted(results) == ["OK", "VERSION_CONFLICT"]
    lesson.refresh_from_db()
    assert lesson.version == 2 and lesson.state == "CANCELLED"
    assert ResourceBooking.objects.count() == 20 and CalendarEvent.objects.count() == 7
