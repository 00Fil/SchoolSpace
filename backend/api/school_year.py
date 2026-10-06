"""API P2 (guida v3.1): anno scolastico, periodi di studio, approvazione in blocco,
orari del centro dalla griglia."""

from datetime import time as dtime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.availability.models import AvailabilityRule
from apps.scheduling import school_year as service
from apps.scheduling.models import PlanningAudit, SchoolYear, ServiceWindow, StudyPeriod
from apps.scheduling.revision import lock_revision

from ._privacy_common import (
    BadPayload,
    boolean,
    center_only,
    handle_errors,
    integer,
    iso_date,
    payload,
    text,
)


def period_json(p):
    return {
        "id": str(p.pk),
        "school_year": str(p.school_year_id),
        "kind": p.kind,
        "kind_label": StudyPeriod.Kind(p.kind).label,
        "label": p.label,
        "start_date": p.start_date.isoformat(),
        "end_date": p.end_date.isoformat(),
        "closes_center": bool(p.closure_id),
        "version": p.version,
    }


def year_json(y):
    return {
        "id": str(y.pk),
        "name": y.name,
        "start_date": y.start_date.isoformat(),
        "end_date": y.end_date.isoformat(),
        "active": y.active,
        "version": y.version,
        "periods": [period_json(p) for p in y.periods.all()],
    }


@api_view(["GET", "POST"])
@handle_errors
def years(request):
    if request.method == "GET":
        # Lettura per tutti gli autenticati: serve ai portali per i periodi di default.
        if not request.user.is_authenticated:
            return Response(status=401)
        rows = SchoolYear.objects.prefetch_related("periods")
        return Response({"count": rows.count(), "page": 1, "results": [year_json(y) for y in rows]})
    center_only(request)
    data = payload(request, required=("name", "start_date", "end_date", "reason"))
    year = service.create_year(
        request.user,
        name=text(data, "name", 40),
        start_date=iso_date(data, "start_date"),
        end_date=iso_date(data, "end_date"),
        reason=data["reason"],
    )
    return Response(year_json(year), status=201)


@api_view(["GET"])
@handle_errors
def current_year(request):
    if not request.user.is_authenticated:
        return Response(status=401)
    try:
        day = iso_date(dict(request.query_params.items()), "date") or timezone.localdate()
    except BadPayload:
        return Response({"code": "INVALID_PAYLOAD"}, status=400)
    year = service.year_for(day)
    return Response(year_json(year) if year else None)


@api_view(["PATCH"])
@handle_errors
def year_detail(request, pk):
    center_only(request)
    year = get_object_or_404(SchoolYear, pk=pk)
    data = payload(request, required=("expected_version", "reason"), optional=("name", "start_date", "end_date", "active"))
    year = service.update_year(
        request.user,
        year,
        expected_version=integer(data, "expected_version"),
        reason=data["reason"],
        name=text(data, "name", 40, required=False),
        start_date=iso_date(data, "start_date"),
        end_date=iso_date(data, "end_date"),
        active=boolean(data, "active") if "active" in data else None,
    )
    return Response(year_json(year))


@api_view(["POST"])
@handle_errors
def year_periods(request, pk):
    center_only(request)
    year = get_object_or_404(SchoolYear, pk=pk)
    data = payload(request, required=("kind", "start_date", "end_date", "reason"), optional=("label",))
    period = service.create_period(
        request.user,
        year,
        kind=text(data, "kind", 10),
        label=text(data, "label", 80, required=False) or "",
        start_date=iso_date(data, "start_date"),
        end_date=iso_date(data, "end_date"),
        reason=data["reason"],
    )
    return Response(period_json(period), status=201)


@api_view(["PATCH"])
@handle_errors
def period_detail(request, pk):
    center_only(request)
    period = get_object_or_404(StudyPeriod, pk=pk)
    data = payload(request, required=("expected_version", "reason"), optional=("kind", "label", "start_date", "end_date"))
    period = service.update_period(
        request.user,
        period,
        expected_version=integer(data, "expected_version"),
        reason=data["reason"],
        kind=text(data, "kind", 10, required=False) or None,
        label=data.get("label"),
        start_date=iso_date(data, "start_date"),
        end_date=iso_date(data, "end_date"),
    )
    return Response(period_json(period))


