"""Riconciliazione tra calendario pubblicato e DTO di pianificazione di una settimana.

Semantica (s2-calendario):
- una lezione occupa la settimana *fisica* in cui cade (``start_at``); la sua unità
  canonica resta quella della settimana nominale (DemandUnit), anche dopo uno
  spostamento tra settimane;
- nella settimana nominale l'unità di una lezione spostata altrove è soddisfatta e
  viene rimossa dal DTO (nessuna doppia espansione); nella settimana fisica la
  lezione compare come unità sintetica bloccata con la stessa chiave canonica;
- un'unità coperta da un RecoveryObligation non rinunciato è rimossa: il recupero
  (lezione con ``recovery``) compare come unità sintetica ``recovery:<id>``;
- le serie attive (LessonSeries) proiettano blocchi sulle unità libere della
  richiesta solo se compatibili con il calendario già fisso (mai forzati).
"""

import contextvars
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from apps.scheduling.contracts import utc_epoch
from apps.scheduling.validator import validate_assignments
from apps.scheduling.source import DataNotReady
from domain.intervals import local_to_utc
from .models import LessonOccurrence

OCCUPYING = ("PUBLISHED", "COMPLETED")
ZONE = "Europe/Rome"
_series_projection = contextvars.ContextVar("calendar_series_projection", default=True)


@contextmanager
def operations_compile():
    """Compilazione per comandi sul calendario: nessuna proiezione delle serie.

    Le date di serie non ancora pubblicate non sono appuntamenti e non devono
    bloccare spostamenti o pratiche di conflitto."""
    token = _series_projection.set(False)
    try:
        yield
    finally:
        _series_projection.reset(token)


def week_of(moment):
    local = moment.astimezone(ZoneInfo(ZONE)).date()
    return local - timedelta(days=local.weekday())


def week_window(week):
    return (
        local_to_utc(datetime.combine(week, time.min)),
        local_to_utc(datetime.combine(week + timedelta(days=7), time.min)),
    )


def unit_key(lesson):
    if lesson.recovery_id:
        return f"recovery:{lesson.recovery_id}"
    return lesson.demand.demand_key


def request_id_of(demand_key):
    if not demand_key.startswith("req:"):
        return None
    return demand_key[4:].split("/", 1)[0]


def assignment(lesson, epoch):
    def minute(dt):
        seconds = (dt - epoch).total_seconds()
        if seconds % 60:
            raise DataNotReady(
                "CALENDAR_PRECISION", "Calendario non allineato al minuto"
            )
        return int(seconds / 60)

    return {
        "demand_key": unit_key(lesson),
        "tutor_id": str(lesson.tutor_id),
        "mode": lesson.mode,
        "location": lesson.location,
        "space_id": str(lesson.space_id) if lesson.space_id else None,
        "video_id": str(lesson.video_id) if lesson.video_id else None,
        "start": minute(lesson.start_at),
        "end": minute(lesson.end_at),
    }


def _lessons():
    return LessonOccurrence.objects.select_related(
        "demand__request", "publication__plan__run__snapshot", "recovery"
    ).prefetch_related("participants")


def active_week(week):
    """Lezioni che occupano fisicamente la settimana locale (PUBLISHED/COMPLETED)."""
    start, end = week_window(week)
    return _lessons().filter(state__in=OCCUPYING, start_at__gte=start, start_at__lt=end)


def canonical_week(week):
    """Lezioni ordinarie (non di recupero) la cui unità canonica è della settimana."""
    return _lessons().filter(
        state__in=OCCUPYING, demand__week_start=week, recovery__isnull=True
    )


def original_unit(lesson):
    snapshot = lesson.publication.plan.run.snapshot
    for unit in snapshot.data["units"]:
        if unit["demand_key"] == lesson.demand.demand_key:
            return unit
    raise DataNotReady(
        "PUBLISHED_DEMAND_CHANGED", "Unità canonica assente dallo snapshot d'origine"
    )


