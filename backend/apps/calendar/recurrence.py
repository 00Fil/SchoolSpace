"""Sottoinsieme esplicito di RFC 5545 per LessonSeries (FR10, T12–T14).

Supportato: FREQ=WEEKLY (obbligatorio), INTERVAL=1..52, BYDAY=MO..SU (lista),
UNTIL=AAAAMMGG oppure AAAAMMGGTHHMMSSZ (obbligatorio: regola limitata). Qualsiasi
altra parte (COUNT, BYMONTH, BYSETPOS, WKST, …) è rifiutata, mai ignorata.
Le occorrenze mantengono l'ora locale Europe/Rome; ore locali inesistenti o ambigue
(cambio d'ora) sono rifiutate con spiegazione, senza conversioni implicite.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from domain.intervals import local_to_utc

DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
SUPPORTED_TIMEZONE = "Europe/Rome"


class RecurrenceError(ValueError):
    def __init__(self, code, message, **extra):
        self.code, self.message, self.extra = code, message, extra
        super().__init__(message)


@dataclass(frozen=True)
class Rule:
    interval: int
    byday: tuple
    until: date


def parse_rrule(text, zone=SUPPORTED_TIMEZONE):
    if zone != SUPPORTED_TIMEZONE:
        raise RecurrenceError("TIMEZONE_UNSUPPORTED", "Fuso supportato: Europe/Rome")
    if not isinstance(text, str) or not text.strip():
        raise RecurrenceError("RRULE_INVALID", "Regola di ricorrenza obbligatoria")
    body = text.strip()
    if body.upper().startswith("RRULE:"):
        body = body[6:]
    parts = {}
    for chunk in body.split(";"):
        if "=" not in chunk:
            raise RecurrenceError("RRULE_INVALID", f"Parte non valida: {chunk!r}")
        key, value = chunk.split("=", 1)
        key = key.strip().upper()
        if key in parts:
            raise RecurrenceError("RRULE_INVALID", f"Parte duplicata: {key}")
        parts[key] = value.strip().upper()
    unsupported = sorted(set(parts) - {"FREQ", "INTERVAL", "BYDAY", "UNTIL"})
    if unsupported:
        raise RecurrenceError(
            "RRULE_UNSUPPORTED",
            "Parti RRULE non supportate: rifiutate, non ignorate",
            parts=unsupported,
        )
    if parts.get("FREQ") != "WEEKLY":
        raise RecurrenceError("RRULE_UNSUPPORTED", "Solo FREQ=WEEKLY è supportata")
    try:
        interval = int(parts.get("INTERVAL", "1"))
    except ValueError as error:
        raise RecurrenceError("RRULE_INVALID", "INTERVAL intero richiesto") from error
    if not 1 <= interval <= 52:
        raise RecurrenceError("RRULE_INVALID", "INTERVAL tra 1 e 52")
    days = [d.strip() for d in parts.get("BYDAY", "").split(",") if d.strip()]
    if not days or any(d not in DAYS for d in days) or len(set(days)) != len(days):
        raise RecurrenceError(
            "RRULE_INVALID", "BYDAY obbligatorio: MO..SU senza prefissi numerici"
        )
    if "UNTIL" not in parts:
        raise RecurrenceError(
            "RRULE_UNBOUNDED", "UNTIL obbligatorio: la serie deve avere un termine"
        )
    until = parse_until(parts["UNTIL"], zone)
    return Rule(interval, tuple(sorted(DAYS.index(d) for d in days)), until)


def parse_until(value, zone=SUPPORTED_TIMEZONE):
    """UNTIL come data locale inclusa. Forma UTC convertita nella data locale."""
    try:
        if len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").date()
        if len(value) == 16 and value.endswith("Z"):
            moment = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
            return moment.astimezone(ZoneInfo(zone)).date()
    except ValueError:
        pass
    raise RecurrenceError(
        "RRULE_INVALID", "UNTIL nel formato AAAAMMGG o AAAAMMGGTHHMMSSZ"
    )


def format_rrule(rule):
    parts = ["FREQ=WEEKLY"]
    if rule.interval != 1:
        parts.append(f"INTERVAL={rule.interval}")
    parts.append("BYDAY=" + ",".join(DAYS[d] for d in rule.byday))
    parts.append("UNTIL=" + rule.until.strftime("%Y%m%d"))
    return ";".join(parts)


def monday(day):
    return day - timedelta(days=day.weekday())


def nominal_dates(start_date, rule, until_date=None, first=None, last=None):
    """Date locali nominali della serie in [first, last) e entro until_date (inclusa).

    L'intervallo di settimane è ancorato alla settimana di DTSTART; DTSTART stesso
    deve appartenere a BYDAY (come raccomandato da RFC 5545)."""
    if start_date.weekday() not in rule.byday:
        raise RecurrenceError(
            "DTSTART_NOT_IN_BYDAY", "La data iniziale deve cadere in un giorno BYDAY"
        )
    end = min(rule.until, until_date) if until_date else rule.until
    anchor = monday(start_date)
    day = max(start_date, first) if first else start_date
    result = []
    while day <= end and (last is None or day < last):
        weeks = (monday(day) - anchor).days // 7
        if (
            day >= start_date
            and weeks % rule.interval == 0
            and day.weekday() in rule.byday
        ):
            result.append(day)
        day += timedelta(days=1)
    return result


def local_start(day, start_time, zone=SUPPORTED_TIMEZONE):
    try:
        return local_to_utc(datetime.combine(day, start_time), zone)
    except ValueError as error:
        raise RecurrenceError(
            "INVALID_LOCAL_TIME",
            "Ora locale inesistente o ambigua per il cambio d'ora: approvazione esplicita richiesta",
            date=day.isoformat(),
        ) from error


def occurrence_key(root_id, day):
    return f"series:{root_id}/{day.isoformat()}"


def parse_override(value):
    """Override "solo questa" non materializzata: 'AAAA-MM-GGTHH:MM' locale."""
    try:
        moment = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError) as error:
        raise RecurrenceError(
            "OVERRIDE_INVALID", "Override come AAAA-MM-GGTHH:MM locale"
        ) from error
    return moment.date(), moment.time()


def expand(series_like, first=None, last=None):
    """Occorrenze (chiave, data nominale, inizio UTC, fine UTC) di un segmento.

    ``series_like`` espone start_date, start_time, duration_minutes, rrule,
    until_date, exdates, overrides, timezone e root id. EXDATE escluse senza
    cambiare la chiave delle altre istanze; override spostano solo l'istanza indicata."""
    rule = parse_rrule(series_like.rrule, series_like.timezone)
    root = series_like.root_id or series_like.id
    excluded = set(series_like.exdates or [])
    overrides = series_like.overrides or {}
    out = []
    for day in nominal_dates(
        series_like.start_date, rule, series_like.until_date, first, last
    ):
        iso = day.isoformat()
        if iso in excluded:
            continue
        if iso in overrides:
            actual_day, actual_time = parse_override(overrides[iso])
        else:
            actual_day, actual_time = day, series_like.start_time
        start = local_start(actual_day, actual_time, series_like.timezone)
        out.append(
            {
                "key": occurrence_key(root, day),
                "nominal_date": iso,
                "start_at": start,
                "end_at": start + timedelta(minutes=series_like.duration_minutes),
                "overridden": iso in overrides,
            }
        )
    return out


def week_bounds(week_start, zone=SUPPORTED_TIMEZONE):
    return (
        local_to_utc(datetime.combine(week_start, time.min), zone),
        local_to_utc(datetime.combine(week_start + timedelta(days=7), time.min), zone),
    )
