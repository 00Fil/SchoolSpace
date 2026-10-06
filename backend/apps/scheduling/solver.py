"""Real CP-SAT engine over a bounded DTO. Never publishes or writes bookings.

Search proceeds by lexicographic phases (paper §6.4): each term of
``objective_order`` is minimised in turn and fixed only after OPTIMAL.  A
FEASIBLE/time-limited phase stops the sequence: lower terms are not optimised
and no global lexicographic optimum is claimed.  The independent validator and
the independent objective evaluator are the source of truth for the result.
"""

from importlib.metadata import version
from time import monotonic
from ortools.sat.python import cp_model
from .contracts import parse_input, input_hash, InputError
from .candidates import compile_candidates, public_fields, POOL
from .model import build
from .objectives import evaluate
from .validator import validate_assignments
from . import diagnostics
from .warmstart import greedy

BUILD_VERSION = "0.8.0"
RESULT_STATUSES = {
    "OPTIMAL",
    "FEASIBLE",
    "INFEASIBLE",
    "UNKNOWN",
    "MODEL_INVALID",
    "BLOCKED",
    "VALIDATION_FAILED",
}
DIAGNOSTIC_BUDGET_SECONDS = 5.0


def objective_scope(data):
    if data["schema_version"] == "0.4":
        return "COVERAGE_P0_P1_P2_ONLY"
    return "LEXICOGRAPHIC_VECTOR"


def assign_pooled_spaces(data, assignments):
    """Exact interval colouring of pooled identical spaces (greedy by start)."""
    spaces = [r for r in data["resources"] if r["kind"] == "SPACE"]
    if not spaces:
        return True
    buffer = spaces[0]["buffer_minutes"]
    requests = []
    for a in assignments:
        for field in ("space_id", "student_space_id"):
            if a.get(field) == POOL:
                requests.append((a["start"], a["end"] + buffer, id(a), field, a))
    free_at = {space["id"]: None for space in spaces}
    for start, end, _, field, a in sorted(
        requests, key=lambda r: (r[0], r[1], r[2], r[3])
    ):
        chosen = None
        for space in spaces:
            last = free_at[space["id"]]
            other = a.get("space_id") if field == "student_space_id" else None
            if (last is None or last <= start) and space["id"] != other:
                chosen = space["id"]
                break
        if chosen is None:
            return False
        free_at[chosen] = end
        a[field] = chosen
    return True


WATCH_THRESHOLD_SECONDS = 30
WATCH_INTERVAL_SECONDS = 20


def solve_watched(solver, model, progress, remaining):
    """Long searches (profilo THOROUGH) keep the heartbeat alive and honour a
    cancellation while CP-SAT is running: a watchdog thread calls ``progress``
    every few seconds and stops the search when it raises InterruptedError.
    Short searches (<= 30 s, NFR04) are unchanged."""
    if remaining <= WATCH_THRESHOLD_SECONDS:
        return solver.solve(model)
    import threading

    done = threading.Event()
    interrupted = []

    def watch():
        try:
            while not done.wait(WATCH_INTERVAL_SECONDS):
                try:
                    progress("SEARCH")
                except InterruptedError:
                    interrupted.append(True)
                    solver.stop_search()
                    return
                except Exception:
                    pass  # heartbeat best effort: never kills the search
        finally:
            try:
                from django.db import connection

                connection.close()
            except Exception:
                pass

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        code = solver.solve(model)
    finally:
        done.set()
        thread.join()
    if interrupted:
        raise InterruptedError("CANCELLED")
    return code


