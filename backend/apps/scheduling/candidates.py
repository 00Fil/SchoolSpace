"""Exhaustive enumeration within explicit, configurable size caps. No top-k pruning.

Every alternative (tutor, mode, tutor location, space, video, student location,
start) admitted by the approved data is enumerated.  Excluded options are
recorded in a reason ledger.  When the physical spaces are provably
interchangeable (same capacity, buffer and opening windows, no space-specific
closures, locks or previous assignments) they are represented as a pool and a
concrete space is assigned after the search by interval colouring, which is
exact for identical exclusive resources; the independent validator then checks
the concrete spaces again.
"""

from .contracts import InputError, effective_limits
from .timeline import day_key, week_key, slot, crosses_local_midnight

MAX_CANDIDATES = 3000  # historical v0.4 cap; v0.5 uses DTO/default limits
POOL = "__SPACE_POOL__"

__all__ = [
    "compile_candidates",
    "subtract",
    "starts",
    "day_key",
    "week_key",
    "spaces_interchangeable",
    "POOL",
]


def subtract(windows, exclusions):
    spans = sorted((w["start"], w["end"]) for w in windows)
    for start, end in exclusions:
        result = []
        for a, b in spans:
            if end <= a or start >= b:
                result.append((a, b))
            else:
                if a < start:
                    result.append((a, start))
                if end < b:
                    result.append((end, b))
        spans = result
    return spans