def synthetic_unit(lesson, data):
    """Unità per una lezione fuori dalla propria settimana nominale o di recupero."""
    unit = deepcopy(original_unit(lesson))
    unit["demand_key"] = unit_key(lesson)
    unit["locked_assignment"] = None
    if lesson.recovery_id:
        unit["participants"] = sorted(lesson.recovery.participants)
        unit["duration_minutes"] = lesson.recovery.minutes_remaining
        unit["mandatory"] = True
    request = lesson.demand.request
    epoch = utc_epoch(data)

    def minute(day):
        moment = local_to_utc(datetime.combine(day, time.min))
        return int((moment - epoch).total_seconds() / 60)

    unit["earliest_start"] = max(0, minute(request.period_start))
    unit["latest_end"] = min(
        data["horizon_minutes"], minute(request.period_end + timedelta(days=1))
    )
    students = {s["id"] for s in data["students"]}
    tutors = {t["id"] for t in data["tutors"]}
    if not set(unit["participants"]) <= students or str(lesson.tutor_id) not in tutors:
        raise DataNotReady(
            "CROSS_WEEK_CONTEXT_MISSING",
            "Partecipanti o tutor della lezione assenti dai dati della settimana di destinazione",
        )
    # Contratto del DTO (contracts.parse_input): tutor ammessi presenti nel DTO,
    # tipo coerente con il numero di partecipanti, periodo non vuoto.
    unit["allowed_tutors"] = sorted(set(unit["allowed_tutors"]) & tutors)
    unit["type"] = "GROUP" if len(unit["participants"]) > 1 else "INDIVIDUAL"
    if unit["latest_end"] <= unit["earliest_start"]:
        raise DataNotReady(
            "OUTSIDE_REQUEST_PERIOD",
            "La settimana di destinazione è fuori dal periodo della richiesta",
        )
    return unit


def check_published(lesson, unit, data, policy):
    tutors = {t["id"]: t for t in data["tutors"]}
    resources = {v["id"]: v for v in data["resources"]}
    if set(unit["participants"]) != {
        str(p.student_id) for p in lesson.participants.all()
    }:
        raise DataNotReady(
            "PUBLISHED_PARTICIPANTS_CHANGED",
            "Partecipanti pubblicati diversi dalla domanda corrente",
        )
    original = lesson.publication.plan.run.snapshot
    if original.policy_id != policy.id or original.policy_version != policy.version:
        raise DataNotReady(
            "PUBLISHED_POLICY_CHANGED",
            "La policy delle lezioni pubblicate richiede riconciliazione esplicita",
        )
    profile = tutors.get(str(lesson.tutor_id))
    if not profile:
        raise DataNotReady(
            "PUBLISHED_TUTOR_CHANGED",
            "Tutor pubblicato non più eleggibile nei dati correnti",
        )
    if lesson.tutor_occupied_until != lesson.end_at + timedelta(
        minutes=profile["pause_minutes"]
    ):
        raise DataNotReady(
            "PUBLISHED_BUFFER_CHANGED",
            "Politica di occupazione pubblicata cambiata",
        )
    for resource_id, occupied_until in [
        (lesson.space_id, lesson.space_occupied_until),
        (lesson.video_id, lesson.video_occupied_until),
    ]:
        if resource_id:
            resource = resources.get(str(resource_id))
            if not resource or occupied_until != lesson.end_at + timedelta(
                minutes=resource["buffer_minutes"]
            ):
                raise DataNotReady(
                    "PUBLISHED_BUFFER_CHANGED",
                    "Risorsa o buffer pubblicati cambiati",
                )


def recovered_demand_keys(week):
    from .models import RecoveryObligation

    return set(
        RecoveryObligation.objects.filter(demand__week_start=week)
        .exclude(state="WAIVED")
        .values_list("demand__demand_key", flat=True)
    )


