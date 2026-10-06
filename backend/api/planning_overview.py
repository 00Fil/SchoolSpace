"""Panoramica della pianificazione per il gestore (v0.9.4).

Sola lettura: compila lo stesso snapshot che userebbe il motore e il catalogo
dei candidati (slot ammissibili per unità), così il centro vede *prima* del
calcolo quali richieste sono ben vincolate, quali hanno poche alternative e
perché una richiesta non è collocabile. Non scrive nulla.
"""

from collections import defaultdict
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from apps.identity.policies import is_center
from apps.education.models import Student, TeachingRequest, Tutor
from apps.scheduling.contracts import InputError
from apps.scheduling.candidates import compile_candidates
from apps.scheduling.models import PlanningPolicy, TutorSkill
from apps.scheduling.revision import lock_revision
from apps.scheduling.source import (
    compile_source,
    DataNotReady,
    thorough_budget,
    thorough_workers,
)


def union_minutes(windows):
    total, end = 0, None
    for start, stop in sorted((w["start"], w["end"]) for w in windows):
        if end is None or start > end:
            total += stop - start
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total


def request_level(req):
    if req.curriculum_block_id:
        return req.curriculum_block.path.level
    return req.student.level if req.student_id else ""


@api_view(["GET"])
def planning_overview(request):
    if not is_center(request.user):
        raise PermissionDenied()
    from .planning_data import gate

    try:
        week = serializers.DateField().run_validation(
            request.query_params.get("horizon_start")
        )
    except serializers.ValidationError:
        return Response({"code": "INVALID_PAYLOAD"}, status=400)
    if week.weekday() != 0:
        return Response(
            {"code": "MONDAY_REQUIRED", "message": "Scegliere un lunedì"}, status=400
        )
    policies = PlanningPolicy.objects.order_by("name", "id")
    policy_id = request.query_params.get("policy_id")
    policy = (
        policies.filter(pk=policy_id).first()
        if policy_id
        else policies.filter(approved_for_exploration=True).first() or policies.first()
    )
    mode = request.query_params.get("mode", "STRICT")
    if mode not in ("STRICT", "COVERAGE"):
        mode = "STRICT"
    weeks = policy.horizon_weeks if policy else 1
    end = week + timedelta(days=7 * weeks)
    rows = list(
        TeachingRequest.objects.filter(period_start__lt=end, period_end__gte=week)
        .exclude(status="WITHDRAWN")
        .select_related("student", "subject", "curriculum_block__path", "group")
        .prefetch_related("preferred_tutors", "participants__student")
        .order_by("status", "student__display_name", "subject__name", "id")
    )
    skills = list(
        TutorSkill.objects.filter(
            approved=True, valid_from__lt=end, valid_until__gte=week, tutor__active=True
        )
        .filter(Q(tutor__account__isnull=True) | Q(tutor__account__is_active=True))
        .select_related("tutor")
    )
    tutor_names = {str(t.id): t.display_name for t in Tutor.objects.all()}
    requests = []
    for req in rows:
        level = request_level(req)
        competent = sorted(
            {
                str(s.tutor_id)
                for s in skills
                if s.subject_id == req.subject_id
                and s.level == level
                and s.mode == req.mode
            },
            key=lambda i: tutor_names.get(i, i),
        )
        chosen = [str(t.id) for t in req.preferred_tutors.all()]
        problems = []
        if not req.mode:
            problems.append("REQUEST_MODE_MISSING")
        if not level.strip():
            problems.append("LEVEL_MISSING")
        if not competent:
            problems.append("REQUEST_SKILLS_MISSING")
        if req.tutor_choice == "REQUIRED" and not set(chosen) & set(competent):
            problems.append("REQUIRED_TUTOR_UNAVAILABLE")
        if req.tutor_choice == "PREFERRED" and not set(chosen) & set(competent):
            problems.append("PREFERRED_TUTOR_NOT_COMPETENT")
        if req.kind == "SERIES" and not chosen:
            problems.append("SERIES_TUTOR_MISSING")
        if req.curriculum_block_id:
            name = ", ".join(
                p.student.display_name for p in req.participants.all()
            ) or (req.group.name if req.group_id else "")
        else:
            name = req.student.display_name if req.student_id else ""
        requests.append(
            {
                "id": str(req.id),
                "status": req.status,
                "origin": req.origin,
                "student_id": str(req.student_id) if req.student_id else None,
                "student_name": name,
                "subject": str(req.subject_id),
                "subject_name": req.subject.name,
                "level": level,
                "mode": req.mode,
                "duration_minutes": req.duration_minutes,
                "sessions_per_week": req.sessions_per_week,
                "kind": req.kind,
                "fixed_time": req.fixed_time,
                "priority": req.priority,
                "mandatory": req.mandatory,
                "period_start": req.period_start,
                "period_end": req.period_end,
                "tutor_choice": req.tutor_choice,
                "preferred_tutors": [
                    {"id": i, "display_name": tutor_names.get(i, i)} for i in chosen
                ],
                "competent_tutors": [
                    {"id": i, "display_name": tutor_names.get(i, i)} for i in competent
                ],
                "notes": req.notes,
                "derived": bool(req.curriculum_block_id),
                "problems": problems,
            }
        )
    counts = defaultdict(int)
    for r in requests:
        counts[r["status"]] += 1
    out = {
        "horizon_start": week,
        "horizon_end": end,
        "planning_enabled": gate(request),
        "policy": policy
        and {
            "id": str(policy.id),
            "name": policy.name,
            "budget_seconds": policy.budget_seconds,
            "horizon_weeks": policy.horizon_weeks,
            "objective_order": policy.objective_order or ["P0", "P1", "P2"],
            "approved_for_exploration": policy.approved_for_exploration,
        },
        "thorough": {
            "budget_seconds": thorough_budget(),
            "search_workers": thorough_workers(),
        },
        "counts": dict(counts),
        "requests": requests,
        "ready": False,
        "issues": [],
        "analysis": None,
    }
    if not policy:
        out["issues"] = [
            {"code": "POLICY_MISSING", "message": "Creare una policy di pianificazione"}
        ]
        return Response(out)
    with transaction.atomic():
        out["revision"] = lock_revision().revision
        try:
            dto, specs = compile_source(policy, week, mode)
        except DataNotReady as error:
            out["issues"] = [
                {
                    "code": error.code,
                    "message": error.message,
                    **({"request_id": error.ref} if error.ref else {}),
                }
            ]
            return Response(out)
    out["ready"] = True
    try:
        compiled, ledger = compile_candidates(dto)
    except InputError as error:
        out["issues"] = [{"code": error.code, "message": error.message}]
        return Response(out)
    per_request = {}
    tutor_options = defaultdict(int)
    for key, options in compiled.items():
        req_id = key.split("/")[0].removeprefix("req:")
        row = per_request.setdefault(
            req_id,
            {
                "units": 0,
                "placeable_units": 0,
                "min_options": None,
                "slots": 0,
                "tutors": defaultdict(int),
                "reasons": set(),
            },
        )
        row["units"] += 1
        if options:
            row["placeable_units"] += 1
        row["min_options"] = (
            len(options)
            if row["min_options"] is None
            else min(row["min_options"], len(options))
        )
        row["slots"] = max(row["slots"], len({o["start"] for o in options}))
        for o in options:
            row["tutors"][o["tutor_id"]] += 1
            tutor_options[o["tutor_id"]] += 1
        row["reasons"].update(ledger.get(key, []) if not options else [])
    units = {u["demand_key"]: u for u in dto["units"]}
    demand_by_student = defaultdict(int)
    demand_by_tutor = defaultdict(int)
    for u in units.values():
        for p in u["participants"]:
            demand_by_student[p] += u["duration_minutes"]
        for t in u["allowed_tutors"]:
            demand_by_tutor[t] += u["duration_minutes"]
    student_names = {
        str(s.id): s.display_name
        for s in Student.objects.filter(id__in=[s["id"] for s in dto["students"]])
    }
    out["analysis"] = {
        "units": len(units),
        "candidates": sum(len(v) for v in compiled.values()),
        "demand_minutes": sum(
            u["duration_minutes"] * len(u["participants"]) for u in units.values()
        ),
        "service_minutes": union_minutes(dto["service_windows"]),
        "schema_version": dto["schema_version"],
        "objective_order": dto["objective_order"],
        "requests": {
            req_id: {
                **{k: v for k, v in row.items() if k not in ("tutors", "reasons")},
                "tutors": [
                    {"id": t, "display_name": tutor_names.get(t, t), "options": n}
                    for t, n in sorted(row["tutors"].items(), key=lambda i: -i[1])
                ],
                "reasons": sorted(row["reasons"]),
            }
            for req_id, row in per_request.items()
        },
        "tutors": sorted(
            [
                {
                    "id": t["id"],
                    "display_name": tutor_names.get(t["id"], t["id"]),
                    "available_minutes": union_minutes(t["availability"]),
                    "eligible_demand_minutes": demand_by_tutor[t["id"]],
                    "weekly_limit_minutes": t.get("weekly_limit_minutes"),
                    "options": tutor_options[t["id"]],
                }
                for t in dto["tutors"]
            ],
            key=lambda r: r["display_name"],
        ),
        "students": sorted(
            [
                {
                    "id": s["id"],
                    "display_name": student_names.get(s["id"], s["id"]),
                    "available_minutes": union_minutes(s["availability"]),
                    "demand_minutes": demand_by_student[s["id"]],
                }
                for s in dto["students"]
            ],
            key=lambda r: r["display_name"],
        ),
    }
    return Response(out)
