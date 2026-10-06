"""Macchina a stati del piano (GAP-E07) e proposta periodica dell'orizzonte (GAP-E06).

SchedulePlan (apps.scheduling) resta immutabile e non viene modificato: lo stato
operativo vive in PlanReview. Transizioni: DRAFT→VALIDATED|STALE|REJECTED,
VALIDATED→PUBLISHED|STALE|REJECTED; PUBLISHED, STALE e REJECTED sono terminali.
"""

from datetime import timedelta
from django.conf import settings
from django.db import transaction
from apps.education.path_services import DomainError as BaseDomainError
from apps.scheduling.models import SchedulePlan, PlanningPolicy, PlanningRevision
from apps.scheduling.source import DataNotReady
from .models import PlanReview, HorizonProposal, ConflictCase, Publication
from .context import week_of, request_id_of, unit_key, active_week
from .commands import (
    Command,
    audit,
    event,
    require_reason,
    check_version,
    now,
    DomainError,
)
from .services import verify_plan, current_dto

STALE_CODES = {"STALE_INPUT", "UNTRACKED_INPUT_CHANGE", "SNAPSHOT_CHANGED"}


def derived_state(review, plan, revision):
    if hasattr(plan, "publication") or Publication.objects.filter(plan=plan).exists():
        return "PUBLISHED"
    if (
        review.state in ("DRAFT", "VALIDATED")
        and plan.run.snapshot.revision != revision
    ):
        return "STALE"
    if review.state == "VALIDATED" and review.validated_revision != revision:
        return "STALE"
    return review.state


def review_summary(review, revision):
    plan = review.plan
    return {
        "plan_id": str(plan.id),
        "state": derived_state(review, plan, revision),
        "stored_state": review.state,
        "version": review.version,
        "validated_revision": review.validated_revision,
        "snapshot_revision": plan.run.snapshot.revision,
        "current_revision": revision,
        "report": review.report,
        "transitions": sorted(PlanReview.TRANSITIONS[review.state]),
    }


def transition(actor, review, state, reason, report=None, revision=None):
    if state not in PlanReview.TRANSITIONS[review.state]:
        raise DomainError(
            "PLAN_STATE_INVALID", f"Transizione {review.state}→{state} non ammessa"
        )
    before = {"state": review.state, "version": review.version}
    review.state = state
    review.report = report or review.report
    review.version += 1
    review.updated_by = actor
    if state == "VALIDATED":
        review.validated_revision = revision
    review.save()
    audit(
        actor,
        "PLAN_" + state,
        reason,
        obj=review,
        before=before,
        after={
            "state": state,
            "version": review.version,
            "plan_id": str(review.plan_id),
        },
    )
    event(
        "PLAN_" + state,
        f"plan:{review.plan_id}:v{review.version}",
        {"plan_id": str(review.plan_id), "state": state},
    )


def lock_review(plan_id):
    plan = (
        SchedulePlan.objects.select_for_update(of=("self",))
        .select_related("run__snapshot__policy")
        .filter(pk=plan_id)
        .first()
    )
    if not plan:
        raise DomainError("NOT_FOUND", "Proposta inesistente")
    review, _ = PlanReview.objects.select_for_update().get_or_create(plan=plan)
    if (
        review.state in ("DRAFT", "VALIDATED")
        and Publication.objects.filter(plan=plan).exists()
    ):
        review.state = "PUBLISHED"
        review.save()
    return plan, review


