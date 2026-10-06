"""Independent evaluation of the lexicographic vector (U_P0,U_P1,U_P2,F,C,R,P,G).

This module reads only the raw DTO and a list of public assignments.  It does
not use the candidate compiler or CP-SAT: the solver compares the values it
optimised with these, and a mismatch is reported as VALIDATION_FAILED.

Definitions (paper §6.4, encodings to be approved with D03):
- U_p: teaching minutes per beneficiary not assigned, priority p.
- F:   max over students of ceil(scale * unassigned / demanded) minutes.
- C:   unlocked appointments not kept identical (unassigned counts as change).
- R:   recurring-slot variations.  With a preferred slot each deviating date
       costs 100 + min(99, distance in grid steps on the weekly circle); without
       a preferred slot each date outside the series' modal slot costs 100.
- P:   sum of weights of declared preferences not respected by a lesson,
       plus PREFERRED_TUTOR_WEIGHT per lesson not given to a preferred tutor.
- G:   fragmentation proxy: active (tutor, local day) + (student, local day).
"""

from collections import Counter, defaultdict
from .timeline import slot, day_key

TERMS = ("P0", "P1", "P2", "F", "C", "R", "P", "G")
WEEK_MINUTES = 7 * 1440


def contained(windows, start, end):
    cursor = start
    for a, b in sorted((w["start"], w["end"]) for w in windows):
        if b <= cursor:
            continue
        if a > cursor:
            return False
        cursor = max(cursor, b)
        if cursor >= end:
            return True
    return cursor >= end


def normalized(assignment):
    a = dict(assignment)
    if a.get("student_location") and not (
        a["student_location"] == "ON_SITE" and a["mode"] == "ONLINE"
    ):
        if a.get("student_space_id") is None:
            a.pop("student_location", None)
            a.pop("student_space_id", None)
    return a


def slot_cost(data, preferred, start):
    weekday, minute = slot(data, start)
    if (weekday, minute) == (preferred["weekday"], preferred["local_start_minute"]):
        return 0
    delta = abs(
        weekday * 1440
        + minute
        - preferred["weekday"] * 1440
        - preferred["local_start_minute"]
    )
    delta = min(delta, WEEK_MINUTES - delta)
    return 100 + min(99, delta // data["grid_minutes"])


# Peso di una lezione assegnata a un tutor diverso da quello preferito dalla
# famiglia (v0.9.4). Pari al peso massimo di una preferenza oraria dichiarata.
PREFERRED_TUTOR_WEIGHT = 100


def preference_cost(data, assignment, participants, unit=None):
    cost = 0
    preferred = (unit or {}).get("preferred_tutors")
    if preferred and assignment["tutor_id"] not in preferred:
        cost += PREFERRED_TUTOR_WEIGHT
    for item in data.get("preferences", []):
        involved = (
            item["subject_id"] in participants
            if item["subject_kind"] == "STUDENT"
            else item["subject_id"] == assignment["tutor_id"]
        )
        if involved and not contained(
            item["windows"], assignment["start"], assignment["end"]
        ):
            cost += item["weight"]
    return cost


def evaluate(data, assignments):
    units = {u["demand_key"]: u for u in data["units"]}
    chosen = {a["demand_key"]: a for a in assignments}
    values = {}
    for p in ("P0", "P1", "P2"):
        values[p] = sum(
            u["duration_minutes"] * len(u["participants"])
            for u in units.values()
            if u["priority"] == p and u["demand_key"] not in chosen
        )
    demanded = defaultdict(int)
    missing = defaultdict(int)
    for u in units.values():
        for student in u["participants"]:
            demanded[student] += u["duration_minutes"]
            if u["demand_key"] not in chosen:
                missing[student] += u["duration_minutes"]
    scale = (data.get("fairness_policy") or {}).get("scale", 1000)
    values["F"] = max(
        [-(-scale * missing[s] // demanded[s]) for s in demanded if demanded[s]] or [0]
    )
    values["C"] = sum(
        1
        for key, u in units.items()
        if u.get("previous_assignment")
        and (
            key not in chosen
            or normalized(chosen[key]) != normalized(u["previous_assignment"])
        )
    )
    r = 0
    for series in data.get("series", []):
        placed = [chosen[k] for k in series["units"] if k in chosen]
        if series["preferred_slot"]:
            r += sum(
                slot_cost(data, series["preferred_slot"], a["start"]) for a in placed
            )
        elif placed:
            modal = Counter(slot(data, a["start"]) for a in placed).most_common(1)[0][1]
            r += 100 * (len(placed) - modal)
    values["R"] = r
    values["P"] = sum(
        preference_cost(
            data,
            a,
            set(units[a["demand_key"]]["participants"]),
            units[a["demand_key"]],
        )
        for a in assignments
        if a["demand_key"] in units
    )
    days = set()
    for a in assignments:
        if a["demand_key"] not in units:
            continue
        day = day_key(data, a["start"])
        days.add(("T", a["tutor_id"], day))
        for student in units[a["demand_key"]]["participants"]:
            days.add(("S", student, day))
    values["G"] = len(days)
    return values
