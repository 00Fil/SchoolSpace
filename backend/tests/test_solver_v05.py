"""Contract v0.5: full lexicographic vector, H11/H12, D05-D07 cases, diagnostics.

Synthetic models only.  The independent validator and objective evaluator are
the source of truth; tests tamper with outputs to prove they are not bypassed.
"""

from copy import deepcopy
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from apps.scheduling.benchmark import benchmark_input
from apps.scheduling.candidates import compile_candidates
from apps.scheduling.contracts import InputError, parse_input, input_hash
from apps.scheduling.fixtures import demo_input
from apps.scheduling.objectives import evaluate
from apps.scheduling.policies import fairness_policy
from apps.scheduling.solver import simulate
from apps.scheduling.validator import validate_assignments

ROOT = Path(__file__).resolve().parents[2]
RESULT = Draft202012Validator(
    json.loads((ROOT / "contracts/planning-result.schema.json").read_text())
)
DAY = 1440


def v05(n=1, order=("P0", "P1", "P2")):
    data = demo_input()
    data["schema_version"] = "0.5"
    data["budget_seconds"] = 10
    data["objective_order"] = list(order)
    if "F" in order:
        data["fairness_policy"] = fairness_policy()
    template = deepcopy(data["units"][0])
    data["units"] = []
    for i in range(n):
        unit = deepcopy(template)
        unit.update(
            demand_key=f"unit-{i + 1}",
            type="INDIVIDUAL",
            participants=[f"student-demo-{i + 1}"],
            allowed_tutors=["tutor-demo-1"],
            earliest_start=480,
            latest_end=840,
        )
        data["units"].append(unit)
    data["resources"] = data["resources"][:1]
    return data


def run(data):
    result = simulate(data)
    RESULT.validate(result)
    return result


def by_key(result):
    return {a["demand_key"]: a for a in result["assignments"]}


def coverage(data):
    data["mode"] = "COVERAGE"
    for u in data["units"]:
        u["mandatory"] = False
    return data


# --- contract versioning -------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(horizon_days=8, horizon_minutes=8 * DAY),
        lambda d: d.update(series=[]),
        lambda d: d.update(student_buffer_minutes=15),
        lambda d: d.update(allow_cross_local_midnight=True),
        lambda d: d.update(objective_order=["P0", "P1", "P2", "F"]),
        lambda d: d.update(budget_seconds=20),
    ],
)
def test_v04_keeps_historical_limits(change):
    data = demo_input()
    change(data)
    with pytest.raises(InputError) as error:
        parse_input(data)
    assert error.value.code in ("VERSION_FEATURE", "INVALID_INPUT")


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda d: d.update(objective_order=["P1", "P0", "P2"]), "OBJECTIVE_ORDER"),
        (
            lambda d: d.update(objective_order=["P0", "P1", "P2", "F"]),
            "FAIRNESS_POLICY_REQUIRED",
        ),
        (
            lambda d: (
                d.update(
                    limits={
                        "max_units": 1,
                        "max_tutors": 10,
                        "max_students": 120,
                        "max_candidates": 10,
                    }
                )
                or d["units"].append({**deepcopy(d["units"][0]), "demand_key": "x"})
            ),
            "SIZE_LIMIT",
        ),
        (
            lambda d: (
                d["units"][0].update(previous_assignment=None)
                or d.update(
                    replanning={
                        "scope": "LOCAL",
                        "unlocked": [
                            {"demand_key": "unit-1", "authorization_id": "a1"}
                        ],
                        "expansion_candidates": [],
                        "propose_scope_expansion": False,
                    }
                )
            ),
            "UNLOCK_AUTHORIZATION",
        ),
    ],
)
def test_v05_semantic_rejections(change, code):
    data = v05()
    change(data)
    with pytest.raises(InputError) as error:
        parse_input(data)
    assert error.value.code == code


