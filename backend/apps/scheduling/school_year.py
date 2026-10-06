"""Anno scolastico e periodi di studio (guida v3.1, P2; decisione DC-ANNO).

* scrive solo il centro, con motivo e versione attesa; ogni scrittura è in PlanningAudit
  e incrementa la revisione di pianificazione (cambia i dati del motore);
* le pause (natale, pasqua, estate, altre) creano/aggiornano una chiusura «tutte le
  modalità» dal primo all'ultimo giorno inclusi, ora di Roma;
* inizi e periodi per i recuperi non chiudono il centro;
* i periodi stanno dentro l'anno e le pause non si sovrappongono tra loro né ai recuperi.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.education.tutors import check_version, require_center, require_reason
from apps.privacy.errors import Conflict, PrivacyError

from .models import Closure, PlanningAudit, SchoolYear, StudyPeriod
from .revision import lock_revision

ROME = ZoneInfo("Europe/Rome")


def _audit(actor, operation, obj, reason):
    PlanningAudit.objects.create(actor=actor, operation=operation, object_id=obj.pk, reason=reason)


def _check_year(name, start, end, exclude=None):
    if not name or not start or not end:
        raise PrivacyError("INVALID", "Nome, inizio e fine obbligatori")
    if end <= start:
        raise PrivacyError("INVALID_RANGE", "La fine deve seguire l'inizio")
    if (end - start).days > 400:
        raise PrivacyError("INVALID_RANGE", "Un anno scolastico dura al massimo 400 giorni")
    clash = SchoolYear.objects.filter(start_date__lte=end, end_date__gte=start)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise Conflict("YEAR_OVERLAP", "Si sovrappone a un altro anno scolastico")


@transaction.atomic
def create_year(actor, *, name, start_date, end_date, reason):
    require_center(actor)
    reason = require_reason(reason)
    lock_revision()
    _check_year(name, start_date, end_date)
    year = SchoolYear.objects.create(name=name, start_date=start_date, end_date=end_date)
    _audit(actor, "school_year:create", year, reason)
    return year


@transaction.atomic
def update_year(actor, year, *, expected_version, reason, **fields):
    require_center(actor)
    reason = require_reason(reason)
    lock_revision()
    year = SchoolYear.objects.select_for_update().get(pk=year.pk)
    check_version(year, expected_version)
    for key in ("name", "start_date", "end_date", "active"):
        if fields.get(key) is not None:
            setattr(year, key, fields[key])
    _check_year(year.name, year.start_date, year.end_date, exclude=year)
    if (
        year.periods.filter(start_date__lt=year.start_date).exists()
        or year.periods.filter(end_date__gt=year.end_date).exists()
    ):
        raise Conflict("PERIOD_OUTSIDE_YEAR", "Alcuni periodi resterebbero fuori dall'anno")
    year.save()
    _audit(actor, "school_year:update", year, reason)
    return year


def _check_period(year, kind, start, end, exclude=None):
    if kind not in StudyPeriod.Kind.values:
        raise PrivacyError("INVALID", "Tipo di periodo non valido")
    if not start or not end or end < start:
        raise PrivacyError("INVALID_RANGE", "Date del periodo non valide")
    if start < year.start_date or end > year.end_date:
        raise Conflict("PERIOD_OUTSIDE_YEAR", "Il periodo deve stare dentro l'anno scolastico")
    if kind == "START":
        return
    others = year.periods.filter(start_date__lte=end, end_date__gte=start).exclude(kind="START")
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if kind == "RECOVERY":
        others = others.filter(kind__in=StudyPeriod.BREAKS)
    if others.exists():
        raise Conflict("PERIOD_OVERLAP", "Si sovrappone a una pausa o a un periodo per i recuperi")


def _sync_closure(period):
    if period.kind not in StudyPeriod.BREAKS:
        if period.closure_id:
            closure = period.closure
            period.closure = None
            period.save()
            closure.delete()
        return
    start = datetime.combine(period.start_date, time.min, tzinfo=ROME)
    end = datetime.combine(period.end_date + timedelta(days=1), time.min, tzinfo=ROME)
    reason = (StudyPeriod.Kind(period.kind).label + (": " + period.label if period.label else ""))[:160]
    if period.closure_id:
        closure = period.closure
        closure.start_at, closure.end_at, closure.reason = start, end, reason
        closure.mode, closure.resource = "ALL", None
        closure.save()
    else:
        period.closure = Closure.objects.create(start_at=start, end_at=end, mode="ALL", resource=None, reason=reason)
        period.save()


@transaction.atomic
def create_period(actor, year, *, kind, start_date, end_date, label="", reason):
    require_center(actor)
    reason = require_reason(reason)
    lock_revision()
    year = SchoolYear.objects.select_for_update().get(pk=year.pk)
    _check_period(year, kind, start_date, end_date)
    period = StudyPeriod.objects.create(school_year=year, kind=kind, label=label, start_date=start_date, end_date=end_date)
    _sync_closure(period)
    _audit(actor, "study_period:create", period, reason)
    return period


@transaction.atomic
def update_period(actor, period, *, expected_version, reason, **fields):
    require_center(actor)
    reason = require_reason(reason)
    lock_revision()
    period = StudyPeriod.objects.select_for_update().get(pk=period.pk)
    check_version(period, expected_version)
    for key in ("kind", "label", "start_date", "end_date"):
        if fields.get(key) is not None:
            setattr(period, key, fields[key])
    _check_period(period.school_year, period.kind, period.start_date, period.end_date, exclude=period)
    period.save()
    _sync_closure(period)
    _audit(actor, "study_period:update", period, reason)
    return period


@transaction.atomic
def delete_period(actor, period, *, expected_version, reason):
    require_center(actor)
    reason = require_reason(reason)
    lock_revision()
    period = StudyPeriod.objects.select_for_update().get(pk=period.pk)
    check_version(period, expected_version)
    _audit(actor, "study_period:delete", period, reason)
    closure = period.closure
    period.delete()
    if closure is not None:
        closure.delete()


def year_for(day):
    return SchoolYear.objects.filter(active=True, start_date__lte=day, end_date__gte=day).first()