@transaction.atomic
def validate_plan(actor, plan_id, command, key):
    """Validazione esplicita: rivalida sui dati correnti e registra l'esito."""
    cmd = Command(
        actor, "calendar-plan-validate", key, {"plan_id": str(plan_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    plan, review = lock_review(plan_id)
    revision = cmd.revision.revision
    if review.state not in ("DRAFT", "VALIDATED"):
        raise DomainError("PLAN_STATE_INVALID", f"Proposta in stato {review.state}")
    if (
        command["expected_revision"] != revision
        or plan.run.snapshot.revision != revision
    ):
        transition(
            cmd.actor,
            review,
            "STALE",
            "Revisione degli input cambiata",
            {"code": "STALE_INPUT"},
        )
        return cmd.done({**review_summary(review, revision), "experimental": True})
    try:
        checked = verify_plan(plan, revision)
    except BaseDomainError as error:
        code = str(error.detail["code"])
        target = "STALE" if code in STALE_CODES else "REJECTED"
        report = {"code": code, "message": str(error.detail.get("message", ""))}
        if "violations" in error.detail:
            report["violations"] = error.detail["violations"]
        transition(cmd.actor, review, target, "Validazione esplicita fallita", report)
        return cmd.done({**review_summary(review, revision), "experimental": True})
    report = {
        "code": "PASSED",
        "new_assignments": len(checked["new"]),
        "kept_lessons": len(checked["existing"]),
        "unassigned_demand_keys": sorted(checked["missing"]),
    }
    if review.state == "VALIDATED":
        review.report, review.validated_revision = report, revision
        review.version += 1
        review.save()
    else:
        transition(
            cmd.actor,
            review,
            "VALIDATED",
            "Validazione esplicita superata",
            report,
            revision,
        )
    return cmd.done({**review_summary(review, revision), "experimental": True})


@transaction.atomic
def reject_plan(actor, plan_id, command, key):
    cmd = Command(
        actor, "calendar-plan-reject", key, {"plan_id": str(plan_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    plan, review = lock_review(plan_id)
    check_version(review, command["expected_version"])
    reason = require_reason(command)
    transition(cmd.actor, review, "REJECTED", reason, {"code": "REJECTED_BY_CENTER"})
    return cmd.done(
        {**review_summary(review, cmd.revision.revision), "experimental": True}
    )


def plan_lifecycle(plan):
    review = PlanReview.objects.filter(plan=plan).first() or PlanReview(plan=plan)
    revision = PlanningRevision.objects.get_or_create(pk=1)[0].revision
    from .models import CalendarAudit

    history = []
    if review.pk:
        history = [
            {
                "operation": a.operation,
                "at": a.created_at.isoformat(),
                "actor_id": str(a.actor_id) if a.actor_id else a.system_actor,
                "before": a.before,
                "after": a.after,
                "reason": a.reason,
            }
            for a in CalendarAudit.objects.filter(
                object_type="PlanReview", object_id=review.pk
            ).order_by("created_at")
        ]
    return {
        **review_summary(review, revision),
        "history": history,
        "experimental": True,
    }


# --- GAP-E06: estensione dell'orizzonte ------------------------------------------


def month_weeks(today=None):
    """Lunedì delle settimane che toccano il mese solare successivo (D06)."""
    from zoneinfo import ZoneInfo

    local = (today or now()).astimezone(ZoneInfo("Europe/Rome")).date()
    first = (local.replace(day=1) + timedelta(days=32)).replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    week = first - timedelta(days=first.weekday())
    weeks = []
    while week <= last:
        weeks.append(week)
        week += timedelta(days=7)
    return weeks


def horizon_weeks(count=None, today=None):
    if count is None and getattr(settings, "CALENDAR_HORIZON_MODE", "WEEKS") == "MONTH":
        return month_weeks(today)
    count = count or getattr(settings, "CALENDAR_HORIZON_WEEKS", 6)
    first = week_of(today or now()) + timedelta(days=7)
    return [first + timedelta(days=7 * i) for i in range(count)]


def propose_horizon(actor, policy_id=None, weeks=None, mode="STRICT"):
    """Per ogni settimana dell'orizzonte: rileva conflitti, poi crea un run di bozza.

    Bloccata se esistono pratiche aperte fino a quella settimana. Idempotente per
    (settimana, revisione). Non pubblica mai: la pubblicazione resta del centro."""
    from .conflicts import detect_conflicts
    from apps.scheduling.runs import submit_run

    weeks = list(weeks or horizon_weeks())
    policy = (
        PlanningPolicy.objects.get(pk=policy_id)
        if policy_id
        else PlanningPolicy.objects.filter(approved_for_exploration=True)
        .order_by("id")
        .first()
    )
    if policy is None:
        raise DomainError(
            "POLICY_MISSING", "Nessuna policy approvata per l'esplorazione"
        )
    with transaction.atomic():
        detect_conflicts(actor)
    results = []
    for week in weeks:
        with transaction.atomic():
            revision = PlanningRevision.objects.get_or_create(pk=1)[0].revision
            existing = HorizonProposal.objects.filter(
                week_start=week, revision=revision
            ).first()
            if existing:
                results.append(existing)
                continue
            blocking = list(
                ConflictCase.objects.filter(state="OPEN", week_start__lte=week)
                .order_by("week_start", "id")
                .values_list("id", "kind", "week_start")
            )
            proposal = HorizonProposal(week_start=week, revision=revision)
            if blocking:
                proposal.state = "BLOCKED"
                proposal.blocking = [
                    {"conflict_id": str(i), "kind": k, "week_start": w.isoformat()}
                    for i, k, w in blocking
                ]
            else:
                try:
                    data = current_dto(policy, week, mode)
                    published = {unit_key(l) for l in active_week(week)}
                    free = [
                        u
                        for u in data["units"]
                        if u["demand_key"] not in published
                        and request_id_of(u["demand_key"])
                    ]
                    if not free:
                        proposal.state = "COVERED"
                    else:
                        response = submit_run(
                            actor,
                            policy.id,
                            week,
                            revision,
                            mode,
                            f"horizon:{week.isoformat()}:r{revision}",
                        )
                        proposal.state = "PROPOSED"
                        proposal.run_id = response["run_id"]
                except (BaseDomainError, DataNotReady) as error:
                    detail = getattr(error, "detail", None)
                    code = (
                        str(detail["code"])
                        if detail
                        else getattr(error, "code", "ERROR")
                    )
                    proposal.state = "BLOCKED"
                    proposal.blocking = [{"code": code}]
            proposal.save()
            results.append(proposal)
    return results


def proposal_summary(row):
    return {
        "week_start": row.week_start.isoformat(),
        "revision": row.revision,
        "state": row.state,
        "run_id": str(row.run_id) if row.run_id else None,
        "blocking": row.blocking,
    }


@transaction.atomic
def horizon_command(actor, command, key):
    """Trigger manuale del job (centro): stessa logica, con ricevuta idempotente."""
    cmd = Command(actor, "calendar-horizon", key, command)
    if cmd.replay:
        return cmd.replay
    weeks = horizon_weeks(command.get("weeks"))
    rows = propose_horizon(cmd.actor, command.get("policy_id"), weeks)
    return cmd.done(
        {
            "proposals": [proposal_summary(r) for r in rows],
            "published": False,
            "experimental": True,
        }
    )
