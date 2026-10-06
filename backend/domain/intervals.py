"""Experimental pure functions. Half-open intervals; no database writes."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True, order=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Offset esplicito obbligatorio")
        object.__setattr__(self, "start", self.start.astimezone(timezone.utc))
        object.__setattr__(self, "end", self.end.astimezone(timezone.utc))
        if self.end <= self.start:
            raise ValueError("Intervallo non positivo")


def normalize(intervals):
    result = []
    for item in sorted(intervals):
        if result and item.start <= result[-1].end:
            result[-1] = Interval(result[-1].start, max(item.end, result[-1].end))
        else:
            result.append(item)
    return result


def subtract(available, removed):
    result = normalize(available)
    for exclusion in normalize(removed):
        updated = []
        for item in result:
            if exclusion.end <= item.start or exclusion.start >= item.end:
                updated.append(item)
                continue
            if item.start < exclusion.start:
                updated.append(Interval(item.start, exclusion.start))
            if exclusion.end < item.end:
                updated.append(Interval(exclusion.end, item.end))
        result = updated
    return result


def intersect(*collections):
    if not collections:
        return []
    result = normalize(collections[0])
    for collection in collections[1:]:
        other = normalize(collection)
        result = normalize(
            [
                Interval(max(a.start, b.start), min(a.end, b.end))
                for a in result
                for b in other
                if max(a.start, b.start) < min(a.end, b.end)
            ]
        )
    return result


def compile_effective(recurring, added, removed, state):
    if state == "UNKNOWN":
        raise ValueError("Disponibilità mancante: pianificazione bloccata")
    if state == "DECLARED_NONE":
        return []
    if state not in {"APPROVED", "APPROVED_UNRESTRICTED"}:
        raise ValueError("Stato non supportato")
    # Unrestricted still requires explicit bounded service windows as recurring input.
    return subtract([*recurring, *added], removed)


def local_to_utc(naive, zone="Europe/Rome"):
    if naive.tzinfo is not None:
        raise ValueError("Richiesta un'ora locale senza offset")
    tz = ZoneInfo(zone)
    candidates = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
        if candidate.astimezone(tz).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if len(candidates) != 1:
        raise ValueError(
            "Ora locale inesistente o ambigua: approvazione esplicita richiesta"
        )
    return candidates.pop()


def expand_weekly(
    weekday,
    start_time,
    end_time,
    period_start,
    period_end,
    horizon_start,
    horizon_end,
    zone="Europe/Rome",
):
    if not 0 <= weekday <= 6 or end_time <= start_time:
        raise ValueError("Regola settimanale non valida")
    # Period end inclusive; planning horizon end exclusive.
    day = max(period_start, horizon_start)
    result = []
    while day <= period_end and day < horizon_end:
        if day.weekday() == weekday:
            result.append(
                Interval(
                    local_to_utc(datetime.combine(day, start_time), zone),
                    local_to_utc(datetime.combine(day, end_time), zone),
                )
            )
        day += timedelta(days=1)
    return result
