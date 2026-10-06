"""Greedy constructive incumbent used only as a CP-SAT solution hint.

The hint never becomes a result by itself: CP-SAT must accept it (or repair
it) and the final assignments still go through the independent validator.
Units in synchronisations/sequences are left to the solver.
"""

from collections import defaultdict
from .candidates import POOL
from .timeline import day_key, week_key


def greedy(data, candidates):
    units = {u["demand_key"]: u for u in data["units"]}
    tutors = {t["id"]: t for t in data["tutors"]}
    resources = {r["id"]: r for r in data["resources"]}
    spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    skip = set()
    for item in data.get("family_constraints", []):
        if item["kind"] in ("SAME_START", "SAME_INTERVAL"):
            skip |= set(item["units"])
    for item in data.get("sequences", []):
        skip |= set(item["units"])
    for series in data.get("series", []):
        if series["stability"] == "REQUIRED" and not series["preferred_slot"]:
            skip |= set(series["units"])
    family_rules = defaultdict(list)
    for item in data.get("family_constraints", []):
        for key in item["units"]:
            family_rules[key].append(item)
    busy = defaultdict(list)
    tutor_lessons = defaultdict(list)
    pool = []
    daily, weekly = defaultdict(int), defaultdict(int)
    chosen = {}
    rank = {"P0": 0, "P1": 1, "P2": 2}

    def required(u):
        return data["mode"] == "STRICT" or u["mandatory"] or u["locked_assignment"]

    order = sorted(
        units.values(),
        key=lambda u: (
            not u["locked_assignment"],
            not required(u),
            rank[u["priority"]],
            len(candidates[u["demand_key"]]),
            u["demand_key"],
        ),
    )

    def free(resource, start, end):
        return all(end <= s or e <= start for s, e in busy[resource])

    def fits(c, u):
        t = tutors[c["tutor_id"]]
        d = c["end"] - c["start"]
        if not free(("T", t["id"]), c["start"], c["end"] + t["pause_minutes"]):
            return False
        for other in tutor_lessons[t["id"]]:
            first, second = (other, c) if other["start"] <= c["start"] else (c, other)
            gap = max(
                t["pause_minutes"],
                t["transition_minutes"][first["location"]][second["location"]],
            )
            if second["start"] < first["end"] + gap:
                return False
        sb = data["student_buffer_minutes"]
        if any(
            not free(("S", p), c["start"], c["end"] + sb) for p in u["participants"]
        ):
            return False
        need_pool = [c.get("space_id"), c.get("student_space_id")].count(POOL)
        for rid in (c["space_id"], c["video_id"], c.get("student_space_id")):
            if rid and rid != POOL:
                if not free(
                    ("R", rid), c["start"], c["end"] + resources[rid]["buffer_minutes"]
                ):
                    return False
        if need_pool:
            end = c["end"] + spaces[0]["buffer_minutes"]
            points = [c["start"]] + [s for s, e in pool if c["start"] < s < end]
            for p in points:
                if sum(1 for s, e in pool if s <= p < e) + need_pool > len(spaces):
                    return False
        if daily[(t["id"], day_key(data, c["start"]))] + d > t["daily_limit_minutes"]:
            return False
        if (
            weekly[(t["id"], week_key(data, c["start"]))] + d
            > t["weekly_limit_minutes"]
        ):
            return False
        for item in family_rules[c["demand_key"]]:
            for key in item["units"]:
                if key == c["demand_key"] or key not in chosen:
                    continue
                o = chosen[key]
                same_day = day_key(data, o["start"]) == day_key(data, c["start"])
                if item["kind"] == "SAME_DAY" and not same_day:
                    return False
                if item["kind"] == "DIFFERENT_DAYS" and same_day:
                    return False
                if (
                    item["kind"] == "NO_OVERLAP"
                    and o["start"] < c["end"]
                    and c["start"] < o["end"]
                ):
                    return False
        return True

    for u in order:
        key = u["demand_key"]
        if key in skip:
            continue
        for c in candidates[key]:
            if fits(c, u):
                t = tutors[c["tutor_id"]]
                chosen[key] = c
                busy[("T", t["id"])].append((c["start"], c["end"] + t["pause_minutes"]))
                tutor_lessons[t["id"]].append(c)
                for p in u["participants"]:
                    busy[("S", p)].append(
                        (c["start"], c["end"] + data["student_buffer_minutes"])
                    )
                for rid in (c["space_id"], c["video_id"], c.get("student_space_id")):
                    if rid == POOL:
                        pool.append(
                            (c["start"], c["end"] + spaces[0]["buffer_minutes"])
                        )
                    elif rid:
                        busy[("R", rid)].append(
                            (c["start"], c["end"] + resources[rid]["buffer_minutes"])
                        )
                daily[(t["id"], day_key(data, c["start"]))] += c["end"] - c["start"]
                weekly[(t["id"], week_key(data, c["start"]))] += c["end"] - c["start"]
                break
    return chosen