def attach_calendar(data, week, policy, unlocked_ids=()):
    unlocked = {str(v) for v in unlocked_ids}
    units = {u["demand_key"]: u for u in data["units"]}
    epoch = utc_epoch(data)
    start, end = week_window(week)
    recovered = recovered_demand_keys(week)
    removed = set()
    occupied = set()
    for lesson in canonical_week(week):
        key = lesson.demand.demand_key
        unit = units.get(key)
        if not unit:
            raise DataNotReady(
                "PUBLISHED_DEMAND_CHANGED",
                "Domanda pubblicata non riconciliabile: nessuna cancellazione implicita",
            )
        here = start <= lesson.start_at < end
        if not here:
            # Soddisfatta in un'altra settimana fisica; resta libera solo se il
            # comando corrente sta spostando proprio questa lezione.
            if str(lesson.id) not in unlocked:
                removed.add(key)
            continue
        check_published(lesson, unit, data, policy)
        occupied.add(key)
        if str(lesson.id) not in unlocked:
            unit["locked_assignment"] = assignment(lesson, epoch)
    # Un obbligo di recupero soddisfa l'unità solo se nessuna lezione la occupa già
    # (es. lezione conclusa con un assente): niente doppio monte settimanale.
    removed |= recovered - occupied
    data["units"] = [u for u in data["units"] if u["demand_key"] not in removed]
    for lesson in active_week(week):
        if lesson.recovery_id is None and lesson.demand.week_start == week:
            continue
        unit = synthetic_unit(lesson, data)
        check_published(lesson, unit, data, policy)
        if str(lesson.id) not in unlocked:
            unit["locked_assignment"] = assignment(lesson, epoch)
        data["units"].append(unit)
    fixed = [u["locked_assignment"] for u in data["units"] if u["locked_assignment"]]
    if validate_assignments(data, fixed, require_coverage=False)["status"] != "PASSED":
        raise DataNotReady(
            "PUBLISHED_CONFLICT",
            "Lezioni pubblicate incompatibili: risolvere senza riscritture automatiche",
        )
    if _series_projection.get():
        project_series(data, week, fixed)
    return data


def series_candidates(data, week):
    """Occorrenze di serie attive nella settimana, non ancora materializzate."""
    from .models import LessonSeries
    from .recurrence import expand, RecurrenceError

    requests = {request_id_of(u["demand_key"]) for u in data["units"]} - {None}
    if not requests:
        return []
    used = set(
        LessonOccurrence.objects.filter(recurrence_key__isnull=False).values_list(
            "recurrence_key", flat=True
        )
    )
    out = []
    rows = LessonSeries.objects.filter(
        state="ACTIVE",
        request_id__in=requests,
        start_date__lt=week + timedelta(days=7),
        until_date__gte=week,
    ).order_by("start_date", "id")
    for series in rows:
        try:
            occurrences = expand(series, week, week + timedelta(days=7))
        except RecurrenceError:
            continue
        for occ in occurrences:
            if occ["key"] not in used and occ["nominal_date"] not in (
                series.carried or {}
            ):
                out.append((series, occ))
    return sorted(out, key=lambda item: (item[1]["start_at"], item[1]["key"]))


def project_series(data, week, fixed):
    """Blocca su unità libere le occorrenze di serie compatibili; mai forzare."""
    epoch = utc_epoch(data)
    free = {}
    for unit in sorted(data["units"], key=lambda u: u["demand_key"]):
        request = request_id_of(unit["demand_key"])
        if request and not unit["locked_assignment"]:
            free.setdefault(request, []).append(unit)
    projected = []
    for series, occ in series_candidates(data, week):
        queue = free.get(str(series.request_id))
        if not queue:
            continue
        minutes = (occ["start_at"] - epoch).total_seconds() / 60
        if not minutes.is_integer():
            continue
        candidate = {
            "demand_key": queue[0]["demand_key"],
            "tutor_id": str(series.tutor_id),
            "mode": series.mode,
            "location": series.location,
            "space_id": str(series.space_id) if series.space_id else None,
            "video_id": str(series.video_id) if series.video_id else None,
            "start": int(minutes),
            "end": int(minutes) + series.duration_minutes,
        }
        if (
            0 <= candidate["start"]
            and candidate["end"] <= data["horizon_minutes"]
            and validate_assignments(data, [*fixed, candidate], require_coverage=False)[
                "status"
            ]
            == "PASSED"
        ):
            queue.pop(0)["locked_assignment"] = candidate
            fixed.append(candidate)
            projected.append((series, occ, candidate))
    return projected