def simulate(value, progress=None, *, with_diagnostics=True):
    progress = progress or (lambda phase: None)
    progress("PREFLIGHT")
    began = monotonic()
    data = parse_input(value)
    v05 = data["schema_version"] == "0.5"
    base = {
        "schema_version": data["schema_version"],
        "build_version": BUILD_VERSION,
        "objective_scope": objective_scope(data),
        "execution_mode": "IN_PROCESS_DTO",
        "publishable": False,
        "calendar_changed": False,
        "epoch": data["epoch"],
        "timezone": data["timezone"],
        "input_hash": input_hash(data),
        "policy_version": data["policy_version"],
        "solver_version": version("ortools"),
        "assignments": [],
        "unassigned": [],
        "optimality_proven_levels": [],
        "validation": {"status": "NOT_RUN", "violations": []},
        "is_complete": False,
    }
    if v05:
        base["objective_vector"] = list(data["objective_order"])
        base["policy_approvals"] = policy_approvals(data)
        base["warnings"] = [
            {
                "code": "POLICY_PENDING_APPROVAL",
                "message": f"Policy {name} da approvare",
            }
            for name, state in base["policy_approvals"].items()
            if state != "APPROVED"
        ]

    def finish(result):
        if v05 and "statistics" in result:
            result["statistics"].setdefault("wall_time_seconds", monotonic() - began)
        return result

    try:
        candidates, ledger = compile_candidates(data)
    except InputError as error:
        result = {
            **base,
            "solver_status": "BLOCKED",
            "diagnostics": [{"code": error.code, "message": error.message}],
            "statistics": {"wall_time_seconds": monotonic() - began},
        }
        if v05 and error.code == "LOCKED_ILLEGAL" and data.get("replanning"):
            result["scope_expansion"] = {
                "status": "PROPOSED_REQUIRES_APPROVAL",
                "additional_unlock": list(error.fields),
                "auto_applied": False,
                "reason": "LOCKED_NOW_ILLEGAL",
            }
        return result
    locked = [u["locked_assignment"] for u in data["units"] if u["locked_assignment"]]
    fixed_validation = validate_assignments(data, locked, require_coverage=False)
    if fixed_validation["status"] == "FAILED":
        return {
            **base,
            "solver_status": "BLOCKED",
            "diagnostics": [
                {
                    "code": "LOCKED_CONFLICT",
                    "message": "Appuntamenti bloccati incompatibili",
                }
            ],
            "validation": fixed_validation,
            "statistics": {"wall_time_seconds": monotonic() - began},
        }
    progress("MODEL")
    bundle = build(data, candidates)
    model = bundle.model
    problem = model.validate()
    if problem:
        return {
            **base,
            "solver_status": "MODEL_INVALID",
            "diagnostics": [
                {
                    "code": "MODEL_INVALID",
                    "message": "Modello invalido; nessun calendario prodotto",
                }
            ],
            "statistics": {"wall_time_seconds": monotonic() - began},
        }
    if v05:
        # Constructive incumbent as a hint only (never a result by itself).
        hinted = greedy(data, candidates)
        for candidate, x in bundle.choices:
            model.add_hint(x, int(hinted.get(candidate["demand_key"]) is candidate))
        for key, z in bundle.presence.items():
            model.add_hint(z, int(key in hinted))
        statistics_hint = len(hinted)
    else:
        statistics_hint = None
    built = monotonic()
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = data.get("search_workers", 1)
    solver.parameters.random_seed = 0
    if v05 and data["budget_seconds"] <= WATCH_THRESHOLD_SECONDS:
        # Benchmark-driven (T34): full probing/presolve loops on ~10^5 optional
        # alternatives consumed the whole budget before the first solution.
        # v0.9.4: the THOROUGH profile (hours of budget) keeps CP-SAT's full
        # presolve and probing, which pay off on long searches.
        solver.parameters.cp_model_probing_level = 0
        solver.parameters.max_presolve_iterations = 1
        solver.parameters.symmetry_level = 1
    proven = []
    best = None
    best_values = None
    status = "UNKNOWN"
    termination = "TIME_LIMIT"
    objective_values = {}
    phases = []
    # Budget covers the whole solve sequence; lower levels never optimise after an unproven level.
    # v0.4: the budget covers preflight and model build too (historical).
    # v0.5 (NFR04): budget_seconds is the search budget, starting after build.
    deadline = (built if v05 else began) + data["budget_seconds"]
    for term in data["objective_order"]:
        objective = bundle.terms[term]
        if best is not None and isinstance(objective, int):
            # Constant term (e.g. no unit of that priority): proven without search.
            objective_values[term] = objective
            proven.append(term)
            phases.append({"term": term, "status": "OPTIMAL", "seconds": 0.0})
            continue
        remaining = deadline - monotonic()
        if remaining <= 0:
            status = "FEASIBLE" if best is not None else "UNKNOWN"
            termination = "TIME_LIMIT"
            break
        model.minimize(objective)
        if best_values is not None:
            model.clear_hints()
            for (candidate, x), value in zip(bundle.choices, best_values):
                model.add_hint(x, value)
            chosen_keys = {
                c["demand_key"] for (c, _), v in zip(bundle.choices, best_values) if v
            }
            for key, z in bundle.presence.items():
                model.add_hint(z, int(key in chosen_keys))
        solver.parameters.max_time_in_seconds = remaining
        progress("SEARCH")
        phase_began = monotonic()
        code = solve_watched(solver, model, progress, remaining)
        name = solver.status_name(code)
        phases.append(
            {
                "term": term,
                "status": name,
                "seconds": round(monotonic() - phase_began, 4),
            }
        )
        if name not in ("OPTIMAL", "FEASIBLE"):
            status = "FEASIBLE" if best is not None and name == "UNKNOWN" else name
            if name in ("MODEL_INVALID", "INFEASIBLE"):
                best = None
            termination = "TIME_LIMIT" if name == "UNKNOWN" else name
            break
        best_values = [int(solver.value(x)) for _, x in bundle.choices]
        best = [
            public_fields(candidate, data)
            for (candidate, _), value in zip(bundle.choices, best_values)
            if value
        ]
        objective_values[term] = int(round(solver.objective_value))
        status = name
        if name != "OPTIMAL":
            termination = "TIME_LIMIT"
            break
        proven.append(term)
        model.add(objective == objective_values[term])
        termination = "OBJECTIVES_PROVEN"
    searched = monotonic()
    statistics = {
        "candidate_count": len(bundle.choices),
        "model_build_seconds": round(built - began, 4),
        "search_seconds": round(searched - built, 4),
    }
    if v05:
        statistics["phases"] = phases
        statistics["variables"] = len(model.proto.variables)
        statistics["constraints"] = len(model.proto.constraints)
        statistics["hinted_units"] = statistics_hint
    if best is None:
        result = {
            **base,
            "solver_status": status,
            "termination_reason": termination,
            "diagnostics": [
                {
                    "code": status,
                    "message": "Impossibilità dimostrata nel DTO"
                    if status == "INFEASIBLE"
                    else "Ricerca non conclusiva o errore tecnico; nessuna prova di impossibilità",
                }
            ],
            "empty_domain_diagnostics": [
                {"demand_key": key, "reason_codes": ledger[key]}
                for key, options in candidates.items()
                if not options
            ],
            "statistics": {**statistics, "wall_time_seconds": monotonic() - began},
        }
        if v05 and with_diagnostics:
            progress("DIAGNOSTICS")
            diag_began = monotonic()
            if status == "INFEASIBLE":
                result["conflict_analysis"] = diagnostics.conflict_analysis(
                    data, candidates, DIAGNOSTIC_BUDGET_SECONDS
                )
            result["hypotheses"] = diagnostics.hypotheses(
                data,
                candidates,
                [],
                [u["demand_key"] for u in data["units"] if _required(data, u)],
            )
            expansion = diagnostics.scope_expansion(data, simulate)
            if expansion:
                result["scope_expansion"] = expansion
            result["statistics"]["diagnostic_seconds"] = round(
                monotonic() - diag_began, 4
            )
        return result
    progress("VALIDATION")
    if not assign_pooled_spaces(data, best):
        return _validation_failed(
            base,
            statistics,
            began,
            [{"code": "POOL_COLOURING", "demand_key": "unknown"}],
        )
    validation = validate_assignments(data, best)
    independent = evaluate(data, best)
    mismatched = [
        {"code": "OBJECTIVE_MISMATCH", "demand_key": term}
        for term, value in objective_values.items()
        if independent[term] != value
    ]
    if validation["status"] != "PASSED" or mismatched:
        return _validation_failed(
            base, statistics, began, validation["violations"] + mismatched
        )
    assigned = {a["demand_key"] for a in best}
    unassigned = [
        {
            "demand_key": u["demand_key"],
            "priority": u["priority"],
            "mandatory": u["mandatory"],
            "reason_codes": ledger[u["demand_key"]]
            if not candidates[u["demand_key"]]
            else ["RESOURCE_CONTENTION_OR_LOAD"],
        }
        for u in data["units"]
        if u["demand_key"] not in assigned
    ]
    # Overall OPTIMAL only when every term of the declared vector is proven.
    status = "OPTIMAL" if len(proven) == len(data["objective_order"]) else "FEASIBLE"
    result = {
        **base,
        "solver_status": status,
        "termination_reason": termination,
        "assignments": sorted(best, key=lambda a: (a["start"], a["demand_key"])),
        "unassigned": unassigned,
        "is_complete": not unassigned,
        "optimality_proven_levels": proven,
        "objective_values": objective_values,
        "validation": validation,
        "diagnostics": [],
        "statistics": {**statistics, "wall_time_seconds": monotonic() - began},
    }
    if v05:
        result["evaluated_objectives"] = independent
        if with_diagnostics and unassigned:
            progress("DIAGNOSTICS")
            diag_began = monotonic()
            result["hypotheses"] = diagnostics.hypotheses(
                data, candidates, best, [u["demand_key"] for u in unassigned]
            )
            if any(u["mandatory"] or u["priority"] == "P0" for u in unassigned):
                expansion = diagnostics.scope_expansion(data, simulate)
                if expansion:
                    result["scope_expansion"] = expansion
            result["statistics"]["diagnostic_seconds"] = round(
                monotonic() - diag_began, 4
            )
    return result


def _required(data, unit):
    return (
        data["mode"] == "STRICT" or unit["mandatory"] or bool(unit["locked_assignment"])
    )


def _validation_failed(base, statistics, began, violations):
    return {
        **base,
        "solver_status": "VALIDATION_FAILED",
        "validation": {"status": "FAILED", "violations": violations},
        "diagnostics": [
            {
                "code": "VALIDATION_FAILED",
                "message": "Proposta rifiutata dal validatore indipendente",
            }
        ],
        "statistics": {**statistics, "wall_time_seconds": monotonic() - began},
    }


def policy_approvals(data):
    approvals = {}
    if "F" in data["objective_order"]:
        approvals["fairness"] = data["fairness_policy"]["approval_status"]
    return approvals
