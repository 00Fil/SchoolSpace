"""Diagnostics that never book anything and never relax the published model.

- ``hypotheses``: suggested alternatives for unassigned/required units, split
  into MOVE_WITHIN_DECLARED (start already inside declared availability; it may
  require moving other lessons) and REQUEST_NEW_AVAILABILITY (the start needs a
  new declaration; ``booking_allowed`` is always false until it is approved).
- ``conflict_analysis``: diagnostic submodels.  Each required unit is solved
  in isolation (with locks) to separate individual impossibility from global
  conflict; an assumption model returns a *sufficient, not necessarily
  minimal* set of conflicting requirements/constraints.
- ``scope_expansion``: in local replanning, a relaxed run over the declared
  expansion candidates proposes which extra appointments to unlock.  It is a
  proposal requiring approval before a new run, never applied automatically.
"""

from copy import deepcopy
from time import monotonic
from ortools.sat.python import cp_model
from .candidates import compile_candidates
from .contracts import InputError
from .model import build
from .objectives import contained
from .validator import _same

MAX_UNITS = 20
PER_KIND = 3
MAX_ISOLATED = 60


def _occupations(data, a, units, tutors, resources):
    pause = tutors[a["tutor_id"]]["pause_minutes"]
    yield ("TUTOR", a["tutor_id"]), a["start"], a["end"] + pause
    for p in units[a["demand_key"]]["participants"]:
        yield ("STUDENT", p), a["start"], a["end"] + data["student_buffer_minutes"]
    for field in ("space_id", "video_id", "student_space_id"):
        rid = a.get(field)
        if rid and rid in resources:
            yield (
                ("RESOURCE", rid),
                a["start"],
                a["end"] + resources[rid]["buffer_minutes"],
            )


def _conflicts(data, candidate, assignments, units, tutors, resources):
    spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    mine = list(_occupations(data, candidate, units, tutors, resources))
    hits = set()
    for other in assignments:
        if other["demand_key"] == candidate["demand_key"]:
            continue
        for res, s, e in _occupations(data, other, units, tutors, resources):
            for res2, s2, e2 in mine:
                if res == res2 and s < e2 and s2 < e:
                    hits.add(other["demand_key"])
    pooled = [candidate.get(f) for f in ("space_id", "student_space_id")].count(
        "__SPACE_POOL__"
    )
    if pooled:
        busy = [
            o["demand_key"]
            for o in assignments
            for f in ("space_id", "student_space_id")
            if o.get(f)
            and resources.get(o[f], {}).get("kind") == "SPACE"
            and o["start"] < candidate["end"]
            and candidate["start"] < o["end"]
        ]
        if len(busy) + pooled > len(spaces):
            hits |= set(busy)
    return sorted(hits)


def _relaxed(data, unit):
    """Copy of the DTO where the unit's people are available whenever the
    service is open: used only to find starts needing new declarations."""
    copy = deepcopy(data)
    copy["units"] = [deepcopy(unit)]
    copy["units"][0]["locked_assignment"] = None
    copy["units"][0].pop("previous_assignment", None)
    copy.pop("replanning", None)
    for key in ("series", "family_constraints", "sequences"):
        copy.pop(key, None)
    service = copy["service_windows"]
    for s in copy["students"]:
        if s["id"] in unit["participants"]:
            s["availability_state"] = "APPROVED"
            s["availability"] = [
                {"mode": w["mode"], "start": w["start"], "end": w["end"]}
                for w in service
                if w["location"] == "REMOTE" or w["mode"] == "IN_PERSON"
            ]
    for t in copy["tutors"]:
        if t["id"] in unit["allowed_tutors"]:
            t["availability_state"] = "APPROVED"
            t["availability"] = deepcopy(service)
    return copy


def hypotheses(data, candidates, assignments, keys, budget=3.0):
    began = monotonic()
    units = {u["demand_key"]: u for u in data["units"]}
    tutors = {t["id"]: t for t in data["tutors"]}
    students = {s["id"]: s for s in data["students"]}
    resources = {r["id"]: r for r in data["resources"]}
    result = []
    for key in keys[:MAX_UNITS]:
        if monotonic() - began > budget:
            break
        unit = units[key]
        if any(a["demand_key"] == key for a in assignments):
            continue
        declared = []
        for c in candidates.get(key, []):
            conflicts = _conflicts(data, c, assignments, units, tutors, resources)
            declared.append((len(conflicts), c["start"], c, conflicts))
        declared.sort(key=lambda item: (item[0], item[1]))
        for _, _, c, conflicts in declared[:PER_KIND]:
            result.append(
                {
                    "kind": "MOVE_WITHIN_DECLARED",
                    "status": "HYPOTHESIS",
                    "demand_key": key,
                    "tutor_id": c["tutor_id"],
                    "mode": c["mode"],
                    "start": c["start"],
                    "end": c["end"],
                    "requires_moving": conflicts,
                    "missing_availability": [],
                    "booking_allowed": False,
                }
            )
        try:
            relaxed, _ = compile_candidates(_relaxed(data, unit))
        except InputError:
            continue
        seen = {(c["tutor_id"], c["mode"], c["start"]) for c in candidates.get(key, [])}
        asks = []
        for c in relaxed.get(key, []):
            if (c["tutor_id"], c["mode"], c["start"]) in seen:
                continue
            missing = []
            t = tutors[c["tutor_id"]]
            if t["availability_state"] == "DECLARED_NONE" or not contained(
                [
                    w
                    for w in t["availability"]
                    if w["mode"] == c["mode"] and w["location"] == c["location"]
                ],
                c["start"],
                c["end"] + t["pause_minutes"],
            ):
                missing.append({"kind": "TUTOR", "id": c["tutor_id"]})
            for p in unit["participants"]:
                s = students[p]
                if s["availability_state"] == "DECLARED_NONE" or not contained(
                    [w for w in s["availability"] if w["mode"] == c["mode"]],
                    c["start"],
                    c["end"],
                ):
                    missing.append({"kind": "STUDENT", "id": p})
            if not missing:
                continue
            conflicts = _conflicts(data, c, assignments, units, tutors, resources)
            asks.append(
                (len(missing), len(conflicts), c["start"], c, missing, conflicts)
            )
        asks.sort(key=lambda item: item[:3])
        for _, _, _, c, missing, conflicts in asks[:PER_KIND]:
            result.append(
                {
                    "kind": "REQUEST_NEW_AVAILABILITY",
                    "status": "HYPOTHESIS",
                    "demand_key": key,
                    "tutor_id": c["tutor_id"],
                    "mode": c["mode"],
                    "start": c["start"],
                    "end": c["end"],
                    "requires_moving": conflicts,
                    "missing_availability": missing,
                    "booking_allowed": False,
                }
            )
    return result