@api_view(["POST"])
@handle_errors
def period_delete(request, pk):
    center_only(request)
    period = get_object_or_404(StudyPeriod, pk=pk)
    data = payload(request, required=("expected_version", "reason"))
    service.delete_period(request.user, period, expected_version=integer(data, "expected_version"), reason=data["reason"])
    return Response(status=204)


# --- Disponibilità: approvazione in blocco (DC-APPROVAZIONI: approva solo il centro) ---


@api_view(["POST"])
@handle_errors
def availability_bulk_review(request):
    center_only(request)
    data = payload(request, required=("ids", "status", "reason"))
    ids, status = data["ids"], data["status"]
    if not isinstance(ids, list) or not ids or len(ids) > 500 or not all(isinstance(i, str) for i in ids):
        raise BadPayload("ids: elenco di identificativi (max 500)")
    if status not in ("APPROVED", "REVOKED"):
        raise BadPayload("status: APPROVED o REVOKED")
    reason = text(data, "reason", 200)
    allowed_from = ("DRAFT",) if status == "APPROVED" else ("DRAFT", "APPROVED")
    with transaction.atomic():
        lock_revision()
        rows = list(AvailabilityRule.objects.select_for_update().filter(pk__in=ids))
        changed, skipped = [], []
        for rule in rows:
            if rule.status not in allowed_from:
                skipped.append(str(rule.pk))
                continue
            rule.status = status
            rule.approved_by = request.user
            rule.save()
            PlanningAudit.objects.create(actor=request.user, operation="availability:" + status, object_id=rule.pk, reason=reason)
            changed.append(str(rule.pk))
    found = {str(r.pk) for r in rows}
    return Response({"changed": changed, "skipped": skipped, "not_found": [i for i in ids if i not in found]})


# --- Orari del centro dalla griglia: sostituzione atomica per modalità e periodo ---


@api_view(["POST"])
@handle_errors
def service_windows_replace(request):
    center_only(request)
    data = payload(request, required=("mode", "period_start", "period_end", "slots", "reason"))
    mode = data["mode"]
    if mode not in ("IN_PERSON", "ONLINE"):
        raise BadPayload("mode: IN_PERSON o ONLINE")
    start, end = iso_date(data, "period_start"), iso_date(data, "period_end")
    if not start or not end or end < start:
        raise BadPayload("Periodo non valido")
    slots = data["slots"]
    if not isinstance(slots, list) or len(slots) > 200:
        raise BadPayload("slots: elenco (max 200)")
    parsed = []
    for s in slots:
        if not isinstance(s, dict) or set(s) != {"weekday", "start", "end"}:
            raise BadPayload("slot: weekday, start, end (minuti)")
        wd, a, b = s["weekday"], s["start"], s["end"]
        if not all(type(x) is int for x in (wd, a, b)) or not (0 <= wd <= 6 and 0 <= a < b <= 1440) or a % 15 or b % 15:
            raise BadPayload("slot non valido")
        parsed.append((wd, dtime(a // 60, a % 60), dtime(23, 59) if b == 1440 else dtime(b // 60, b % 60)))
    reason = text(data, "reason", 200)
    location = "ON_SITE" if mode == "IN_PERSON" else "REMOTE"
    with transaction.atomic():
        lock_revision()
        old = ServiceWindow.objects.filter(mode=mode, location=location, resource__isnull=True, period_start=start, period_end=end)
        removed = old.count()
        old.delete()
        created = [
            ServiceWindow.objects.create(mode=mode, location=location, weekday=wd, start_time=a, end_time=b, period_start=start, period_end=end, resource=None)
            for wd, a, b in parsed
        ]
        for w in created:
            PlanningAudit.objects.create(actor=request.user, operation="service_window:replace", object_id=w.pk, reason=reason)
    return Response({"created": len(created), "removed": removed})
