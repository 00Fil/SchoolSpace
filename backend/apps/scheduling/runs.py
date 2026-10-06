"""Durable experimental job commands. No calendar publication command exists."""

from datetime import timedelta
import hashlib, json, uuid
from django.db import transaction
from django.utils import timezone
from apps.identity.models import Account
from apps.identity.policies import is_center
from apps.governance.models import CommandReceipt
from apps.education.path_services import Conflict, DomainError
from .models import (
    PlanningPolicy,
    PlanningSnapshot,
    DemandUnit,
    ScheduleRun,
    RunDispatch,
    SchedulePlan,
    PlanningAudit,
)
from .revision import lock_revision
from .source import compile_source
from .contracts import input_hash
from .solver import simulate
from .environment import runtime_environment
from apps.reasons import reason_or_default

# Ordering invariant (verified in tests): search budget (<=30 s, NFR04) <
# Celery soft limit (60 s) < hard limit (90 s) < lease (120 s).  A hard-killed
# worker is therefore reclaimed only after the kill, never while still running.
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3
# v0.9.4 – profilo THOROUGH (calcolo accurato/notturno): stessi invarianti,
# scalati sul budget dello snapshot: budget < soft < hard < lease.
THOROUGH_MARGIN_SECONDS = 600


def run_limits(budget_seconds):
    """(soft, hard, lease) for one run; standard runs keep 60/90/120 s."""
    from math import ceil

    if budget_seconds <= 30:
        return 60, 90, LEASE_SECONDS
    soft = ceil(budget_seconds) + THOROUGH_MARGIN_SECONDS
    return soft, soft + 60, soft + 120


@transaction.atomic
def submit_run(
    actor,
    policy_id,
    week_start,
    expected_revision,
    mode,
    key,
    unlock=None,
    propose_scope_expansion=False,
    effort="STANDARD",
):
    """``unlock``: [{"lesson_id", "reason"}] authorised by the centre actor for a
    local replan (GAP-D05); each authorisation is audited before the snapshot."""
    if not key or len(key) > 255 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise DomainError(
            "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key obbligatoria e senza spazi"
        )
    revision = lock_revision()
    Account.objects.select_for_update().get(pk=actor.pk)
    command = {
        "policy_id": str(policy_id),
        "horizon_start": str(week_start),
        "expected_revision": expected_revision,
        "mode": mode,
    }
    if effort != "STANDARD":
        command["effort"] = effort
    if unlock:
        command["unlock"] = sorted(
            [{"lesson_id": str(i["lesson_id"]), "reason": i["reason"]} for i in unlock],
            key=lambda i: i["lesson_id"],
        )
        command["propose_scope_expansion"] = bool(propose_scope_expansion)
    body_hash = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()
    receipt = CommandReceipt.objects.filter(
        actor=actor, operation="schedule-db-run", key=key
    ).first()
    if receipt:
        if receipt.body_hash != body_hash:
            raise Conflict("IDEMPOTENCY_CONFLICT", "Stessa chiave con comando diverso")
        return receipt.response
    if revision.revision != expected_revision:
        raise Conflict("STALE_INPUT", "La revisione degli input è cambiata")
    policy = PlanningPolicy.objects.get(pk=policy_id)
    replanning = None
    if unlock:
        ids = [str(item["lesson_id"]) for item in unlock]
        if len(set(ids)) != len(ids):
            raise DomainError(
                "UNLOCK_DUPLICATE",
                "Ogni sblocco richiede una lezione distinta",
            )
        authorizations = {}
        for item in unlock:
            audit = PlanningAudit.objects.create(
                actor=actor,
                operation="authorize_unlock",
                object_id=item["lesson_id"],
                reason=reason_or_default(item.get("reason")),
            )
            authorizations[str(item["lesson_id"])] = f"audit:{audit.id}"
        replanning = {
            "authorizations": authorizations,
            "propose_scope_expansion": propose_scope_expansion,
        }
    dto, specs = compile_source(
        policy, week_start, mode, replanning=replanning, effort=effort
    )
    for request, serial, unit, unit_week in specs:
        DemandUnit.objects.get_or_create(
            request=request,
            week_start=unit_week,
            serial=serial,
            defaults={"demand_key": unit["demand_key"]},
        )
    snapshot = PlanningSnapshot.objects.create(
        revision=revision.revision,
        schema_version=dto["schema_version"],
        horizon_start=week_start,
        horizon_end=week_start + timedelta(days=dto["horizon_days"]),
        policy=policy,
        policy_version=policy.version,
        actor=actor,
        data=dto,
        input_hash=input_hash(dto),
        environment=runtime_environment(),
    )
    run = ScheduleRun.objects.create(snapshot=snapshot, actor=actor)
    RunDispatch.objects.create(run=run)
    PlanningAudit.objects.create(actor=actor, operation="queue_run", object_id=run.id)
    response = {
        "run_id": str(run.id),
        "snapshot_id": str(snapshot.id),
        "status": "QUEUED",
        "revision": revision.revision,
        "poll_url": f"/api/v1/schedule-runs/{run.id}/",
        "publishable": False,
        "effort": effort,
        "budget_seconds": dto["budget_seconds"],
    }
    CommandReceipt.objects.create(
        actor=actor,
        operation="schedule-db-run",
        key=key,
        body_hash=body_hash,
        response=response,
    )
    # DB commit first; broker is transport only. Failure leaves durable PENDING dispatch.
    transaction.on_commit(lambda: dispatch_one(run.id))
    return response