def test_v05_result_reports_vector_and_pending_policy():
    data = v05(order=("P0", "P1", "P2", "F", "G"))
    result = run(data)
    assert result["schema_version"] == "0.5"
    assert result["objective_scope"] == "LEXICOGRAPHIC_VECTOR"
    assert result["objective_vector"] == ["P0", "P1", "P2", "F", "G"]
    assert result["policy_approvals"] == {"fairness": "PENDING_APPROVAL"}
    assert result["warnings"][0]["code"] == "POLICY_PENDING_APPROVAL"
    assert result["solver_status"] == "OPTIMAL"
    assert result["optimality_proven_levels"] == ["P0", "P1", "P2", "F", "G"]
    assert result["evaluated_objectives"]["G"] == result["objective_values"]["G"] == 2
    assert result["publishable"] is False


def test_fairness_policy_registry_is_versioned_and_pending():
    policy = fairness_policy()
    assert policy["approval_status"] == "PENDING_APPROVAL" and policy["version"] == 1
    with pytest.raises(ValueError):
        fairness_policy(version=2)


# --- lexicographic vector ------------------------------------------------


def test_fairness_spreads_deficit_after_coverage():
    data = coverage(v05(3, ("P0", "P1", "P2", "F")))
    data["units"][1]["participants"] = ["student-demo-1"]  # A has two units
    data["tutors"][0]["availability"] = [
        {"mode": "IN_PERSON", "location": "ON_SITE", "start": 480, "end": 600}
    ]
    result = run(data)
    assert result["objective_values"]["P1"] == 60
    assert result["objective_values"]["F"] == 500
    assert "unit-3" in by_key(result)  # student B is not left with 100% deficit


def test_unproven_level_stops_lower_terms(monkeypatch):
    from ortools.sat.python import cp_model

    original = cp_model.CpSolver.solve
    calls = []

    def solve(self, model):
        code = original(self, model)
        calls.append(code)
        return cp_model.FEASIBLE if len(calls) == 2 else code

    monkeypatch.setattr(cp_model.CpSolver, "solve", solve)
    data = coverage(v05(2, ("P0", "P1", "P2", "F", "G")))
    result = run(data)
    assert result["solver_status"] == "FEASIBLE"
    assert result["optimality_proven_levels"] == ["P0"]
    assert "F" not in result["objective_values"]


def test_objective_mismatch_is_validation_failure(monkeypatch):
    import apps.scheduling.solver as solver

    monkeypatch.setattr(
        solver,
        "evaluate",
        lambda data, a: {t: 999 for t in "P0 P1 P2 F C R P G".split()},
    )
    result = run(v05())
    assert (
        result["solver_status"] == "VALIDATION_FAILED" and result["assignments"] == []
    )
    assert any(
        v["code"] == "OBJECTIVE_MISMATCH" for v in result["validation"]["violations"]
    )


def test_preferences_and_fragmentation_terms():
    data = v05(2, ("P0", "P1", "P2", "P", "G"))
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
    data["preferences"] = [
        {
            "subject_kind": "STUDENT",
            "subject_id": "student-demo-1",
            "windows": [{"start": 600, "end": 720}],
            "weight": 5,
        }
    ]
    result = run(data)
    assert result["objective_values"]["P"] == 0
    assert all(600 <= a["start"] and a["end"] <= 720 for a in result["assignments"])
    assert evaluate(parse_input(data), result["assignments"])["G"] == 2


# --- recurring stability (GAP-D03) ---------------------------------------


