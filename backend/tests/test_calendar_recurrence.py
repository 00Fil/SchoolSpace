"""GAP-E01 (s2-calendario): sottoinsieme RRULE, EXDATE, chiavi stabili, DST. Puri."""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings, strategies as st

from apps.calendar.recurrence import (
    RecurrenceError,
    expand,
    format_rrule,
    local_start,
    nominal_dates,
    occurrence_key,
    parse_rrule,
)

ROME = ZoneInfo("Europe/Rome")
NAMES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def series(**extra):
    base = dict(
        id="root-1",
        root_id=None,
        start_date=date(2026, 10, 7),
        start_time=time(16, 0),
        duration_minutes=60,
        rrule="FREQ=WEEKLY;BYDAY=WE;UNTIL=20261216T150000Z",
        until_date=None,
        exdates=[],
        overrides={},
        timezone="Europe/Rome",
    )
    base.update(extra)
    return SimpleNamespace(**base)


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


def test_t12_paper_example_exdate_and_dst():
    rows = expand(series(exdates=["2026-10-14"]))
    starts = [r["start_at"] for r in rows]
    assert utc(2026, 10, 7, 14) in starts
    assert utc(2026, 10, 14, 14) not in starts  # EXDATE
    assert utc(2026, 10, 21, 14) in starts  # CEST
    assert utc(2026, 10, 28, 15) in starts  # CET dopo il cambio d'ora
    assert rows[-1]["nominal_date"] == "2026-12-16"  # UNTIL UTC → data locale inclusa
    assert all(r["start_at"].astimezone(ROME).hour == 16 for r in rows)
    assert len(rows) == 10


def test_keys_stable_under_exdate_and_override():
    plain = {r["nominal_date"]: r["key"] for r in expand(series())}
    changed = expand(
        series(exdates=["2026-10-14"], overrides={"2026-10-21": "2026-10-22T09:30"})
    )
    for row in changed:
        assert plain[row["nominal_date"]] == row["key"]
    moved = next(r for r in changed if r["nominal_date"] == "2026-10-21")
    assert moved["overridden"] and moved["start_at"] == utc(2026, 10, 22, 7, 30)
    assert occurrence_key("root-1", date(2026, 10, 21)) == "series:root-1/2026-10-21"


def test_segment_uses_root_key():
    rows = expand(series(id="seg-2", root_id="root-1", start_date=date(2026, 11, 4)))
    assert rows[0]["key"] == "series:root-1/2026-11-04"


@pytest.mark.parametrize(
    "text,code",
    [
        ("FREQ=DAILY;BYDAY=MO;UNTIL=20261231", "RRULE_UNSUPPORTED"),
        ("FREQ=WEEKLY;BYDAY=MO;COUNT=3;UNTIL=20261231", "RRULE_UNSUPPORTED"),
        ("FREQ=WEEKLY;BYDAY=MO;BYSETPOS=1;UNTIL=20261231", "RRULE_UNSUPPORTED"),
        ("FREQ=WEEKLY;BYDAY=MO", "RRULE_UNBOUNDED"),
        ("FREQ=WEEKLY;UNTIL=20261231", "RRULE_INVALID"),
        ("FREQ=WEEKLY;BYDAY=1MO;UNTIL=20261231", "RRULE_INVALID"),
        ("FREQ=WEEKLY;BYDAY=MO,MO;UNTIL=20261231", "RRULE_INVALID"),
        ("FREQ=WEEKLY;INTERVAL=0;BYDAY=MO;UNTIL=20261231", "RRULE_INVALID"),
        ("FREQ=WEEKLY;BYDAY=MO;UNTIL=2026-12-31", "RRULE_INVALID"),
        ("FREQ=WEEKLY;FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231", "RRULE_INVALID"),
        ("", "RRULE_INVALID"),
    ],
)
def test_unsupported_parts_rejected_not_ignored(text, code):
    with pytest.raises(RecurrenceError) as error:
        parse_rrule(text)
    assert error.value.code == code


def test_timezone_and_dtstart_checks():
    with pytest.raises(RecurrenceError) as error:
        parse_rrule("FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231", "Europe/London")
    assert error.value.code == "TIMEZONE_UNSUPPORTED"
    rule = parse_rrule("FREQ=WEEKLY;BYDAY=MO;UNTIL=20261231")
    with pytest.raises(RecurrenceError) as error:
        nominal_dates(date(2026, 10, 6), rule)
    assert error.value.code == "DTSTART_NOT_IN_BYDAY"


def test_interval_anchored_on_dtstart_week():
    rule = parse_rrule("RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;UNTIL=20261029")
    days = nominal_dates(date(2026, 10, 8), rule)
    assert days == [date(2026, 10, 8), date(2026, 10, 19), date(2026, 10, 22)]
    assert format_rrule(rule) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;UNTIL=20261029"


def test_invalid_local_time_on_spring_forward():
    with pytest.raises(RecurrenceError) as error:
        local_start(date(2027, 3, 28), time(2, 30))
    assert error.value.code == "INVALID_LOCAL_TIME"
    with pytest.raises(RecurrenceError) as error:
        expand(
            series(
                start_date=date(2027, 3, 21),
                start_time=time(2, 30),
                rrule="FREQ=WEEKLY;BYDAY=SU;UNTIL=20270404",
            )
        )
    assert error.value.code == "INVALID_LOCAL_TIME"


@settings(max_examples=60, deadline=None)
@given(
    start=st.dates(min_value=date(2026, 1, 5), max_value=date(2028, 12, 25)),
    days=st.sets(st.integers(0, 6), min_size=1, max_size=7),
    interval=st.integers(1, 4),
    weeks=st.integers(1, 30),
    hour=st.sampled_from([8, 10, 15, 18, 20]),
    excluded=st.integers(0, 10),
)
def test_property_local_time_keys_and_exdates(
    start, days, interval, weeks, hour, excluded
):
    start = start + timedelta(days=(min(days) - start.weekday()) % 7)
    until = start + timedelta(weeks=weeks)
    names = ",".join(NAMES[d] for d in sorted(days))
    rule = f"FREQ=WEEKLY;INTERVAL={interval};BYDAY={names};UNTIL={until:%Y%m%d}"
    base = expand(series(start_date=start, start_time=time(hour), rrule=rule))
    keys = [r["key"] for r in base]
    assert len(keys) == len(set(keys))
    assert base and base[0]["nominal_date"] == start.isoformat()
    for row in base:
        local = row["start_at"].astimezone(ROME)
        assert local.hour == hour and local.date().isoformat() == row["nominal_date"]
        assert local.weekday() in days
        assert row["end_at"] - row["start_at"] == timedelta(minutes=60)
    drop = [r["nominal_date"] for r in base[:: max(1, excluded)]][:excluded]
    rest = expand(
        series(start_date=start, start_time=time(hour), rrule=rule, exdates=drop)
    )
    assert [r["key"] for r in rest] == [
        k for r, k in zip(base, keys) if r["nominal_date"] not in drop
    ]
