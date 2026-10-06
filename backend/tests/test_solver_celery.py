"""GAP-D09: soft/hard time limits, broker loss, heartbeat and reconciler.

The in-process tests simulate the prefork outcomes (SoftTimeLimitExceeded,
hard kill = lease expiry without commit).  The real Redis + prefork test runs
only when SOLVER_TEST_REDIS_URL is set (Redis is not available in this CI).
"""

from datetime import date, timedelta
from io import StringIO
import os
import shutil
import subprocess
import sys
import time
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from apps.identity.models import Account
from apps.scheduling import runs
from apps.scheduling.models import (
    PlanningPolicy,
    PlanningRevision,
    ScheduleRun,
    SchedulePlan,
    RunDispatch,
)
from apps.scheduling.contracts import SCHEMA
from apps.scheduling.tasks import execute

WEEK = date(2026, 10, 5)


def test_time_limit_ordering_invariant():
    # Policy (profilo STANDARD): budget <= 30 s (NFR04) < soft 60 < hard 90 < lease 120.
    assert 30 < settings.CELERY_TASK_SOFT_TIME_LIMIT == 60
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT < settings.CELERY_TASK_TIME_LIMIT == 90
    assert settings.CELERY_TASK_TIME_LIMIT < runs.LEASE_SECONDS
    assert runs.run_limits(30) == (60, 90, runs.LEASE_SECONDS)
    # v0.9.4 profilo THOROUGH: stesso invariante scalato sul budget del run.
    budget_max = SCHEMA["properties"]["budget_seconds"]["maximum"]
    assert budget_max == 43200
    for budget in (30.5, settings.PLANNING_THOROUGH_BUDGET_SECONDS, budget_max):
        soft, hard, lease = runs.run_limits(budget)
        assert budget < soft < hard < lease
    assert execute.acks_late and execute.reject_on_worker_lost
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1


@pytest.fixture
def queued(settings, monkeypatch, db):
    settings.DEBUG = True
    settings.EXPERIMENTAL_DB_PLANNING = True
    actor = Account.objects.create_superuser(
        username="celery-center",
        email="celery-center@example.invalid",
        password="synthetic-test-password",
    )
    call_command(
        "seed_planning_demo", actor=actor.username, days="0", stdout=StringIO()
    )
    monkeypatch.setattr("apps.scheduling.runs.dispatch_one", lambda run_id: False)
    policy = PlanningPolicy.objects.get()
    response = runs.submit_run(
        actor,
        policy.id,
        WEEK,
        PlanningRevision.objects.get(pk=1).revision,
        "STRICT",
        "celery-key",
    )
    return ScheduleRun.objects.get(pk=response["run_id"])


def test_soft_time_limit_is_non_conclusive_failure(queued, monkeypatch):
    def soft(dto, progress=None):
        progress("SEARCH")
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(runs, "simulate", soft)
    assert runs.process_run(queued.id) == "FAILED"
    queued.refresh_from_db()
    assert queued.error_code == "SOFT_TIME_LIMIT" and queued.result is None
    assert not SchedulePlan.objects.filter(run=queued).exists()
    assert queued.heartbeat_at is not None


def test_heartbeat_tracks_real_phases(queued, monkeypatch):
    seen = []
    original = runs.simulate

    def spy(dto, progress=None):
        def wrapped(phase):
            progress(phase)
            seen.append(ScheduleRun.objects.get(pk=queued.id).phase)

        return original(dto, progress=wrapped)

    monkeypatch.setattr(runs, "simulate", spy)
    assert runs.process_run(queued.id) == "SUCCEEDED"
    assert seen[:2] == ["PREFLIGHT", "MODEL"] and "VALIDATION" in seen


def test_hard_kill_is_reclaimed_and_fenced(queued, monkeypatch):
    """Hard limit kills the child: no commit, lease expires, reconciler requeues;
    the killed attempt's token can no longer commit."""
    tokens = []

    def killed(dto, progress=None):
        tokens.append(ScheduleRun.objects.get(pk=queued.id).claim_token)
        ScheduleRun.objects.filter(pk=queued.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        runs.reconcile_runs()  # reconciler runs while the old worker is "dead"
        return original(dto, progress=None)

    original = runs.simulate
    monkeypatch.setattr(runs, "simulate", killed)
    status = runs.process_run(queued.id)
    queued.refresh_from_db()
    assert (
        status == "QUEUED" and queued.status == "QUEUED" and queued.claim_token is None
    )
    monkeypatch.setattr(runs, "simulate", original)
    assert runs.process_run(queued.id) == "SUCCEEDED"
    queued.refresh_from_db()
    assert queued.attempts == 2 and queued.claim_token != tokens[0]


def test_attempts_exhausted_after_repeated_kills(queued):
    for _ in range(runs.MAX_ATTEMPTS):
        ScheduleRun.objects.filter(pk=queued.id).update(
            status="RUNNING",
            attempts=ScheduleRun.objects.get(pk=queued.id).attempts + 1,
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )
        runs.reconcile_runs()
    queued.refresh_from_db()
    assert queued.status == "FAILED" and queued.error_code == "ATTEMPTS_EXHAUSTED"


def test_broker_loss_then_recovery(queued, monkeypatch):
    monkeypatch.undo()
    calls = []

    def down(*args, **kwargs):
        raise ConnectionError("broker down")

    monkeypatch.setattr(execute, "apply_async", down)
    assert runs.dispatch_one(queued.id) is False
    dispatch = RunDispatch.objects.get(run=queued)
    assert dispatch.status == "PENDING" and dispatch.error_code == "BROKER_UNAVAILABLE"
    monkeypatch.setattr(execute, "apply_async", lambda *a, **k: calls.append(a))
    assert runs.reconcile_runs() == 1 and calls
    assert RunDispatch.objects.get(run=queued).status == "SENT"


REDIS = os.environ.get("SOLVER_TEST_REDIS_URL")


@pytest.mark.skipif(
    not REDIS or not shutil.which("celery"),
    reason="Richiede Redis reale (SOLVER_TEST_REDIS_URL) e celery CLI",
)
def test_real_prefork_soft_and_hard_limits():
    # config.test_settings forza il broker in memoria: il worker reale usa le settings
    # base, che leggono CELERY_BROKER_URL dall'ambiente.
    env = {
        **os.environ,
        "CELERY_BROKER_URL": REDIS,
        "DJANGO_SETTINGS_MODULE": "config.settings",
    }
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "config",
            # Il worker deve scrivere i risultati (in produzione sono ignorati).
            "--result-backend",
            REDIS,
            "worker",
            "--pool=prefork",
            "--concurrency=1",
            "-Q",
            "probe",
            "--loglevel=WARNING",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
    )
    try:
        # Client dedicato: l'app di progetto è già legata al broker in memoria dei test.
        from celery import Celery

        client = Celery("probe-client", broker=REDIS, backend=REDIS)
        time.sleep(5)
        soft = client.send_task(
            "apps.scheduling.tasks.probe_time_limit",
            args=[5],
            queue="probe",
            soft_time_limit=1,
            time_limit=3,
            ignore_result=False,
        )
        assert soft.get(timeout=30) == "SOFT_TIME_LIMIT"
        hard = client.send_task(
            "apps.scheduling.tasks.probe_time_limit",
            args=[0],
            queue="probe",
            soft_time_limit=1,
            time_limit=2,
            ignore_result=False,
        )
        assert hard.get(timeout=30) == "COMPLETED"
    finally:
        worker.terminate()
        worker.wait(timeout=30)