def two_weeks(order=("P0", "P1", "P2", "R")):
    data = v05(2, order)
    data.update(horizon_days=14, horizon_minutes=14 * DAY)
    week = 7 * DAY
    for w in (
        data["service_windows"]
        + data["tutors"][0]["availability"]
        + data["resources"][0]["availability"]
    ):
        pass
    extend = lambda windows: (
        windows
        + [{**w, "start": w["start"] + week, "end": w["end"] + week} for w in windows]
    )
    data["service_windows"] = extend(data["service_windows"])
    for t in data["tutors"]:
        t["availability"] = extend(t["availability"])
        for s in t["skills"]:
            s["end"] = 14 * DAY
    for s in data["students"]:
        s["availability"] = extend(s["availability"])
    data["resources"][0]["availability"] = extend(data["resources"][0]["availability"])
    data["units"][1].update(
        participants=["student-demo-1"], earliest_start=week, latest_end=week + 840
    )
    data["units"][0]["latest_end"] = 840
    data["series"] = [
        {
            "series_key": "s1",
            "units": ["unit-1", "unit-2"],
            "stability": "PREFERRED",
            "preferred_slot": None,
        }
    ]
    return data


def test_recurring_slot_is_kept_across_weeks():
    result = run(two_weeks())
    a = by_key(result)
    assert result["objective_values"]["R"] == 0
    assert a["unit-2"]["start"] - a["unit-1"]["start"] == 7 * DAY


def test_preferred_slot_from_previous_plan_and_required_incompatible_week():
    data = two_weeks()
    data["series"][0]["preferred_slot"] = {
        "weekday": 0,
        "local_start_minute": 600,
        "source": "PREVIOUS_PLAN",
    }
    result = run(data)
    assert [a["start"] % (7 * DAY) for a in result["assignments"]] == [480, 480]
    data["series"][0]["stability"] = "REQUIRED"
    data["students"][0]["availability"] = [
        w for w in data["students"][0]["availability"] if w["start"] < 7 * DAY
    ]
    data["students"][0]["availability"] += [
        {"mode": "IN_PERSON", "start": 7 * DAY + 720, "end": 7 * DAY + 840}
    ]
    result = run(data)
    assert result["solver_status"] == "INFEASIBLE"
    reasons = {
        d["demand_key"]: d["reason_codes"] for d in result["empty_domain_diagnostics"]
    }
    assert "RECURRING_SLOT_REQUIRED" in reasons["unit-2"]


# --- H11 / H12 (GAP-D04) -------------------------------------------------


def family(kind, n=2):
    data = v05(n)
    data["resources"] = demo_input()["resources"]
    for u in data["units"]:
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    data["family_constraints"] = [
        {
            "constraint_id": "fam-1",
            "kind": kind,
            "units": [u["demand_key"] for u in data["units"]],
        }
    ]
    return data


def test_same_start_synchronisation():
    data = family("SAME_START")
    data["units"][1]["duration_minutes"] = 90
    data["students"][0]["availability"] = [
        {"mode": "IN_PERSON", "start": 600, "end": 700}
    ]
    result = run(data)
    a = by_key(result)
    assert a["unit-1"]["start"] == a["unit-2"]["start"]
    assert 600 <= a["unit-1"]["start"] and a["unit-1"]["end"] <= 700
    tampered = deepcopy(result["assignments"])
    tampered[1]["start"] += 15
    tampered[1]["end"] += 15
    codes = {
        v["code"]
        for v in validate_assignments(parse_input(data), tampered)["violations"]
    }
    assert "FAMILY_SYNC" in codes


def test_same_interval_requires_equal_duration_and_sync_is_all_or_none():
    data = family("SAME_INTERVAL")
    data["units"][1]["duration_minutes"] = 90
    with pytest.raises(InputError):
        parse_input(data)
    data = coverage(family("SAME_START"))
    data["students"][1]["availability"] = []
    data["students"][1]["availability_state"] = "DECLARED_NONE"
    result = run(data)
    assert result["assignments"] == []  # unit-1 not placed without its sibling


