"""Derive recurring slots (LessonSeries) from a previous validated plan (GAP-D03).

The centre explicitly asks to confirm the slots of a plan; the result is a
PREFERRED stability by default.  REQUIRED must be declared by the centre on the
LessonSeries itself (a family's binding request), never inferred.
"""

from datetime import timedelta
from django.db import transaction
from apps.education.path_services import DomainError
from .contracts import utc_epoch
from .models import DemandUnit, LessonSeries, PlanningAudit, PlanningRevision
from .revision import lock_revision


@transaction.atomic
def derive_series_from_plan(plan, actor, stability="PREFERRED"):
    if stability not in ("PREFERRED", "REQUIRED"):
        raise DomainError("SERIES_STABILITY", "Stabilità PREFERRED o REQUIRED")
    revision = lock_revision()
    if plan.state != "VALIDATED" or plan.run.snapshot.revision != revision.revision:
        raise DomainError(
            "PLAN_NOT_CURRENT", "Solo una proposta validata e non obsoleta"
        )
    data = plan.run.snapshot.data
    epoch = utc_epoch(data)
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(data["timezone"])
    units = {
        u.demand_key: u
        for u in DemandUnit.objects.filter(
            demand_key__in=[a["demand_key"] for a in plan.assignments]
        )
    }
    first = {}
    for a in sorted(plan.assignments, key=lambda a: a["start"]):
        unit = units.get(a["demand_key"])
        if unit and (unit.request_id, unit.serial) not in first:
            first[(unit.request_id, unit.serial)] = (
                epoch + timedelta(minutes=a["start"])
            ).astimezone(zone)
    changed = []
    for (request_id, serial), moment in sorted(first.items(), key=lambda i: str(i[0])):
        row = LessonSeries.objects.filter(request_id=request_id, serial=serial).first()
        values = {
            "weekday": moment.weekday(),
            "local_start_time": moment.time().replace(tzinfo=None),
            "stability": stability,
            "source": "PREVIOUS_PLAN",
            "source_plan": plan,
            "active": True,
        }
        if row is None:
            row = LessonSeries(request_id=request_id, serial=serial, **values)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        row.save()
        changed.append(row)
    PlanningAudit.objects.create(
        actor=actor, operation="derive_series", object_id=plan.id
    )
    return changed, PlanningRevision.objects.get(pk=1).revision
