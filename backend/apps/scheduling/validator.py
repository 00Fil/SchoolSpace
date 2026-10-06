"""Independent checks over raw DTO, never calls the candidate compiler or CP-SAT.

v0.5 adds: student location (online from the centre needs a seat), student
buffer, optional lessons across local midnight, enrolment periods (H12),
curricular sequences (H12), family constraints/synchronisations (H11) and
required recurring slots.
"""

from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo
from .contracts import utc_epoch

FIELDS = {
    "demand_key",
    "tutor_id",
    "mode",
    "location",
    "space_id",
    "video_id",
    "start",
    "end",
}
STUDENT_FIELDS = {"student_location", "student_space_id"}


def _local_slot(epoch, zone, minute):
    moment = (epoch + timedelta(minutes=minute)).astimezone(zone)
    return moment.weekday(), moment.hour * 60 + moment.minute


def _same(a, b):
    def norm(x):
        x = dict(x)
        if x.get("student_location") and not (
            x["student_location"] == "ON_SITE" and x["mode"] == "ONLINE"
        ):
            if x.get("student_space_id") is None:
                x.pop("student_location")
                x.pop("student_space_id")
        return x

    return norm(a) == norm(b)


def validate_assignments(data, assignments, require_coverage=True):
    units = {u["demand_key"]: u for u in data["units"]}
    tutors = {t["id"]: t for t in data["tutors"]}
    students = {s["id"]: s for s in data["students"]}
    resources = {r["id"]: r for r in data["resources"]}
    violations = []
    seen = set()
    bookings = defaultdict(list)
    daily = defaultdict(int)
    weekly = defaultdict(int)
    by_tutor = defaultdict(list)
    epoch = utc_epoch(data)
    zone = ZoneInfo(data["timezone"])
    v05 = data["schema_version"] == "0.5"
    student_buffer = data["student_buffer_minutes"]
    enrollment = {e["student_id"]: e["periods"] for e in data.get("enrollments", [])}
    placed = {}

    def fail(code, key):
        violations.append({"code": code, "demand_key": key})

    def contains(windows, start, end):
        # Independent union sweep: compiler uses integer start sets instead.
        cursor = start
        for window in sorted(windows, key=lambda w: (w["start"], w["end"])):
            if window["end"] <= cursor:
                continue
            if window["start"] > cursor:
                break
            cursor = max(cursor, window["end"])
            if cursor >= end:
                return True
        return False

    for a in assignments:
        if (
            not isinstance(a, dict)
            or (set(a) != FIELDS and not (v05 and set(a) == FIELDS | STUDENT_FIELDS))
            or type(a.get("start")) is not int
            or type(a.get("end")) is not int
        ):
            fail("ASSIGNMENT_SCHEMA", "unknown")
            continue
        if (
            any(
                type(a[field]) is not str
                for field in ("demand_key", "tutor_id", "mode", "location")
            )
            or any(
                a.get(field) is not None and type(a.get(field)) is not str
                for field in ("space_id", "video_id", "student_space_id")
            )
            or a.get("student_location", "ON_SITE") not in ("ON_SITE", "REMOTE")
            or a["start"] < 0
            or a["start"] >= a["end"]
            or a["end"] > data["horizon_minutes"]
        ):
            fail("ASSIGNMENT_SCHEMA", "unknown")
            continue
        key = a["demand_key"]
        u = units.get(key)
        t = tutors.get(a["tutor_id"])
        start, end = a["start"], a["end"]
        if key in seen:
            fail("DUPLICATE_ASSIGNMENT", key)
        seen.add(key)
        if not u or not t:
            fail("UNKNOWN_REFERENCE", key)
            continue
        if t["availability_state"] in ("UNKNOWN", "DECLARED_NONE"):
            fail("TUTOR_AVAILABILITY", key)
        if (
            a["tutor_id"] not in u["allowed_tutors"]
            or a["mode"] not in u["allowed_modes"]
        ):
            fail("ILLEGAL_OPTION", key)
        if a["mode"] not in ("IN_PERSON", "ONLINE") or a["location"] not in (
            "ON_SITE",
            "REMOTE",
        ):
            fail("ILLEGAL_OPTION", key)
            continue
        if (
            start % data["grid_minutes"]
            or end - start != u["duration_minutes"]
            or start < u["earliest_start"]
            or end > u["latest_end"]
            or end <= start
        ):
            fail("DURATION_OR_WINDOW", key)
        local = (epoch + timedelta(minutes=start)).astimezone(zone)
        last = (epoch + timedelta(minutes=end - 1)).astimezone(zone)
        if local.date() != last.date() and not data["allow_cross_local_midnight"]:
            fail("CROSS_LOCAL_MIDNIGHT", key)
        where = a.get("student_location") or (
            "ON_SITE" if a["mode"] == "IN_PERSON" else "REMOTE"
        )
        seat = resources.get(a.get("student_space_id"))
        if a["mode"] == "IN_PERSON" and (
            where != "ON_SITE" or a.get("student_space_id") is not None
        ):
            fail("STUDENT_LOCATION", key)
        if a["mode"] == "ONLINE" and where == "REMOTE" and a.get("student_space_id"):
            fail("STUDENT_LOCATION", key)
        if a["mode"] == "ONLINE" and where == "ON_SITE":
            if (
                not seat
                or seat["kind"] != "SPACE"
                or a["location"] != "REMOTE"
                or len(u["participants"]) > seat["student_capacity"]
            ):
                fail("STUDENT_SEAT_REQUIRED", key)
                seat = None
            elif not contains(
                [w for w in data["service_windows"] if w["location"] == "ON_SITE"],
                start,
                end + seat["buffer_minutes"],
            ):
                fail("SERVICE_CLOSED", key)
        for p in u["participants"]:
            if p in enrollment and not contains(enrollment[p], start, end):
                fail("OUTSIDE_ENROLLMENT", key)
        placed[key] = a
        if not any(
            s["subject"] == u["subject"]
            and s["level"] == u["level"]
            and s["mode"] == a["mode"]
            and s["start"] <= start
            and end <= s["end"]
            for s in t["skills"]
        ):
            fail("UNQUALIFIED_TUTOR", key)
        if a["mode"] == "IN_PERSON" and a["location"] != "ON_SITE":
            fail("LOCATION", key)
        space = resources.get(a["space_id"])
        video = resources.get(a["video_id"])
        needs_space = a["mode"] == "IN_PERSON" or (
            a["location"] == "ON_SITE" and data["online_onsite_requires_space"]
        )
        if needs_space != (a["space_id"] is not None) or (
            a["space_id"] is not None and (not space or space["kind"] != "SPACE")
        ):
            fail("SPACE_REQUIRED", key)
        needs_video = a["mode"] == "ONLINE" and data["video_channels_required"]
        if needs_video != (a["video_id"] is not None) or (
            a["video_id"] is not None
            and (not video or video["kind"] != "VIDEO_CHANNEL")
        ):
            fail("VIDEO_REQUIRED", key)
        if a["mode"] == "IN_PERSON" and (
            len(u["participants"]) > 2
            or (space and len(u["participants"]) > space["student_capacity"])
        ):
            fail("SPACE_CAPACITY", key)
        if (
            a["mode"] == "ONLINE"
            and u["type"] == "GROUP"
            and (
                u["online_capacity"] is None
                or len(u["participants"]) > u["online_capacity"]
            )
        ):
            fail("ONLINE_CAPACITY", key)
        pause_end = end + t["pause_minutes"]
        occupation_end = max(pause_end, end + (space["buffer_minutes"] if space else 0))
        if not contains(
            [
                w
                for w in t["availability"]
                if w["mode"] == a["mode"] and w["location"] == a["location"]
            ],
            start,
            pause_end,
        ):
            fail("TUTOR_AVAILABILITY", key)
        if not contains(
            [
                w
                for w in data["service_windows"]
                if w["mode"] == a["mode"] and w["location"] == a["location"]
            ],
            start,
            occupation_end,
        ):
            fail("SERVICE_CLOSED", key)
        for p in u["participants"]:
            student = students[p]
            if student["availability_state"] in (
                "UNKNOWN",
                "DECLARED_NONE",
            ) or not contains(
                [
                    w
                    for w in student["availability"]
                    if w["mode"] == a["mode"]
                    and (
                        not v05
                        or (
                            w.get("location")
                            or ("ON_SITE" if w["mode"] == "IN_PERSON" else "REMOTE")
                        )
                        == where
                    )
                ],
                start,
                end,
            ):
                fail("STUDENT_AVAILABILITY", key)
            bookings[("STUDENT", p)].append((start, end + student_buffer, key))
        for resource in (space, video, seat):
            if resource:
                resource_end = end + resource["buffer_minutes"]
                if not contains(resource["availability"], start, resource_end):
                    fail("RESOURCE_AVAILABILITY", key)
                bookings[("RESOURCE", resource["id"])].append(
                    (start, resource_end, key)
                )
        for c in data["closures"]:
            occupied_end = (
                occupation_end
                if c["resource_id"] is None
                else end + (resources[c["resource_id"]]["buffer_minutes"])
            )
            relevant = c["resource_id"] is None or c["resource_id"] in (
                a["space_id"],
                a["video_id"],
                a.get("student_space_id"),
            )
            if (
                relevant
                and c["mode"] in ("ALL", a["mode"])
                and start < c["end"]
                and c["start"] < occupied_end
            ):
                fail("CLOSURE", key)
        bookings[("TUTOR", t["id"])].append((start, pause_end, key))
        by_tutor[t["id"]].append(a)
        daily[(t["id"], local.date())] += u["duration_minutes"]
        iso = local.isocalendar()
        weekly[(t["id"], iso.year, iso.week)] += u["duration_minutes"]
        if u["locked_assignment"] and not _same(a, u["locked_assignment"]):
            fail("LOCK_CHANGED", key)
    for spans in bookings.values():
        ordered = sorted(spans)
        for index, (start, end, key) in enumerate(ordered):
            if any(
                other_start < end
                for other_start, other_end, other_key in ordered[index + 1 :]
            ):
                fail("RESOURCE_OVERLAP", key)
    for tutor_id, items in by_tutor.items():
        ordered = sorted(items, key=lambda a: a["start"])
        t = tutors[tutor_id]
        for a, b in zip(ordered, ordered[1:]):
            gap = max(
                t["pause_minutes"],
                t["transition_minutes"][a["location"]][b["location"]],
            )
            if b["start"] < a["end"] + gap:
                fail("TRANSITION_OR_PAUSE", b["demand_key"])
    for (tutor_id, day), minutes in daily.items():
        if minutes > tutors[tutor_id]["daily_limit_minutes"]:
            fail("DAILY_LOAD", tutor_id)
    for (tutor_id, year, week), minutes in weekly.items():
        if minutes > tutors[tutor_id]["weekly_limit_minutes"]:
            fail("WEEKLY_LOAD", tutor_id)
    _relations(data, placed, epoch, zone, fail)
    if require_coverage:
        for u in units.values():
            if u["demand_key"] not in seen and (
                data["mode"] == "STRICT" or u["mandatory"] or u["locked_assignment"]
            ):
                fail("MANDATORY_UNASSIGNED", u["demand_key"])
    return {"status": "FAILED" if violations else "PASSED", "violations": violations}