def test_different_days_and_no_overlap():
    data = family("DIFFERENT_DAYS")
    for u in data["units"]:
        u["latest_end"] = 2 * DAY
    for item in data["tutors"] + data["students"]:
        item["availability"] += [
            {**w, "start": w["start"] + DAY, "end": w["end"] + DAY}
            for w in item["availability"]
        ]
    data["service_windows"] += [
        {**w, "start": w["start"] + DAY, "end": w["end"] + DAY}
        for w in data["service_windows"]
    ]
    for r in data["resources"]:
        r["availability"] += [{"start": 480 + DAY, "end": 840 + DAY}]
    result = run(data)
    a = by_key(result)
    assert a["unit-1"]["start"] // DAY != a["unit-2"]["start"] // DAY
    data["family_constraints"][0]["kind"] = "NO_OVERLAP"
    result = run(data)
    a = by_key(result)
    assert (
        a["unit-1"]["end"] <= a["unit-2"]["start"]
        or a["unit-2"]["end"] <= a["unit-1"]["start"]
    )


def test_curricular_sequence_and_predecessor():
    data = coverage(v05(2))
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
    data["sequences"] = [
        {
            "sequence_id": "seq-1",
            "units": ["unit-2", "unit-1"],
            "min_gap_minutes": 30,
            "max_gap_minutes": None,
            "require_predecessor": True,
        }
    ]
    result = run(data)
    a = by_key(result)
    assert a["unit-1"]["start"] >= a["unit-2"]["end"] + 30
    data["units"][1]["allowed_modes"] = ["ONLINE"]
    data["tutors"][0]["skills"] = [
        s for s in data["tutors"][0]["skills"] if s["mode"] == "IN_PERSON"
    ]
    result = run(data)
    assert result["assignments"] == []  # unit-1 may not be placed without unit-2
    bad = [
        {
            "demand_key": "unit-1",
            "tutor_id": "tutor-demo-1",
            "mode": "IN_PERSON",
            "location": "ON_SITE",
            "space_id": "space-demo-1",
            "video_id": None,
            "start": 480,
            "end": 540,
        }
    ]
    codes = {
        v["code"] for v in validate_assignments(parse_input(data), bad)["violations"]
    }
    assert "SEQUENCE_PREDECESSOR" in codes


def test_enrollment_period_restricts_domain():
    data = v05()
    data["enrollments"] = [
        {"student_id": "student-demo-1", "periods": [{"start": 720, "end": 840}]}
    ]
    result = run(data)
    assert result["assignments"][0]["start"] >= 720
    data["enrollments"][0]["periods"] = [{"start": 0, "end": 300}]
    result = run(data)
    assert result["solver_status"] == "INFEASIBLE"
    assert "OUTSIDE_ENROLLMENT" in result["empty_domain_diagnostics"][0]["reason_codes"]


# --- GAP-D07 -------------------------------------------------------------


def test_student_online_from_centre_needs_a_seat():
    data = v05()
    u = data["units"][0]
    u["allowed_modes"] = ["ONLINE"]
    data["students"][0]["availability"] = [
        {"mode": "ONLINE", "location": "ON_SITE", "start": 480, "end": 840}
    ]
    data["service_windows"].append(
        {"mode": "ONLINE", "location": "ON_SITE", "start": 480, "end": 840}
    )
    result = run(data)
    a = result["assignments"][0]
    assert (
        a["student_location"] == "ON_SITE" and a["student_space_id"] == "space-demo-1"
    )
    assert a["location"] == "REMOTE"
    stripped = {**a, "student_space_id": None}
    codes = {
        v["code"]
        for v in validate_assignments(parse_input(data), [stripped])["violations"]
    }
    assert "STUDENT_SEAT_REQUIRED" in codes
    data["closures"] = [
        {"mode": "ALL", "resource_id": "space-demo-1", "start": 0, "end": 840}
    ]
    assert run(data)["solver_status"] == "INFEASIBLE"


def test_student_buffer_separates_lessons():
    data = v05(2)
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
        u["latest_end"] = 600
    data["resources"] = demo_input()["resources"]
    assert run(data)["is_complete"]
    data["student_buffer_minutes"] = 15
    assert run(data)["solver_status"] == "INFEASIBLE"
    data["units"][1]["latest_end"] = 615
    result = run(data)
    a = sorted(result["assignments"], key=lambda x: x["start"])
    assert a[1]["start"] >= a[0]["end"] + 15


