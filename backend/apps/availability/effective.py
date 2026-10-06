"""Disponibilità effettiva con diagnostica completa (GAP-C07).

Stessa semantica del compilatore di pianificazione (apps.scheduling.source):
regole APPROVED ricorrenti in ora locale, eccezioni ADD/REMOVE, intervalli
semiaperti, stato della dichiarazione. A differenza del compilatore non si ferma
al primo problema: restituisce tutte le diagnostiche e ``ready``.
Sola lettura: nessuna scrittura, nessuna revisione incrementata.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from domain.intervals import Interval, compile_effective, local_to_utc, intersect
from .models import (
    AvailabilityRule,
    AvailabilityDeclaration,
    AvailabilityException,
    AvailabilityConflict,
)

ZONE = ZoneInfo("Europe/Rome")
COMBINATIONS = [("IN_PERSON", "ON_SITE"), ("ONLINE", "ON_SITE"), ("ONLINE", "REMOTE")]


def diag(code, severity, message, **extra):
    return {"code": code, "severity": severity, "message": message, **extra}


def expand_rule(rule, first, last, problems):
    """Intervalli UTC di una regola in [first, last); date con ora locale invalida segnalate."""
    out = []
    day = max(rule.period_start, first)
    while day <= rule.period_end and day < last:
        if day.weekday() == rule.weekday:
            try:
                out.append(
                    Interval(
                        local_to_utc(
                            datetime.combine(day, rule.start_time), rule.timezone
                        ),
                        local_to_utc(
                            datetime.combine(day, rule.end_time), rule.timezone
                        ),
                    )
                )
            except ValueError:
                problems.append(
                    diag(
                        "INVALID_LOCAL_TIME",
                        "BLOCKING",
                        "Ora locale inesistente o ambigua (cambio d'ora): regola da correggere",
                        rule_id=str(rule.id),
                        date=day.isoformat(),
                    )
                )
        day += timedelta(days=1)
    return out


def service_intervals(first, last, mode, location):
    from apps.scheduling.models import ServiceWindow

    rows = ServiceWindow.objects.filter(
        resource__isnull=True,
        mode=mode,
        location=location,
        period_start__lt=last,
        period_end__gte=first,
    )
    out = []
    for row in rows:
        day = max(row.period_start, first)
        while day <= row.period_end and day < last:
            if day.weekday() == row.weekday:
                try:
                    out.append(
                        Interval(
                            local_to_utc(datetime.combine(day, row.start_time)),
                            local_to_utc(datetime.combine(day, row.end_time)),
                        )
                    )
                except ValueError:
                    pass
            day += timedelta(days=1)
    return out


def iso(moment):
    return moment.isoformat()


def effective_availability(kind, subject, first, last):
    """kind: 'tutor' | 'student'; first inclusa, last esclusa (date locali)."""
    lookup = {kind: subject}
    start = local_to_utc(datetime.combine(first, time.min))
    end = local_to_utc(datetime.combine(last, time.min))
    problems = []
    declaration = AvailabilityDeclaration.objects.filter(**lookup).first()
    state = declaration.state if declaration else "MISSING"
    if not declaration:
        problems.append(
            diag("MISSING_DECLARATION", "BLOCKING", "Dichiarazione esplicita assente")
        )
    elif state == "UNKNOWN":
        problems.append(
            diag(
                "DECLARATION_UNKNOWN", "BLOCKING", "Disponibilità dichiarata incompleta"
            )
        )
    for conflict in AvailabilityConflict.objects.filter(**lookup, open=True):
        problems.append(
            diag(
                "AVAILABILITY_CONFLICT",
                "BLOCKING",
                "Conflitto tra dichiarazioni da risolvere",
                conflict_id=str(conflict.id),
                reason=conflict.reason,
            )
        )
    rules = list(
        AvailabilityRule.objects.filter(
            **lookup, period_start__lt=last, period_end__gte=first
        ).order_by("weekday", "start_time", "id")
    )
    drafts = [r for r in rules if r.status == "DRAFT"]
    revoked = [r for r in rules if r.status == "REVOKED"]
    approved = [r for r in rules if r.status == "APPROVED"]
    if drafts:
        problems.append(
            diag(
                "AVAILABILITY_PENDING",
                "BLOCKING",
                "Regole nel periodo ancora da approvare o revocare",
                rule_ids=[str(r.id) for r in drafts],
            )
        )
    exceptions = list(
        AvailabilityException.objects.filter(
            **lookup, start_at__lt=end, end_at__gt=start
        ).order_by("start_at", "id")
    )
    if state == "DECLARED_NONE" and (
        approved or any(e.kind == "ADD_AVAILABLE" for e in exceptions)
    ):
        problems.append(
            diag(
                "CONTRADICTORY_AVAILABILITY",
                "BLOCKING",
                "Nessuna disponibilità dichiarata ma finestre attive presenti",
            )
        )
    if kind == "student" and any(
        r.mode == "ONLINE" and r.location == "ON_SITE" for r in [*approved, *exceptions]
    ):
        problems.append(
            diag(
                "STUDENT_ONLINE_ONSITE_UNSUPPORTED",
                "BLOCKING",
                "Studenti online in sede non ancora supportati dalla pianificazione",
            )
        )
    windows = []
    unusable = 0
    for mode, location in COMBINATIONS:
        recurring = [
            i
            for r in approved
            if r.mode == mode and r.location == location
            for i in expand_rule(r, first, last, problems)
        ]
        added, removed = [], []
        for e in exceptions:
            if e.mode == mode and e.location == location:
                clipped = (max(e.start_at, start), min(e.end_at, end))
                if clipped[0] < clipped[1]:
                    (added if e.kind == "ADD_AVAILABLE" else removed).append(
                        Interval(*clipped)
                    )
        if state in ("MISSING", "UNKNOWN"):
            effective = []
        else:
            effective = compile_effective(
                recurring,
                added,
                removed,
                "APPROVED" if state != "DECLARED_NONE" else state,
            )
        effective = [
            Interval(max(i.start, start), min(i.end, end))
            for i in effective
            if max(i.start, start) < min(i.end, end)
        ]
        service = service_intervals(first, last, mode, location)
        usable = intersect(effective, service) if service else []
        for interval in effective:
            minutes = int((interval.end - interval.start).total_seconds() // 60)
            inside = sum(
                int((u.end - u.start).total_seconds() // 60)
                for u in usable
                if u.start >= interval.start and u.end <= interval.end
            )
            unusable += minutes - inside
            windows.append(
                {
                    "mode": mode,
                    "location": location,
                    "start_at": iso(interval.start),
                    "end_at": iso(interval.end),
                    "local_start": iso(interval.start.astimezone(ZONE)),
                    "local_end": iso(interval.end.astimezone(ZONE)),
                    "minutes": minutes,
                    "within_service_minutes": inside,
                }
            )
    if state == "APPROVED" and not windows:
        problems.append(
            diag(
                "NO_EFFECTIVE_WINDOWS",
                "WARNING",
                "Nessuna finestra effettiva nel periodo",
            )
        )
    if unusable:
        problems.append(
            diag(
                "OUTSIDE_SERVICE_WINDOWS",
                "WARNING",
                "Parte delle finestre cade fuori dalle aperture del centro",
                minutes=unusable,
            )
        )
    if revoked:
        problems.append(
            diag(
                "REVOKED_RULES_IGNORED",
                "INFO",
                "Regole revocate ignorate",
                rule_ids=[str(r.id) for r in revoked],
            )
        )
    if kind == "tutor":
        from apps.scheduling.models import TutorOperatingPolicy, TutorSkill

        if not TutorOperatingPolicy.objects.filter(tutor=subject).exists():
            problems.append(
                diag(
                    "TUTOR_LIMITS_MISSING",
                    "BLOCKING",
                    "Limiti, pause e transizioni mancanti",
                )
            )
        if not TutorSkill.objects.filter(
            tutor=subject, approved=True, valid_from__lt=last, valid_until__gte=first
        ).exists():
            problems.append(
                diag(
                    "TUTOR_SKILLS_MISSING",
                    "WARNING",
                    "Nessuna competenza approvata nel periodo",
                )
            )
    windows.sort(key=lambda w: (w["start_at"], w["mode"], w["location"]))
    return {
        "subject": {"kind": kind.upper(), "id": str(subject.id)},
        "from": first.isoformat(),
        "until": last.isoformat(),
        "timezone": "Europe/Rome",
        "declaration_state": state,
        "ready": not any(p["severity"] == "BLOCKING" for p in problems),
        "windows": windows,
        "exceptions": [
            {
                "id": str(e.id),
                "kind": e.kind,
                "mode": e.mode,
                "location": e.location,
                "start_at": iso(e.start_at),
                "end_at": iso(e.end_at),
            }
            for e in exceptions
        ],
        "rules": {
            "approved": len(approved),
            "draft": len(drafts),
            "revoked": len(revoked),
        },
        "diagnostics": problems,
    }
