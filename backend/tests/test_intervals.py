from datetime import datetime, date, time, timezone
import pytest
from domain.intervals import (
    Interval,
    normalize,
    subtract,
    intersect,
    compile_effective,
    local_to_utc,
    expand_weekly,
)


def i(a, b):
    return Interval(
        datetime(2026, 10, 5, a, tzinfo=timezone.utc),
        datetime(2026, 10, 5, b, tzinfo=timezone.utc),
    )


def test_adjacent_merged():
    assert normalize([i(9, 10), i(10, 11)]) == [i(9, 11)]


def test_removal_prevails():
    assert compile_effective([i(9, 12)], [i(10, 13)], [i(11, 12)], "APPROVED") == [
        i(9, 11),
        i(12, 13),
    ]


def test_intersection_all_participants():
    assert intersect([i(9, 12)], [i(10, 13)], [i(11, 14)]) == [i(11, 12)]


def test_boundary_not_overlap():
    assert intersect([i(9, 10)], [i(10, 11)]) == []


def test_unknown_blocks():
    with pytest.raises(ValueError):
        compile_effective([], [], [], "UNKNOWN")


def test_declared_none():
    assert compile_effective([i(9, 12)], [], [], "DECLARED_NONE") == []


def test_dst_local_hour_stable():
    intervals = expand_weekly(
        2,
        time(16),
        time(17),
        date(2026, 10, 1),
        date(2026, 10, 31),
        date(2026, 10, 21),
        date(2026, 10, 29),
    )
    assert [v.start.hour for v in intervals] == [14, 15]


@pytest.mark.parametrize(
    "local", [datetime(2026, 3, 29, 2, 30), datetime(2026, 10, 25, 2, 30)]
)
def test_dst_invalid_or_ambiguous(local):
    with pytest.raises(ValueError):
        local_to_utc(local)


def test_horizon_end_exclusive():
    assert (
        expand_weekly(
            2,
            time(16),
            time(17),
            date(2026, 10, 7),
            date(2026, 10, 7),
            date(2026, 10, 1),
            date(2026, 10, 7),
        )
        == []
    )


def test_naive_rejected():
    with pytest.raises(ValueError):
        Interval(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 10))