def test_lesson_across_local_midnight_explicit_opt_in():
    data = v05()
    # Epoch 00:00Z is 02:00 local: 1290-1350 is 23:30-00:30 Europe/Rome.
    data["units"][0].update(earliest_start=1290, latest_end=1350)
    for item in data["tutors"] + data["students"]:
        for w in item["availability"]:
            w.update(start=1290, end=1350)
    for w in data["service_windows"]:
        w.update(start=1290, end=1350)
    data["resources"][0]["availability"] = [{"start": 1290, "end": 1350}]
    result = run(data)
    assert result["solver_status"] == "INFEASIBLE"
    assert (
        "CROSS_LOCAL_MIDNIGHT" in result["empty_domain_diagnostics"][0]["reason_codes"]
    )
    data["allow_cross_local_midnight"] = True
    result = run(data)
    assert result["is_complete"] and result["validation"]["status"] == "PASSED"


# --- GAP-D05 local replanning ---------------------------------------------


def previous(data, index=0, **changes):
    u = data["units"][index]
    a = {
        "demand_key": u["demand_key"],
        "tutor_id": "tutor-demo-1",
        "mode": "IN_PERSON",
        "location": "ON_SITE",
        "space_id": "space-demo-1",
        "video_id": None,
        "start": 480,
        "end": 540,
    }
    a.update(changes)
    return a


def test_unlocked_appointment_kept_when_possible_and_counted_when_moved():
    data = v05(order=("P0", "P1", "P2", "C"))
    data["units"][0]["previous_assignment"] = previous(data, start=600, end=660)
    data["replanning"] = {
        "scope": "LOCAL",
        "unlocked": [{"demand_key": "unit-1", "authorization_id": "auth-1"}],
        "expansion_candidates": [],
        "propose_scope_expansion": False,
    }
    result = run(data)
    assert (
        result["objective_values"]["C"] == 0
        and result["assignments"][0]["start"] == 600
    )
    data["students"][0]["availability"] = [
        {"mode": "IN_PERSON", "start": 700, "end": 840}
    ]
    result = run(data)
    assert (
        result["objective_values"]["C"] == 1
        and result["assignments"][0]["start"] >= 700
    )


def test_previous_assignment_requires_authorization():
    data = v05()
    data["units"][0]["previous_assignment"] = previous(data)
    with pytest.raises(InputError) as error:
        parse_input(data)
    assert error.value.code == "UNLOCK_AUTHORIZATION"


def test_local_scope_proposes_expansion_without_applying_it():
    data = v05(2, ("P0", "P1", "P2", "C"))
    data["mode"] = "COVERAGE"
    data["units"][0].update(locked_assignment=previous(data), mandatory=False)
    data["units"][1].update(
        participants=["student-demo-2"], mandatory=True, priority="P0"
    )
    data["students"][1]["availability"] = [
        {"mode": "IN_PERSON", "start": 480, "end": 540}
    ]
    data["replanning"] = {
        "scope": "LOCAL",
        "unlocked": [],
        "expansion_candidates": ["unit-1"],
        "propose_scope_expansion": True,
    }
    result = run(data)
    assert result["solver_status"] == "INFEASIBLE"
    assert result["scope_expansion"]["status"] == "PROPOSED_REQUIRES_APPROVAL"
    assert result["scope_expansion"]["additional_unlock"] == ["unit-1"]
    assert (
        result["scope_expansion"]["auto_applied"] is False
        and result["assignments"] == []
    )


def test_locked_now_illegal_proposes_unlock():
    data = v05()
    data["units"][0]["locked_assignment"] = previous(data, start=470, end=530)
    data["replanning"] = {
        "scope": "LOCAL",
        "unlocked": [],
        "expansion_candidates": [],
        "propose_scope_expansion": True,
    }
    result = run(data)
    assert result["solver_status"] == "BLOCKED"
    assert result["scope_expansion"]["additional_unlock"] == ["unit-1"]