def dispatch_one(run_id):
    run = ScheduleRun.objects.filter(
        pk=run_id, status="QUEUED", cancel_requested=False
    ).first()
    if not run:
        return False
    from .tasks import execute

    try:
        from django.conf import settings

        soft, hard, _ = run_limits(run.snapshot.data["budget_seconds"])
        options, queue = {}, "solver"
        if soft > 60:
            # Run lungo (THOROUGH): limiti scalati e coda dedicata, così non
            # blocca i calcoli rapidi sul worker "solver".
            options = {"soft_time_limit": soft, "time_limit": hard}
            queue = getattr(settings, "PLANNING_THOROUGH_QUEUE", "solver")
        execute.apply_async(args=[str(run.id)], queue=queue, retry=False, **options)
    except Exception:
        RunDispatch.objects.filter(run=run).update(
            status="PENDING",
            error_code="BROKER_UNAVAILABLE",
            last_attempt_at=timezone.now(),
        )
        return False
    dispatch = RunDispatch.objects.get(run=run)
    dispatch.status = "SENT"
    dispatch.error_code = ""
    dispatch.attempts += 1
    dispatch.last_attempt_at = timezone.now()
    dispatch.save()
    return True


@transaction.atomic
def cancel_run(run_id, actor):
    lock_revision()
    run = ScheduleRun.objects.select_for_update().get(pk=run_id)
    if run.status in ("SUCCEEDED", "FAILED", "CANCELLED") or run.cancel_requested:
        return run
    run.cancel_requested = True
    if run.status == "QUEUED":
        run.status = "CANCELLED"
        run.phase = "CANCELLED"
        run.finished_at = timezone.now()
    run.save()
    PlanningAudit.objects.create(actor=actor, operation="cancel_run", object_id=run.id)
    return run