def starts(windows, duration, grid, exclusions=()):
    # Union first, so adjacent declared windows can contain a full lesson.
    merged = []
    for a, b in sorted((w["start"], w["end"]) for w in windows):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    spans = subtract([{"start": a, "end": b} for a, b in merged], exclusions)
    result = set()
    for a, b in spans:
        result.update(range(((a + grid - 1) // grid) * grid, b - duration + 1, grid))
    return result


def _norm(windows):
    return sorted((w["start"], w["end"]) for w in windows)


def spaces_interchangeable(data):
    spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    if data["schema_version"] == "0.4" or len(spaces) < 2:
        return False
    first = spaces[0]
    if any(
        r["student_capacity"] != first["student_capacity"]
        or r["buffer_minutes"] != first["buffer_minutes"]
        or _norm(r["availability"]) != _norm(first["availability"])
        for r in spaces
    ):
        return False
    ids = {r["id"] for r in spaces}
    if any(c["resource_id"] in ids for c in data["closures"]):
        return False
    for unit in data["units"]:
        for field in ("locked_assignment", "previous_assignment"):
            a = unit.get(field)
            if a and (a.get("space_id") or a.get("student_space_id")):
                return False
    return True


def student_location(window):
    return window.get("location") or (
        "ON_SITE" if window["mode"] == "IN_PERSON" else "REMOTE"
    )


def public_fields(candidate, data):
    """Assignment fields of a candidate, in the contract shape of the DTO version."""
    a = {
        k: candidate[k]
        for k in (
            "demand_key",
            "tutor_id",
            "mode",
            "location",
            "space_id",
            "video_id",
            "start",
            "end",
        )
    }
    if candidate.get("student_location") == "ON_SITE" and candidate["mode"] == "ONLINE":
        a["student_location"] = "ON_SITE"
        a["student_space_id"] = candidate["student_space_id"]
    return a


def same_assignment(candidate, assignment, data):
    """Locks compare the full public shape; 8 and 10 field forms are equivalent
    when the 10-field form only states the default student location."""
    a = dict(assignment)
    if a.get("student_location") and not (
        a["student_location"] == "ON_SITE" and a["mode"] == "ONLINE"
    ):
        if a.get("student_space_id") is None:
            a.pop("student_location")
            a.pop("student_space_id")
    return public_fields(candidate, data) == a


def compile_candidates(data):
    students = {s["id"]: s for s in data["students"]}
    tutors = {t["id"]: t for t in data["tutors"]}
    v05 = data["schema_version"] == "0.5"
    referenced_students = {p for u in data["units"] for p in u["participants"]}
    referenced_tutors = {t for u in data["units"] for t in u["allowed_tutors"]}
    if any(
        students[s]["availability_state"] == "UNKNOWN" for s in referenced_students
    ) or any(tutors[t]["availability_state"] == "UNKNOWN" for t in referenced_tutors):
        raise InputError(
            "MISSING_AVAILABILITY",
            "Disponibilità UNKNOWN: nessuna simulazione finché il dato non è approvato",
        )
    if data["unsupported_constraints"]:
        raise InputError(
            "UNSUPPORTED_CONSTRAINT",
            "Sono stati dichiarati vincoli non supportati: simulazione bloccata, nessun rilassamento",
        )
    limit = MAX_CANDIDATES if not v05 else effective_limits(data)["max_candidates"]
    pooled = spaces_interchangeable(data)
    all_spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    space_options = (
        [{**all_spaces[0], "id": POOL}] if pooled and all_spaces else all_spaces
    )
    video_options = [r for r in data["resources"] if r["kind"] == "VIDEO_CHANNEL"]
    enrollment = {e["student_id"]: e["periods"] for e in data.get("enrollments", [])}
    required_slot = {}
    for series in data.get("series", []):
        if series["stability"] == "REQUIRED" and series["preferred_slot"]:
            wanted = (
                series["preferred_slot"]["weekday"],
                series["preferred_slot"]["local_start_minute"],
            )
            for key in series["units"]:
                required_slot[key] = wanted
    allow_midnight = data["allow_cross_local_midnight"]
    grid = data["grid_minutes"]
    compiled = {}
    ledger = {}
    illegal = []
    total = 0
    for unit in data["units"]:
        result = []
        reasons = set()
        duration = unit["duration_minutes"]
        key = unit["demand_key"]
        unit_window = starts(
            [{"start": unit["earliest_start"], "end": unit["latest_end"]}],
            duration,
            grid,
        )
        for student_id in unit["participants"]:
            if student_id in enrollment:
                inside = starts(enrollment[student_id], duration, grid)
                if not unit_window & inside:
                    reasons.add("OUTSIDE_ENROLLMENT")
                unit_window &= inside
        for tutor_id in unit["allowed_tutors"]:
            tutor = tutors[tutor_id]
            if tutor["availability_state"] == "DECLARED_NONE":
                reasons.add("TUTOR_DECLARED_NONE")
                continue
            for mode in unit["allowed_modes"]:
                skills = [
                    s
                    for s in tutor["skills"]
                    if s["subject"] == unit["subject"]
                    and s["level"] == unit["level"]
                    and s["mode"] == mode
                ]
                if not skills:
                    reasons.add("NO_ELIGIBLE_TUTOR")
                    continue
                if mode == "IN_PERSON" and len(unit["participants"]) > 2:
                    reasons.add("SPACE_CAPACITY")
                    continue
                if (
                    mode == "ONLINE"
                    and unit["type"] == "GROUP"
                    and (
                        unit["online_capacity"] is None
                        or len(unit["participants"]) > unit["online_capacity"]
                    )
                ):
                    reasons.add("ONLINE_CAPACITY")
                    continue
                student_locations = (
                    ["ON_SITE"]
                    if mode == "IN_PERSON"
                    else (["REMOTE", "ON_SITE"] if v05 else ["REMOTE"])
                )
                for location in (
                    ["ON_SITE"] if mode == "IN_PERSON" else ["ON_SITE", "REMOTE"]
                ):
                    needs_space = mode == "IN_PERSON" or (
                        location == "ON_SITE" and data["online_onsite_requires_space"]
                    )
                    spaces = space_options if needs_space else [None]
                    videos = (
                        video_options
                        if mode == "ONLINE" and data["video_channels_required"]
                        else [None]
                    )
                    if not spaces:
                        reasons.add("NO_SPACE")
                        continue
                    if not videos:
                        reasons.add("NO_VIDEO_CHANNEL")
                        continue
                    removals = [
                        (c["start"], c["end"])
                        for c in data["closures"]
                        if c["resource_id"] is None and c["mode"] in ("ALL", mode)
                    ]
                    tw = [
                        w
                        for w in tutor["availability"]
                        if w["mode"] == mode and w["location"] == location
                    ]
                    service = [
                        w
                        for w in data["service_windows"]
                        if w["mode"] == mode and w["location"] == location
                    ]
                    base = starts(tw, duration + tutor["pause_minutes"], grid)
                    base &= starts(skills, duration, grid)
                    base &= unit_window
                    for where in student_locations:
                        if mode == "ONLINE" and where == "ON_SITE":
                            if location == "ON_SITE":
                                reasons.add("ONLINE_BOTH_ON_SITE")
                                continue
                            if len(unit["participants"]) > 2:
                                reasons.add("SPACE_CAPACITY")
                                continue
                            if not space_options:
                                reasons.add("NO_SPACE")
                                continue
                        student_spaces = (
                            space_options
                            if mode == "ONLINE" and where == "ON_SITE"
                            else [None]
                        )
                        choices_students = set(base)
                        for student_id in unit["participants"]:
                            student = students[student_id]
                            sw = (
                                []
                                if student["availability_state"] == "DECLARED_NONE"
                                else [
                                    w
                                    for w in student["availability"]
                                    if w["mode"] == mode
                                    and (not v05 or student_location(w) == where)
                                ]
                            )
                            choices_students &= starts(sw, duration, grid)
                        if where == "ON_SITE" and mode == "ONLINE":
                            # The student's seat needs the centre to be open on site.
                            site_service = [
                                w
                                for w in data["service_windows"]
                                if w["location"] == "ON_SITE"
                            ]
                            site_removals = [
                                (c["start"], c["end"])
                                for c in data["closures"]
                                if c["resource_id"] is None
                                and c["mode"] in ("ALL", mode)
                            ]
                            choices_students &= starts(
                                site_service,
                                duration + space_options[0]["buffer_minutes"],
                                grid,
                                site_removals,
                            )
                        for space in spaces:
                            for video in videos:
                                for seat in student_spaces:
                                    buffer = space["buffer_minutes"] if space else 0
                                    occupation = duration + max(
                                        tutor["pause_minutes"], buffer
                                    )
                                    choices = choices_students & starts(
                                        service, occupation, grid, removals
                                    )
                                    for resource in (space, video, seat):
                                        if resource:
                                            excluded = [
                                                (c["start"], c["end"])
                                                for c in data["closures"]
                                                if c["resource_id"] == resource["id"]
                                                and c["mode"] in ("ALL", mode)
                                            ]
                                            choices &= starts(
                                                resource["availability"],
                                                duration + resource["buffer_minutes"],
                                                grid,
                                                excluded,
                                            )
                                    if (
                                        seat
                                        and space
                                        and seat["id"] == space["id"] != POOL
                                    ):
                                        continue
                                    for start in sorted(choices):
                                        end = start + duration
                                        if (
                                            not allow_midnight
                                            and crosses_local_midnight(data, start, end)
                                        ):
                                            reasons.add("CROSS_LOCAL_MIDNIGHT")
                                            continue
                                        if (
                                            key in required_slot
                                            and slot(data, start) != required_slot[key]
                                        ):
                                            reasons.add("RECURRING_SLOT_REQUIRED")
                                            continue
                                        candidate = {
                                            "demand_key": key,
                                            "tutor_id": tutor_id,
                                            "mode": mode,
                                            "location": location,
                                            "space_id": space["id"] if space else None,
                                            "video_id": video["id"] if video else None,
                                            "start": start,
                                            "end": end,
                                            "student_location": where,
                                            "student_space_id": seat["id"]
                                            if seat
                                            else None,
                                        }
                                        result.append(candidate)
                                        total += 1
                                        if total > limit:
                                            raise InputError(
                                                "CANDIDATE_LIMIT",
                                                "DTO oltre la dimensione configurata: nessun taglio euristico, nessuna prova di impossibilità",
                                            )
        # Multiple touching skill windows must not be combined to qualify a single lesson.
        result = [
            a
            for a in result
            if any(
                s["subject"] == unit["subject"]
                and s["level"] == unit["level"]
                and s["mode"] == a["mode"]
                and s["start"] <= a["start"]
                and a["end"] <= s["end"]
                for s in tutors[a["tutor_id"]]["skills"]
            )
        ]
        if not result and not reasons:
            reasons.add("NO_COMMON_AVAILABILITY")
        compiled[key] = result
        ledger[key] = sorted(reasons)
        fixed = unit["locked_assignment"]
        if fixed and not any(same_assignment(c, fixed, data) for c in result):
            illegal.append(key)
    if illegal:
        raise InputError(
            "LOCKED_ILLEGAL",
            "Una lezione bloccata viola i dati approvati della simulazione",
            illegal,
        )
    return compiled, ledger