# --- GAP-D06 diagnostics ---------------------------------------------------


def test_hypotheses_distinguish_declared_and_new_availability():
    data = coverage(v05(2))
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
        u["latest_end"] = 840
    data["students"][0]["availability"] = [
        {"mode": "IN_PERSON", "start": 480, "end": 540}
    ]
    result = run(data)
    kinds = {h["kind"] for h in result["hypotheses"]}
    assert kinds == {"MOVE_WITHIN_DECLARED", "REQUEST_NEW_AVAILABILITY"}
    for h in result["hypotheses"]:
        assert h["booking_allowed"] is False and h["status"] == "HYPOTHESIS"
        if h["kind"] == "REQUEST_NEW_AVAILABILITY":
            assert {"kind": "STUDENT", "id": "student-demo-1"} in h[
                "missing_availability"
            ]
        else:
            assert h["requires_moving"]  # the declared hour is taken by the other unit


def test_conflict_analysis_separates_individual_and_joint_impossibility():
    data = v05(3)
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
    data["students"][0]["availability"] = [
        {"mode": "IN_PERSON", "start": 480, "end": 600}
    ]
    data["units"][2]["allowed_modes"] = ["ONLINE"]
    data["tutors"][0]["skills"] = [
        s for s in data["tutors"][0]["skills"] if s["mode"] == "IN_PERSON"
    ]
    result = run(data)
    assert result["solver_status"] == "INFEASIBLE"
    analysis = result["conflict_analysis"]
    assert analysis["isolated_submodels"]["individually_infeasible"] == ["unit-3"]
    assert set(analysis["isolated_submodels"]["individually_feasible"]) == {
        "unit-1",
        "unit-2",
    }
    assert analysis["conflict_set"]["status"] == "SUFFICIENT_NOT_MINIMAL"
    assert analysis["conflict_set"]["members"]


# --- spaces, limits and benchmark fixture (GAP-D01) ----------------------


def test_pooled_identical_spaces_are_coloured_exactly():
    data = v05(3)
    data["resources"] = demo_input()["resources"]
    data["tutors"] = [
        {**deepcopy(data["tutors"][0]), "id": f"tutor-{i}"} for i in range(3)
    ]
    for u in data["units"]:
        u["allowed_tutors"] = [t["id"] for t in data["tutors"]]
        u["latest_end"] = 540
    result = run(data)
    spaces = {a["space_id"] for a in result["assignments"]}
    assert spaces == {"space-demo-1", "space-demo-2", "space-demo-3"}
    assert result["validation"]["status"] == "PASSED"


def test_benchmark_fixture_is_720_units_six_weeks_and_deterministic():
    data = benchmark_input()
    parsed = parse_input(data)
    assert len(parsed["units"]) == 720 and parsed["horizon_days"] == 42
    assert parsed["horizon_minutes"] == 42 * DAY + 60  # end of DST inside the horizon
    assert (
        len({s["id"] for s in parsed["students"]}) == 80 and len(parsed["tutors"]) == 10
    )
    assert input_hash(parse_input(benchmark_input())) == input_hash(parsed)
    candidates, _ = compile_candidates(parsed)
    assert sum(map(len, candidates.values())) <= 150000


def test_contract_fixture_matches_generator():
    fixture = json.loads(
        (ROOT / "contracts/fixtures/planning-benchmark-720.json").read_text()
    )
    assert input_hash(parse_input(fixture)) == input_hash(
        parse_input(benchmark_input())
    )


def test_one_week_benchmark_solves_validly():
    data = benchmark_input(weeks=1, budget=5)
    result = run(data)
    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert result["validation"]["status"] == "PASSED"
    assert not [u for u in result["unassigned"] if u["mandatory"]]