def _relations(data, placed, epoch, zone, fail):
    def day(a):
        return (epoch + timedelta(minutes=a["start"])).astimezone(zone).date()

    for item in data.get("family_constraints", []):
        keys = item["units"]
        kind = item["kind"]
        present = [k for k in keys if k in placed]
        if kind in ("SAME_START", "SAME_INTERVAL"):
            if present and len(present) != len(keys):
                fail("FAMILY_SYNC_PARTIAL", item["constraint_id"])
            if len({placed[k]["start"] for k in present}) > 1 or (
                kind == "SAME_INTERVAL" and len({placed[k]["end"] for k in present}) > 1
            ):
                fail("FAMILY_SYNC", item["constraint_id"])
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                x, y = placed[a], placed[b]
                if kind == "SAME_DAY" and day(x) != day(y):
                    fail("FAMILY_SAME_DAY", item["constraint_id"])
                if kind == "DIFFERENT_DAYS" and day(x) == day(y):
                    fail("FAMILY_DIFFERENT_DAYS", item["constraint_id"])
                if (
                    kind == "NO_OVERLAP"
                    and x["start"] < y["end"]
                    and y["start"] < x["end"]
                ):
                    fail("FAMILY_OVERLAP", item["constraint_id"])
    for item in data.get("sequences", []):
        keys = item["units"]
        for a, b in zip(keys, keys[1:]):
            if b in placed and a not in placed and item["require_predecessor"]:
                fail("SEQUENCE_PREDECESSOR", item["sequence_id"])
            if a in placed and b in placed:
                gap = placed[b]["start"] - placed[a]["end"]
                if gap < item["min_gap_minutes"] or (
                    item["max_gap_minutes"] is not None
                    and gap > item["max_gap_minutes"]
                ):
                    fail("SEQUENCE_ORDER", item["sequence_id"])
    for series in data.get("series", []):
        if series["stability"] != "REQUIRED":
            continue
        slots = {
            _local_slot(epoch, zone, placed[k]["start"])
            for k in series["units"]
            if k in placed
        }
        wanted = series["preferred_slot"]
        if len(slots) > 1 or (
            wanted
            and slots
            and slots != {(wanted["weekday"], wanted["local_start_minute"])}
        ):
            fail("RECURRING_SLOT_REQUIRED", series["series_key"])