def process_run(run_id):
    with transaction.atomic():
        revision = lock_revision()
        run = (
            ScheduleRun.objects.select_for_update(of=("self",))
            .select_related("snapshot")
            .get(pk=run_id)
        )
        if run.status != "QUEUED":
            return run.status
        if run.cancel_requested or not is_center(run.actor):
            run.status = "CANCELLED"
            run.phase = "CANCELLED"
            run.error_code = "ACTOR_ACCESS_REVOKED" if not is_center(run.actor) else ""
            run.finished_at = timezone.now()
            run.save()
            return run.status
        if run.snapshot.revision != revision.revision:
            run.status = "FAILED"
            run.phase = "FAILED"
            run.error_code = "STALE_INPUT"
            run.finished_at = timezone.now()
            run.save()
            return run.status
        if run.snapshot.environment != runtime_environment():
            run.status = "FAILED"
            run.phase = "FAILED"
            run.error_code = "ENVIRONMENT_CHANGED"
            run.finished_at = timezone.now()
            run.save()
            return run.status
        if input_hash(run.snapshot.data) != run.snapshot.input_hash:
            run.status = "FAILED"
            run.phase = "FAILED"
            run.error_code = "SNAPSHOT_HASH_MISMATCH"
            run.finished_at = timezone.now()
            run.save()
            return run.status
        token = uuid.uuid4()
        run.status = "RUNNING"
        run.phase = "PREFLIGHT"
        run.claim_token = token
        run.attempts += 1
        run.started_at = run.heartbeat_at = timezone.now()
        lease = run_limits(run.snapshot.data["budget_seconds"])[2]
        run.lease_expires_at = timezone.now() + timedelta(seconds=lease)
        run.save()
        dto = run.snapshot.data

    def progress(phase):
        current = ScheduleRun.objects.get(pk=run_id)
        if current.cancel_requested or current.claim_token != token:
            raise InterruptedError("CANCELLED")
        ScheduleRun.objects.filter(
            pk=run_id, claim_token=token, status="RUNNING"
        ).update(phase=phase, heartbeat_at=timezone.now())

    from celery.exceptions import SoftTimeLimitExceeded

    try:
        result = simulate(dto, progress=progress)
        error = ""
    except InterruptedError:
        result = None
        error = "CANCELLED"
    except SoftTimeLimitExceeded:
        # Non-conclusive technical stop: never reported as INFEASIBLE.
        result = None
        error = "SOFT_TIME_LIMIT"
    except Exception:
        result = None
        error = "EXECUTION_FAILED"
    with transaction.atomic():
        revision = lock_revision()
        current = (
            ScheduleRun.objects.select_for_update(of=("self",))
            .select_related("snapshot")
            .get(pk=run_id)
        )
        if current.claim_token != token or current.status != "RUNNING":
            return current.status
        if current.lease_expires_at < timezone.now():
            return "LEASE_EXPIRED"
        if (
            current.cancel_requested
            or not is_center(current.actor)
            or error == "CANCELLED"
        ):
            current.status = "CANCELLED"
            current.phase = "CANCELLED"
        elif error or result["solver_status"] in (
            "MODEL_INVALID",
            "VALIDATION_FAILED",
            "BLOCKED",
        ):
            current.status = "FAILED"
            current.error_code = error or result["solver_status"]
            current.result = result
            current.phase = "FAILED"
        else:
            current.status = "SUCCEEDED"
            current.phase = "COMPLETED"
            current.result = result
            if (
                result["solver_status"] in ("OPTIMAL", "FEASIBLE")
                and result["validation"]["status"] == "PASSED"
            ):
                state = (
                    "VALIDATED"
                    if revision.revision == current.snapshot.revision
                    else "STALE"
                )
                SchedulePlan.objects.get_or_create(
                    run=current,
                    defaults={
                        "state": state,
                        "assignments": result["assignments"],
                        "result_hash": hashlib.sha256(
                            json.dumps(result, sort_keys=True).encode()
                        ).hexdigest(),
                    },
                )
        current.finished_at = timezone.now()
        current.heartbeat_at = timezone.now()
        current.save()
        return current.status


def reconcile_runs():
    # Expired claims are fenced: an old worker cannot commit after a new claim.
    with transaction.atomic():
        lock_revision()
        for run in ScheduleRun.objects.select_for_update().filter(
            status="RUNNING", lease_expires_at__lt=timezone.now()
        ):
            if run.cancel_requested:
                run.status = "CANCELLED"
                run.phase = "CANCELLED"
                run.finished_at = timezone.now()
            elif run.attempts >= MAX_ATTEMPTS:
                run.status = "FAILED"
                run.phase = "FAILED"
                run.error_code = "ATTEMPTS_EXHAUSTED"
                run.finished_at = timezone.now()
            else:
                run.status = "QUEUED"
                run.phase = "QUEUED"
                run.claim_token = None
                run.lease_expires_at = None
            run.save()
    sent = 0
    threshold = timezone.now() - timedelta(seconds=30)
    for run in ScheduleRun.objects.filter(
        status="QUEUED", cancel_requested=False
    ).select_related("dispatch"):
        if (
            run.dispatch.status == "PENDING"
            or run.dispatch.last_attempt_at is None
            or run.dispatch.last_attempt_at < threshold
        ):
            sent += int(dispatch_one(run.id))
    return sent
