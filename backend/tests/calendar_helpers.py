"""Helper condivisi dai test s2-calendario (dati sintetici, demo seed)."""

from uuid import uuid4
from datetime import date, datetime, timedelta, timezone as tz

from apps.availability.models import AvailabilityRule
from apps.calendar.models import LessonOccurrence
from apps.calendar.services import publish_plan
from apps.scheduling.models import PlanningRevision, SchedulePlan, ServiceWindow
from apps.scheduling.runs import process_run, submit_run


def revision():
    return PlanningRevision.objects.get(pk=1).revision


def plan_week(center, week, key):
    actor, policy, _ = center
    response = submit_run(actor, policy.id, week, revision(), "STRICT", key)
    assert process_run(response["run_id"]) == "SUCCEEDED"
    plan = SchedulePlan.objects.filter(run_id=response["run_id"]).first()
    if plan is None:
        from apps.scheduling.models import ScheduleRun

        run = ScheduleRun.objects.get(pk=response["run_id"])
        raise AssertionError(
            {k: v for k, v in vars(run).items() if not k.startswith("_")}
        )
    return plan


def publish_week(center, week, key):
    plan = plan_week(center, week, "run-" + key)
    return publish_plan(
        center[0],
        plan.id,
        {
            "expected_version": 1,
            "expected_revision": plan.run.snapshot.revision,
            "accept_unassigned_demand_keys": [],
            "reason": "Synthetic publication",
            "confirm_experimental": True,
        },
        key,
    )


def add_weekday(weekday):
    """Copia disponibilità e finestre di servizio del lunedì su un altro giorno."""
    for row in list(AvailabilityRule.objects.filter(weekday=0)):
        row.pk = uuid4()
        row._state.adding = True
        row.weekday = weekday
        row.version = 1
        row.save()
    for row in list(ServiceWindow.objects.filter(weekday=0)):
        row.pk = uuid4()
        row._state.adding = True
        row.weekday = weekday
        row.version = 1
        row.save()


def set_now(monkeypatch, moment):
    monkeypatch.setattr("apps.calendar.services.now", lambda: moment)


def utc(*parts):
    return datetime(*parts, tzinfo=tz.utc)


def week_lessons(week, **filters):
    start = datetime.combine(week, datetime.min.time(), tz.utc) - timedelta(hours=2)
    return LessonOccurrence.objects.filter(
        start_at__gte=start, start_at__lt=start + timedelta(days=7), **filters
    ).order_by("start_at", "id")


def post(client, url, body, key):
    return client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)


WEEK2 = date(2026, 10, 12)