def _solve(bundle, seconds, assumptions=False):
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = max(0.05, seconds)
    if assumptions:
        bundle.model.add_assumptions(
            [bundle.model.get_bool_var_from_proto_index(i) for i in bundle.assumptions]
        )
    code = solver.solve(bundle.model)
    return solver, solver.status_name(code)


def conflict_analysis(data, candidates, budget):
    began = monotonic()
    required = [
        u["demand_key"]
        for u in data["units"]
        if (data["mode"] == "STRICT" or u["mandatory"]) and not u["locked_assignment"]
    ]
    locked = {u["demand_key"] for u in data["units"] if u["locked_assignment"]}
    isolated = {
        "individually_infeasible": [],
        "individually_feasible": [],
        "not_checked": [],
    }
    for key in required:
        if (
            len(isolated["individually_infeasible"])
            + len(isolated["individually_feasible"])
            >= MAX_ISOLATED
            or monotonic() - began > budget / 2
        ):
            isolated["not_checked"].append(key)
            continue
        if not candidates[key]:
            isolated["individually_infeasible"].append(key)
            continue
        sub = deepcopy(data)
        sub["mode"] = "COVERAGE"
        for u in sub["units"]:
            u["mandatory"] = u["demand_key"] == key or u["demand_key"] in locked
        sub.pop("family_constraints", None)
        sub.pop("sequences", None)
        bundle = build(sub, candidates, only={key} | locked)
        _, status = _solve(bundle, min(1.0, budget / 4))
        bucket = (
            "individually_infeasible"
            if status == "INFEASIBLE"
            else "individually_feasible"
            if status in ("OPTIMAL", "FEASIBLE")
            else "not_checked"
        )
        isolated[bucket].append(key)
    conflict = {"status": "NOT_RUN", "members": []}
    remaining = budget - (monotonic() - began)
    if remaining > 0.1:
        bundle = build(data, candidates, assumptions=True)
        solver, status = _solve(bundle, remaining, assumptions=True)
        if status == "INFEASIBLE":
            indices = solver.sufficient_assumptions_for_infeasibility()
            conflict = {
                "status": "SUFFICIENT_NOT_MINIMAL",
                "members": sorted(
                    bundle.assumptions[i] for i in indices if i in bundle.assumptions
                ),
            }
            if not conflict["members"]:
                conflict["status"] = "HARD_CORE_ONLY"
        else:
            conflict["status"] = status
    return {
        "note": "Analisi diagnostica: insieme sufficiente, non necessariamente minimo; nessun vincolo rilassato nella proposta",
        "isolated_submodels": isolated,
        "conflict_set": conflict,
    }


def scope_expansion(data, simulate):
    replanning = data.get("replanning")
    if (
        not replanning
        or replanning["scope"] != "LOCAL"
        or not replanning["propose_scope_expansion"]
        or not replanning["expansion_candidates"]
    ):
        return None
    relaxed = deepcopy(data)
    keys = set(replanning["expansion_candidates"])
    for u in relaxed["units"]:
        if u["demand_key"] in keys:
            u["previous_assignment"] = u["locked_assignment"]
            u["locked_assignment"] = None
            relaxed["replanning"]["unlocked"].append(
                {
                    "demand_key": u["demand_key"],
                    "authorization_id": "diagnostic-hypothesis",
                }
            )
    order = [t for t in relaxed["objective_order"] if t in ("P0", "P1", "P2")]
    relaxed["objective_order"] = order + ["C"]
    relaxed["budget_seconds"] = max(0.1, min(relaxed["budget_seconds"], 5))
    relaxed["replanning"]["propose_scope_expansion"] = False
    relaxed["replanning"]["expansion_candidates"] = []
    outcome = simulate(relaxed, with_diagnostics=False)
    if outcome["solver_status"] not in ("OPTIMAL", "FEASIBLE"):
        return {
            "status": "NO_EXPANSION_FOUND",
            "additional_unlock": [],
            "auto_applied": False,
            "relaxed_status": outcome["solver_status"],
        }
    units = {u["demand_key"]: u for u in data["units"]}
    chosen = {a["demand_key"]: a for a in outcome["assignments"]}
    moved = sorted(
        k
        for k in keys
        if k not in chosen or not _same(chosen[k], units[k]["locked_assignment"])
    )
    return {
        "status": "PROPOSED_REQUIRES_APPROVAL",
        "additional_unlock": moved,
        "auto_applied": False,
        "relaxed_status": outcome["solver_status"],
        "relaxed_unassigned": len(outcome["unassigned"]),
    }
