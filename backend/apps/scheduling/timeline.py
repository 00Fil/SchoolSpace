"""Cached minute -> Europe/Rome calendar helpers shared by compiler and objectives.

Minutes are integers from the DTO's explicit UTC epoch; every conversion goes
through ``zoneinfo`` so DST weeks (167/169 hours) are handled exactly.
"""

from datetime import timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo
from .contracts import utc_epoch


@lru_cache(maxsize=512)
def _zone(name):
    return ZoneInfo(name)


@lru_cache(maxsize=262144)
def _local(epoch_text, zone_name, minute):
    from datetime import datetime, timezone

    epoch = datetime.fromisoformat(epoch_text.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    return (epoch + timedelta(minutes=minute)).astimezone(_zone(zone_name))


def local(data, minute):
    return _local(data["epoch"], data["timezone"], minute)


def day_key(data, minute):
    return local(data, minute).date().isoformat()


def week_key(data, minute):
    iso = local(data, minute).isocalendar()
    return (iso.year, iso.week)


def slot(data, minute):
    """Local (weekday, minute of day) of an instant: the recurring-slot identity."""
    moment = local(data, minute)
    return moment.weekday(), moment.hour * 60 + moment.minute


def crosses_local_midnight(data, start, end):
    return day_key(data, start) != day_key(data, end - 1)


__all__ = ["utc_epoch", "local", "day_key", "week_key", "slot"]
