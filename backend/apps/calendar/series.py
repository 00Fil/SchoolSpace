"""Comandi LessonSeries (GAP-E01): creazione, EXDATE, "solo questa", "questa e successive".

Le date non ancora materializzate e pubblicate non sono appuntamenti: la serie
proietta blocchi nel DTO di pianificazione (context.project_series) e il centro
pubblica la proposta. Le lezioni concluse o iniziate non vengono mai riscritte.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
from django.db import transaction
from apps.education.models import TeachingRequest, Tutor, Resource
from apps.scheduling.revision import bump_revision
from .models import LessonSeries, LessonOccurrence
from .recurrence import (
    RecurrenceError,
    parse_rrule,
    nominal_dates,
    expand,
    local_start,
    monday,
    parse_override,
    occurrence_key,
)
from .commands import (
    Command,
    audit,
    event,
    require_reason,
    check_version,
    now,
    DomainError,
)
from .operations import (
    lock_lessons,
    change_lessons,
    cancel_lesson,
    require_future_active,
)


def recurrence_error(error):
    return DomainError(error.code, error.message, **error.extra)


def series_summary(series):
    return {
        "id": str(series.id),
        "root_id": str(series.root_id or series.id),
        "parent_id": str(series.parent_id) if series.parent_id else None,
        "request_id": str(series.request_id),
        "timezone": series.timezone,
        "start_date": series.start_date.isoformat(),
        "start_time": series.start_time.strftime("%H:%M"),
        "duration_minutes": series.duration_minutes,
        "rrule": series.rrule,
        "until_date": series.until_date.isoformat(),
        "exdates": sorted(series.exdates),
        "overrides": dict(sorted(series.overrides.items())),
        "carried": dict(sorted(series.carried.items())),
        "tutor_id": str(series.tutor_id),
        "mode": series.mode,
        "location": series.location,
        "space_id": str(series.space_id) if series.space_id else None,
        "video_id": str(series.video_id) if series.video_id else None,
        "state": series.state,
        "version": series.version,
    }


def nominal_of(key):
    return date.fromisoformat(key.rsplit("/", 1)[1])


def check_shape(series, request):
    """Invarianti di un segmento, prima del salvataggio."""
    try:
        rule = parse_rrule(series.rrule, series.timezone)
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    series.until_date = rule.until
    if (
        series.start_date < request.period_start
        or series.until_date > request.period_end
    ):
        raise DomainError(
            "SERIES_OUTSIDE_REQUEST", "Periodo della serie fuori dalla richiesta"
        )
    if series.duration_minutes != request.duration_minutes:
        raise DomainError("SERIES_DURATION_MISMATCH", "Durata diversa dalla richiesta")
    if request.mode and series.mode != request.mode:
        raise DomainError("SERIES_MODE_MISMATCH", "Modalità diversa dalla richiesta")
    if series.mode == "IN_PERSON" and (
        series.location != "ON_SITE" or not series.space_id
    ):
        raise DomainError("SPACE_REQUIRED", "Presenza in sede con spazio obbligatorio")
    if (
        series.space_id
        and not Resource.objects.filter(pk=series.space_id, kind="SPACE").exists()
    ):
        raise DomainError("SPACE_REQUIRED", "Spazio inesistente")
    if (
        series.video_id
        and not Resource.objects.filter(
            pk=series.video_id, kind="VIDEO_CHANNEL"
        ).exists()
    ):
        raise DomainError("VIDEO_REQUIRED", "Canale video inesistente")
    if not Tutor.objects.filter(pk=series.tutor_id).exists():
        raise DomainError("NOT_FOUND", "Tutor inesistente")
    try:
        days = nominal_dates(series.start_date, rule, series.until_date)
        bad = set(series.exdates) - {d.isoformat() for d in days}
        if bad:
            raise DomainError(
                "EXDATE_NOT_IN_SERIES",
                "EXDATE non corrispondenti a istanze della serie",
                dates=sorted(bad),
            )
        for nominal, value in series.overrides.items():
            day, _ = parse_override(value)
            if nominal not in {d.isoformat() for d in days} or monday(day) != monday(
                date.fromisoformat(nominal)
            ):
                raise DomainError(
                    "OVERRIDE_INVALID",
                    "Override solo su istanze della serie e nella stessa settimana",
                )
        expand(series)
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    return rule


def check_weekly_demand(series, request, exclude_ids=()):
    """Occorrenze per settimana (tutti i segmenti attivi) ≤ sessions_per_week."""
    others = LessonSeries.objects.filter(request=request, state="ACTIVE").exclude(
        pk__in=list(exclude_ids)
    )
    counts = defaultdict(int)
    for segment in [*others, series]:
        try:
            for occ in expand(segment):
                counts[monday(date.fromisoformat(occ["nominal_date"]))] += 1
        except RecurrenceError as error:
            raise recurrence_error(error) from error
    over = sorted(
        w.isoformat() for w, n in counts.items() if n > request.sessions_per_week
    )
    if over:
        raise DomainError(
            "SERIES_EXCEEDS_DEMAND",
            "Le serie superano le sessioni settimanali della richiesta: nessuna duplicazione",
            weeks=over[:10],
        )


@transaction.atomic
def create_series(actor, command, key):
    cmd = Command(actor, "calendar-series-create", key, command)
    if cmd.replay:
        return cmd.replay
    reason = require_reason(command)
    request = (
        TeachingRequest.objects.select_for_update()
        .filter(pk=command["request_id"])
        .first()
    )
    if not request:
        raise DomainError("NOT_FOUND", "Richiesta inesistente")
    series = LessonSeries(
        request=request,
        start_date=command["start_date"],
        start_time=command["start_time"],
        duration_minutes=request.duration_minutes,
        rrule=command["rrule"],
        until_date=command["start_date"],
        exdates=sorted({d.isoformat() for d in command.get("exdates", [])}),
        overrides={},
        tutor_id=command["tutor_id"],
        mode=command["mode"],
        location=command["location"],
        space_id=command.get("space_id"),
        video_id=command.get("video_id"),
        created_by=cmd.actor,
    )
    check_shape(series, request)
    check_weekly_demand(series, request)
    series.save()
    linked = None
    if command.get("origin_lesson_id"):
        (lesson,) = lock_lessons([command["origin_lesson_id"]])
        require_future_active(lesson)
        occurrences = {o["start_at"]: o for o in expand(series)}
        occ = occurrences.get(lesson.start_at)
        if (
            lesson.demand.request_id != request.id
            or lesson.recurrence_key
            or lesson.recovery_id
            or occ is None
            or (str(lesson.tutor_id), lesson.mode, lesson.location)
            != (str(series.tutor_id), series.mode, series.location)
        ):
            raise DomainError(
                "ORIGIN_LESSON_MISMATCH",
                "La lezione d'origine deve coincidere con un'istanza della serie",
            )
        lesson.series = series
        lesson.recurrence_key = occ["key"]
        lesson.save(update_fields=["series", "recurrence_key", "updated_at"])
        linked = str(lesson.id)
    audit(cmd.actor, "SERIES_CREATE", reason, obj=series, after=series_summary(series))
    event("SERIES_CREATED", f"series:{series.id}:v1", {"series_id": str(series.id)})
    bump_revision()
    return cmd.done(
        {
            **series_summary(series),
            "linked_lesson_id": linked,
            "revision": cmd.revision.revision + 1,
            "experimental": True,
        }
    )


def lock_series(series_id, expected_version):
    series = (
        LessonSeries.objects.select_for_update(of=("self",))
        .select_related("request")
        .filter(pk=series_id)
        .first()
    )
    if not series:
        raise DomainError("NOT_FOUND", "Serie inesistente")
    check_version(series, expected_version)
    if series.state != "ACTIVE":
        raise DomainError(
            "SERIES_CLOSED", "Segmento chiuso: usare il segmento successivo"
        )
    return series


def nominal_in(series, day):
    rule = parse_rrule(series.rrule, series.timezone)
    if day not in nominal_dates(series.start_date, rule, series.until_date):
        raise DomainError("DATE_NOT_IN_SERIES", "Data non corrispondente a un'istanza")


def finish(cmd, series, operation, reason, before, extra=None):
    series.version += 1
    series.save()
    audit(
        cmd.actor,
        operation,
        reason,
        obj=series,
        before=before,
        after=series_summary(series),
    )
    event(
        "SERIES_" + operation[7:],
        f"series:{series.id}:v{series.version}",
        {"series_id": str(series.id)},
    )
    bump_revision()
    return cmd.done(
        {
            **series_summary(series),
            **(extra or {}),
            "revision": cmd.revision.revision + 1,
            "experimental": True,
        }
    )


@transaction.atomic
def add_exdate(actor, series_id, command, key):
    """ "Solo questa" come esclusione: la chiave delle altre istanze non cambia."""
    cmd = Command(
        actor, "calendar-series-exdate", key, {"series_id": str(series_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    series = lock_series(series_id, command["expected_version"])
    reason = require_reason(command)
    day = command["date"]
    nominal_in(series, day)
    if day.isoformat() in series.exdates:
        raise DomainError("ALREADY_EXCLUDED", "Data già esclusa")
    if local_start(day, series.start_time) <= now():
        raise DomainError("PAST_OCCURRENCE", "Istanza passata: nessuna riscrittura")
    before = series_summary(series)
    cancelled = None
    lesson = LessonOccurrence.objects.filter(
        recurrence_key=occurrence_key(series.root_id or series.id, day)
    ).first()
    if lesson and lesson.state == "COMPLETED":
        raise DomainError("PAST_OCCURRENCE", "Istanza conclusa: nessuna riscrittura")
    if lesson and lesson.state == "PUBLISHED":
        (lesson,) = lock_lessons([lesson.id])
        cancel_lesson(cmd.actor, lesson, reason, "SERIES_EXDATE_CANCEL")
        cancelled = str(lesson.id)
    series.exdates = sorted({*series.exdates, day.isoformat()})
    series.overrides.pop(day.isoformat(), None)
    return finish(
        cmd, series, "SERIES_EXDATE", reason, before, {"cancelled_lesson_id": cancelled}
    )


@transaction.atomic
def override_occurrence(actor, series_id, command, key):
    """ "Solo questa" per un'istanza non ancora materializzata."""
    cmd = Command(
        actor, "calendar-series-override", key, {"series_id": str(series_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    series = lock_series(series_id, command["expected_version"])
    reason = require_reason(command)
    day = command["date"]
    nominal_in(series, day)
    if day.isoformat() in series.exdates:
        raise DomainError("ALREADY_EXCLUDED", "Data esclusa")
    if LessonOccurrence.objects.filter(
        recurrence_key=occurrence_key(series.root_id or series.id, day)
    ).exists():
        raise DomainError(
            "OCCURRENCE_MATERIALIZED",
            "Istanza già pubblicata: usare spostamento/modifica della lezione",
        )
    moment = command["local_start"]
    try:
        start = local_start(moment.date(), moment.time())
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    if start <= now() or local_start(day, series.start_time) <= now():
        raise DomainError("PAST_OCCURRENCE", "Istanza passata: nessuna riscrittura")
    if monday(moment.date()) != monday(day):
        raise DomainError("OVERRIDE_INVALID", "Override solo nella stessa settimana")
    before = series_summary(series)
    series.overrides = {
        **series.overrides,
        day.isoformat(): moment.strftime("%Y-%m-%dT%H:%M"),
    }
    return finish(cmd, series, "SERIES_OVERRIDE", reason, before)


SPLIT_FIELDS = {
    "start_time",
    "rrule",
    "tutor_id",
    "mode",
    "location",
    "space_id",
    "video_id",
}


@transaction.atomic
def split_series(actor, series_id, command, key):
    """ "Questa e successive": chiude il segmento e crea il successivo (T14)."""
    cmd = Command(
        actor, "calendar-series-split", key, {"series_id": str(series_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    old = lock_series(series_id, command["expected_version"])
    reason = require_reason(command)
    changes = dict(command.get("changes") or {})
    if not changes or set(changes) - SPLIT_FIELDS:
        raise DomainError(
            "NO_CHANGES", "Indicare le modifiche ammesse del nuovo segmento"
        )
    pivot = command["from_date"]
    nominal_in(old, pivot)
    if local_start(pivot, old.start_time) <= now():
        raise DomainError("PAST_OCCURRENCE", "La modifica parte da un'istanza futura")
    request = old.request
    new = LessonSeries(
        root_id=old.root_id or old.id,
        parent=old,
        request=request,
        timezone=old.timezone,
        start_date=pivot,
        start_time=changes.get("start_time", old.start_time),
        duration_minutes=old.duration_minutes,
        rrule=changes.get("rrule", old.rrule),
        until_date=pivot,
        exdates=[],
        overrides={},
        carried={},
        tutor_id=changes.get("tutor_id", old.tutor_id),
        mode=changes.get("mode", old.mode),
        location=changes.get("location", old.location),
        space_id=changes.get("space_id", old.space_id)
        if "space_id" in changes
        else old.space_id,
        video_id=changes.get("video_id", old.video_id)
        if "video_id" in changes
        else old.video_id,
        created_by=cmd.actor,
    )
    try:
        rule = parse_rrule(new.rrule, new.timezone)
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    first = pivot
    while first.weekday() not in rule.byday:
        first += timedelta(days=1)
    new.start_date = first
    kept = {d for d in old.exdates if d >= pivot.isoformat()}
    before = series_summary(old)
    old.until_date = max(old.start_date, pivot - timedelta(days=1))
    old.exdates = sorted(d for d in old.exdates if d < pivot.isoformat())
    old.overrides = {k: v for k, v in old.overrides.items() if k < pivot.isoformat()}
    closing = pivot <= old.start_date
    old.state = "CLOSED" if closing else "ACTIVE"
    old.rrule = old.rrule if closing else _with_until(old.rrule, old.until_date)
    check_shape(new, request)
    try:
        dates = {
            d.isoformat() for d in nominal_dates(new.start_date, rule, new.until_date)
        }
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    new.exdates = sorted(kept & dates)
    old.version += 1
    old.save()
    check_weekly_demand(new, request)
    new.save()
    # Lezioni future già pubblicate del segmento chiuso: riallineate al nuovo slot.
    lessons = list(
        LessonOccurrence.objects.filter(
            series=old, state="PUBLISHED", start_at__gt=now()
        ).order_by("start_at", "id")
    )
    lessons = [l for l in lessons if nominal_of(l.recurrence_key) >= pivot]
    lessons = lock_lessons([l.id for l in lessons]) if lessons else []
    targets = defaultdict(list)
    for occ in expand(new):
        targets[monday(date.fromisoformat(occ["nominal_date"]))].append(occ)
    moves, cancels, carried = [], [], {}
    by_week = defaultdict(list)
    for lesson in lessons:
        by_week[monday(nominal_of(lesson.recurrence_key))].append(lesson)
    for week, items in by_week.items():
        slots = list(targets.get(week, []))
        pairs = []
        for lesson in list(items):
            same = next(
                (
                    o
                    for o in slots
                    if o["nominal_date"]
                    == nominal_of(lesson.recurrence_key).isoformat()
                ),
                None,
            )
            if same:
                pairs.append((lesson, same))
                slots.remove(same)
                items.remove(lesson)
        for lesson in items:
            if slots:
                pairs.append((lesson, slots.pop(0)))
            else:
                cancels.append(lesson)
        for lesson, occ in pairs:
            carried[occ["nominal_date"]] = lesson.recurrence_key
            moves.append(
                (
                    lesson,
                    {
                        "start_at": occ["start_at"],
                        "tutor_id": str(new.tutor_id),
                        "mode": new.mode,
                        "location": new.location,
                        "space_id": str(new.space_id) if new.space_id else None,
                        "video_id": str(new.video_id) if new.video_id else None,
                    },
                )
            )
    moved = []
    if moves:
        moved = change_lessons(
            cmd.actor,
            moves,
            "SERIES_SPLIT",
            reason,
            extra_after={"series_id": str(new.id)},
        )
        for lesson, _ in moves:
            lesson.series = new
            lesson.save(update_fields=["series", "updated_at"])
    cancelled = [
        cancel_lesson(cmd.actor, l, reason, "SERIES_SPLIT_CANCEL") for l in cancels
    ]
    new.carried = carried
    new.save(update_fields=["carried", "updated_at"])
    audit(
        cmd.actor,
        "SERIES_SPLIT",
        reason,
        obj=old,
        before=before,
        after=series_summary(old),
    )
    audit(cmd.actor, "SERIES_CREATE", reason, obj=new, after=series_summary(new))
    event(
        "SERIES_SPLIT",
        f"series:{old.id}:v{old.version}",
        {"series_id": str(old.id), "next_series_id": str(new.id)},
    )
    bump_revision()
    return cmd.done(
        {
            "closed": series_summary(old),
            "next": series_summary(new),
            "moved_lessons": moved,
            "cancelled_lessons": cancelled,
            "revision": cmd.revision.revision + 1,
            "experimental": True,
        }
    )


def _with_until(text, until):
    parts = [p for p in text.split(";") if not p.upper().startswith("UNTIL=")]
    return ";".join([*parts, "UNTIL=" + until.strftime("%Y%m%d")])


def occurrences(series, first, last):
    """Diagnostica delle istanze: materializzate, escluse o solo previste."""
    try:
        rule = parse_rrule(series.rrule, series.timezone)
        days = nominal_dates(series.start_date, rule, series.until_date, first, last)
        expanded = {o["nominal_date"]: o for o in expand(series, first, last)}
    except RecurrenceError as error:
        raise recurrence_error(error) from error
    root = series.root_id or series.id
    lessons = {
        l.recurrence_key: l
        for l in LessonOccurrence.objects.filter(
            recurrence_key__in=[occurrence_key(root, d) for d in days]
            + list((series.carried or {}).values())
        )
    }
    out = []
    for day in days:
        iso = day.isoformat()
        key = (series.carried or {}).get(iso) or occurrence_key(root, day)
        lesson = lessons.get(key)
        occ = expanded.get(iso)
        out.append(
            {
                "key": key,
                "nominal_date": iso,
                "status": "EXCLUDED"
                if iso in series.exdates
                else ("MATERIALIZED" if lesson else "PROJECTED"),
                "start_at": (lesson.start_at if lesson else occ["start_at"]).isoformat()
                if (lesson or occ)
                else None,
                "lesson_id": str(lesson.id) if lesson else None,
                "lesson_state": lesson.state if lesson else None,
                "overridden": bool(occ and occ["overridden"]),
            }
        )
    return out


def parse_local(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError) as error:
        raise DomainError("OVERRIDE_INVALID", "Ora locale AAAA-MM-GGTHH:MM") from error
