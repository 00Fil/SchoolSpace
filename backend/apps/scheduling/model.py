"""CP-SAT model construction shared by the search and the diagnostic submodels.

Hard constraints H01-H12 are posted here; objectives are linear expressions
returned per lexicographic term.  ``assumptions=True`` puts coverage
requirements and every H11/H12/series constraint behind assumption literals so
that CP-SAT can return a sufficient (not necessarily minimal) conflict set.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from ortools.sat.python import cp_model
from .candidates import POOL
from .timeline import day_key, week_key, slot
from .objectives import slot_cost, preference_cost


@dataclass
class Bundle:
    model: cp_model.CpModel
    presence: dict
    choices: list  # (candidate, literal)
    by_unit: dict
    terms: dict
    assumptions: dict = field(default_factory=dict)  # literal index -> label
    starts: dict = field(default_factory=dict)


def _required(data, unit):
    return data["mode"] == "STRICT" or unit["mandatory"] or unit["locked_assignment"]


def build(data, candidates, *, assumptions=False, only=None):
    from .candidates import same_assignment

    model = cp_model.CpModel()
    units = [u for u in data["units"] if only is None or u["demand_key"] in only]
    unit_map = {u["demand_key"]: u for u in units}
    tutors = {t["id"]: t for t in data["tutors"]}
    resources = {r["id"]: r for r in data["resources"]}
    spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    student_buffer = data["student_buffer_minutes"]
    presence, by_unit, choices = {}, {}, []
    resource_intervals = defaultdict(list)
    pool_intervals, pool_demands = [], []
    daily, weekly = defaultdict(list), defaultdict(list)
    tutor_options = defaultdict(list)
    bundle = Bundle(model, presence, choices, by_unit, {})

    def guard(label):
        literal = model.new_bool_var("assume:" + label)
        bundle.assumptions[literal.index] = label
        return literal

    for unit in units:
        key = unit["demand_key"]
        z = model.new_bool_var("assigned:" + key)
        presence[key] = z
        options = []
        for index, candidate in enumerate(candidates[key]):
            x = model.new_bool_var(f"{key}:{index}")
            options.append((candidate, x))
            choices.append((candidate, x))
            t = tutors[candidate["tutor_id"]]
            start, end = candidate["start"], candidate["end"]
            duration = end - start
            pool_sizes = []
            occupations = [(("TUTOR", t["id"]), duration + t["pause_minutes"])]
            occupations += [
                (("STUDENT", p), duration + student_buffer)
                for p in unit["participants"]
            ]
            for rid in (
                candidate["space_id"],
                candidate["video_id"],
                candidate.get("student_space_id"),
            ):
                if rid is None:
                    continue
                if rid == POOL:
                    pool_sizes.append(duration + spaces[0]["buffer_minutes"])
                else:
                    occupations.append(
                        (("RESOURCE", rid), duration + resources[rid]["buffer_minutes"])
                    )
            shared = {}
            for size in pool_sizes:
                if size not in shared:
                    shared[size] = model.new_optional_fixed_size_interval_var(
                        start, size, x, f"{key}:{index}:{size}"
                    )
                pool_intervals.append(shared[size])
                pool_demands.append(1)
            for resource, size in occupations:
                if size not in shared:
                    shared[size] = model.new_optional_fixed_size_interval_var(
                        start, size, x, f"{key}:{index}:{size}"
                    )
                resource_intervals[resource].append(shared[size])
            daily[(t["id"], day_key(data, start))].append(duration * x)
            weekly[(t["id"], week_key(data, start))].append(duration * x)
            tutor_options[t["id"]].append((candidate, x))
            if unit["locked_assignment"] and same_assignment(
                candidate, unit["locked_assignment"], data
            ):
                model.add(x == 1)
        by_unit[key] = options
        model.add(sum(x for _, x in options) == z)
        if _required(data, unit):
            if assumptions and not unit["locked_assignment"]:
                model.add(z == 1).only_enforce_if(guard("UNIT:" + key))
            else:
                model.add(z == 1)
        bundle.starts[key] = sum(c["start"] * x for c, x in options)
    for intervals in resource_intervals.values():
        model.add_no_overlap(intervals)
    if pool_intervals:
        model.add_cumulative(pool_intervals, pool_demands, len(spaces))
    for (tutor_id, _), terms in daily.items():
        model.add(sum(terms) <= tutors[tutor_id]["daily_limit_minutes"])
    for (tutor_id, _), terms in weekly.items():
        model.add(sum(terms) <= tutors[tutor_id]["weekly_limit_minutes"])
    for tutor_id, options in tutor_options.items():
        _transitions(model, tutors[tutor_id], options)
    _hard_relations(data, bundle, unit_map, assumptions, guard)
    _symmetry(data, bundle, unit_map)
    _objectives(data, bundle, unit_map)
    return bundle


def _transitions(model, t, options):
    """Location transitions longer than the pause (H11).

    Only pairs not already excluded by NoOverlap on the tutor interval
    (duration + pause) matter: a lesson at location B starting in
    [a.end + pause, a.end + gap) after a lesson ``a`` at location A.  When the
    window ``gap - pause`` is not longer than the shortest lesson, all lessons
    ending in it pairwise overlap, hence are mutually exclusive: one clique
    constraint per (direction, start time) is then exact and much smaller than
    the pairwise form, which is kept as fallback.
    """
    import bisect

    pause = t["pause_minutes"]
    matrix = t["transition_minutes"]
    if max(matrix["ON_SITE"]["REMOTE"], matrix["REMOTE"]["ON_SITE"]) <= pause:
        return
    shortest = min((c["end"] - c["start"] for c, _ in options), default=0)
    for origin in ("ON_SITE", "REMOTE"):
        target = _other(origin)
        gap = matrix[origin][target]
        if gap <= pause:
            continue
        before = sorted(
            ((c["end"], x, c) for c, x in options if c["location"] == origin),
            key=lambda item: item[0],
        )
        after = defaultdict(list)
        for c, x in options:
            if c["location"] == target:
                after[c["start"]].append((c, x))
        ends = [e for e, _, _ in before]
        for begin, starting in after.items():
            lo = bisect.bisect_right(ends, begin - gap)
            hi = bisect.bisect_right(ends, begin - pause)
            ended = before[lo:hi]
            if not ended:
                continue
            if gap - pause <= shortest:
                model.add(
                    sum(x for _, x, _ in ended) + sum(y for _, y in starting) <= 1
                )
            else:
                for _, x, a in ended:
                    for b, y in starting:
                        if a["demand_key"] != b["demand_key"]:
                            model.add_bool_or([x.Not(), y.Not()])


def _other(location):
    return "REMOTE" if location == "ON_SITE" else "ON_SITE"


def _hard_relations(data, bundle, unit_map, assumptions, guard):
    model, z, s = bundle.model, bundle.presence, bundle.starts

    def lits(label):
        return [guard(label)] if assumptions else []

    def day_index(key):
        return sum(
            int(day_key(data, c["start"]).replace("-", "")) * x
            for c, x in bundle.by_unit[key]
        )

    for item in data.get("family_constraints", []):
        keys = [k for k in item["units"] if k in unit_map]
        if len(keys) < 2:
            continue
        enforce = lits("FAMILY:" + item["constraint_id"])
        kind = item["kind"]
        for a, b in zip(keys, keys[1:]):
            if kind in ("SAME_START", "SAME_INTERVAL"):
                model.add(z[a] == z[b]).only_enforce_if(enforce)
                model.add(s[a] == s[b]).only_enforce_if(enforce)
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                both = [z[a], z[b], *enforce]
                if kind == "SAME_DAY":
                    model.add(day_index(a) == day_index(b)).only_enforce_if(both)
                elif kind == "DIFFERENT_DAYS":
                    model.add(day_index(a) != day_index(b)).only_enforce_if(both)
                elif kind == "NO_OVERLAP":
                    da = unit_map[a]["duration_minutes"]
                    db = unit_map[b]["duration_minutes"]
                    order = model.new_bool_var(f"order:{a}:{b}")
                    model.add(s[a] + da <= s[b]).only_enforce_if([*both, order])
                    model.add(s[b] + db <= s[a]).only_enforce_if([*both, order.Not()])
    for item in data.get("sequences", []):
        keys = [k for k in item["units"] if k in unit_map]
        enforce = lits("SEQUENCE:" + item["sequence_id"])
        for a, b in zip(keys, keys[1:]):
            da = unit_map[a]["duration_minutes"]
            both = [z[a], z[b], *enforce]
            model.add(s[b] >= s[a] + da + item["min_gap_minutes"]).only_enforce_if(both)
            if item["max_gap_minutes"] is not None:
                model.add(s[b] <= s[a] + da + item["max_gap_minutes"]).only_enforce_if(
                    both
                )
            if item["require_predecessor"]:
                model.add_implication(z[b], z[a]).only_enforce_if(enforce)
    bundle.series_slots = {}
    for series in data.get("series", []):
        keys = [k for k in series["units"] if k in unit_map]
        if series["preferred_slot"] or not keys:
            continue
        values = sorted(
            {slot(data, c["start"]) for k in keys for c, _ in bundle.by_unit[k]}
        )
        if not values:
            continue
        y = {v: model.new_bool_var(f"slot:{series['series_key']}:{v}") for v in values}
        model.add_exactly_one(y.values())
        matches = []
        for k in keys:
            for v in values:
                options = [
                    x for c, x in bundle.by_unit[k] if slot(data, c["start"]) == v
                ]
                if not options:
                    continue
                m = model.new_bool_var(f"on:{k}:{v}")
                model.add_implication(m, y[v])
                model.add(m <= sum(options))
                matches.append(m)
        placed = sum(z[k] for k in keys)
        bundle.series_slots[series["series_key"]] = (placed, sum(matches))
        if series["stability"] == "REQUIRED":
            model.add(sum(matches) == placed).only_enforce_if(
                lits("SERIES:" + series["series_key"])
            )


def _symmetry(data, bundle, unit_map):
    """Identical, unreferenced units (same request, serials) are ordered by start."""
    referenced = set()
    for name in ("series", "family_constraints", "sequences"):
        for item in data.get(name, []):
            referenced |= set(item["units"])
    for item in (data.get("replanning") or {}).get("unlocked", []):
        referenced.add(item["demand_key"])
    groups = defaultdict(list)
    for key, unit in unit_map.items():
        if (
            key in referenced
            or unit["locked_assignment"]
            or unit.get("previous_assignment")
        ):
            continue
        signature = tuple(
            sorted(
                (k, repr(v))
                for k, v in unit.items()
                if k not in ("demand_key", "locked_assignment", "previous_assignment")
            )
        )
        groups[signature].append(key)
    model, z, s = bundle.model, bundle.presence, bundle.starts
    for keys in groups.values():
        keys.sort()
        if len(keys) < 2 or any(
            len(bundle.by_unit[k]) != len(bundle.by_unit[keys[0]]) for k in keys
        ):
            continue
        for a, b in zip(keys, keys[1:]):
            model.add_implication(z[b], z[a])
            model.add(s[a] + 1 <= s[b]).only_enforce_if(z[b])


def _objectives(data, bundle, unit_map):
    model, z = bundle.model, bundle.presence
    terms = bundle.terms
    order = data["objective_order"]
    for p in ("P0", "P1", "P2"):
        terms[p] = sum(
            u["duration_minutes"] * len(u["participants"]) * (1 - z[u["demand_key"]])
            for u in unit_map.values()
            if u["priority"] == p
        )
    if "F" in order:
        scale = data["fairness_policy"]["scale"]
        demanded, missing = defaultdict(int), defaultdict(list)
        for u in unit_map.values():
            for student in u["participants"]:
                demanded[student] += u["duration_minutes"]
                missing[student].append(
                    u["duration_minutes"] * (1 - z[u["demand_key"]])
                )
        f = model.new_int_var(0, scale, "fairness_max")
        for student, total in demanded.items():
            q = model.new_int_var(0, scale, f"fairness:{student}")
            model.add(q * total >= scale * sum(missing[student]))
            model.add(f >= q)
        terms["F"] = f
    if "C" in order:
        expr = 0
        for key, u in unit_map.items():
            previous = u.get("previous_assignment")
            if not previous:
                continue
            from .candidates import same_assignment

            same = [
                x for c, x in bundle.by_unit[key] if same_assignment(c, previous, data)
            ]
            expr += 1 - sum(same)
        terms["C"] = expr
    if "R" in order:
        expr = 0
        for series in data.get("series", []):
            keys = [k for k in series["units"] if k in unit_map]
            if series["preferred_slot"]:
                for k in keys:
                    expr += sum(
                        slot_cost(data, series["preferred_slot"], c["start"]) * x
                        for c, x in bundle.by_unit[k]
                    )
            elif series["series_key"] in bundle.series_slots:
                placed, on_slot = bundle.series_slots[series["series_key"]]
                expr += 100 * (placed - on_slot)
        terms["R"] = expr
    if "P" in order:
        terms["P"] = sum(
            preference_cost(
                data,
                c,
                set(unit_map[c["demand_key"]]["participants"]),
                unit_map[c["demand_key"]],
            )
            * x
            for c, x in bundle.choices
        )
    if "G" in order:
        days = defaultdict(list)
        units_on = defaultdict(set)
        for c, x in bundle.choices:
            day = day_key(data, c["start"])
            names = [("T", c["tutor_id"], day)] + [
                ("S", student, day)
                for student in unit_map[c["demand_key"]]["participants"]
            ]
            for name in names:
                days[name].append(x)
                units_on[name].add(c["demand_key"])
        expr = 0
        for name, literals in days.items():
            w = model.new_bool_var(f"active:{name}")
            # At most one alternative per unit: the distinct units bound the sum.
            model.add(sum(literals) <= len(units_on[name]) * w)
            expr += w
        terms["G"] = expr
