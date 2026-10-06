"""Small synthetic models: neither the baseline benchmark nor production calendar proof."""

from copy import deepcopy
import json
import pytest
from ortools.sat.python import cp_model
from apps.scheduling.contracts import InputError, parse_input, input_hash
from apps.scheduling.fixtures import demo_input
from apps.scheduling.solver import simulate
from apps.scheduling.validator import validate_assignments


def small(n=1):
    data = demo_input()
    data["budget_seconds"] = 5
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
            latest_end=540,
        )
        data["units"].append(unit)
    data["resources"] = data["resources"][:1]
    return data


def assignment(data, index=0, **overrides):
    unit = data["units"][index]
    a = {
        "demand_key": unit["demand_key"],
        "tutor_id": "tutor-demo-1",
        "mode": "IN_PERSON",
        "location": "ON_SITE",
        "space_id": "space-demo-1",
        "video_id": None,
        "start": unit["earliest_start"],
        "end": unit["earliest_start"] + unit["duration_minutes"],
    }
    a.update(overrides)
    return a


def test_real_cp_sat_demo_valid_complete():
    # The demo proves all three levels in milliseconds; the fixture budget (3 s)
    # covers the whole sequence and could expire under heavy CPU load, turning a
    # proof into FEASIBLE.  A generous budget keeps the assertion strict
    # (OPTIMAL on every level) without depending on machine load.
    data = demo_input()
    data["budget_seconds"] = 10
    result = simulate(data)
    assert result["statistics"]["search_seconds"] < 10
    assert result["solver_status"] == "OPTIMAL"
    assert result["validation"]["status"] == "PASSED"
    assert len(result["assignments"]) == 6 and result["is_complete"]
    assert result["optimality_proven_levels"] == ["P0", "P1", "P2"]
    assert result["objective_scope"] == "COVERAGE_P0_P1_P2_ONLY"
    assert result["publishable"] is False and result["calendar_changed"] is False


def test_input_not_mutated_and_hash_stable():
    data = small()
    original = deepcopy(data)
    result = simulate(data)
    assert data == original and result["input_hash"] == input_hash(original)
    original["policy_version"] = "DIFFERENT"
    assert input_hash(original) != result["input_hash"]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(extra_field="not-supported"),
        lambda d: d["units"][0].update(duration_minutes=60.0),
        lambda d: d["units"][0].update(earliest_start=True),
        lambda d: d["units"].append(deepcopy(d["units"][0])),
        lambda d: d["students"].append(deepcopy(d["students"][0])),
        lambda d: d["units"][0].update(participants=["missing"]),
        lambda d: d["units"][0].update(duration_minutes=75),
        lambda d: d.update(epoch="2026-10-05T00:00:00"),
        lambda d: d.update(epoch="2026-10-05T00:00:00+02:00"),
        lambda d: d.update(epoch="2026-10-05T00:07:00Z"),
        lambda d: d["resources"][0].update(student_capacity=3),
        lambda d: d["tutors"][0]["transition_minutes"]["ON_SITE"].update(ON_SITE=10),
        lambda d: d.update(objective_order=["P0", "P1", "P2", "EQUITY"]),
    ],
)
def test_invalid_or_unsupported_dto_rejected(change):
    data = small()
    change(data)
    with pytest.raises(InputError):
        simulate(data)


def test_missing_availability_is_blocked_not_infeasible():
    data = small()
    data["students"][0]["availability_state"] = "UNKNOWN"
    result = simulate(data)
    assert result["solver_status"] == "BLOCKED"
    assert result["diagnostics"][0]["code"] == "MISSING_AVAILABILITY"


def test_unreferenced_unknown_tutor_does_not_block():
    data = small()
    data["tutors"][1]["availability_state"] = "UNKNOWN"
    assert simulate(data)["is_complete"]


def test_none_is_not_unrestricted():
    data = small()
    data["students"][0].update(availability_state="DECLARED_NONE", availability=[])
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_family_or_curriculum_constraint_not_silently_relaxed():
    data = small()
    data["unsupported_constraints"] = ["family-synchronization", "curriculum-sequence"]
    result = simulate(data)
    assert (
        result["solver_status"] == "BLOCKED"
        and result["diagnostics"][0]["code"] == "UNSUPPORTED_CONSTRAINT"
    )


def test_unqualified_tutor_no_assignments():
    data = small()
    data["tutors"][0]["skills"] = []
    result = simulate(data)
    assert result["solver_status"] == "INFEASIBLE" and not result["assignments"]


def test_dated_skill_must_cover_whole_lesson():
    data = small()
    data["tutors"][0]["skills"][0]["end"] = 510
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_ninety_minutes_do_not_fit_sixty():
    data = small()
    data["units"][0]["duration_minutes"] = 90
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_all_group_participants_intersection():
    data = small()
    data["units"][0].update(
        type="GROUP", participants=["student-demo-1", "student-demo-2"]
    )
    for w in data["students"][1]["availability"]:
        w["end"] = 510
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_group_three_not_split_in_presence():
    data = small()
    data["units"][0].update(
        type="GROUP",
        participants=["student-demo-1", "student-demo-2", "student-demo-3"],
    )
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_online_group_capacity_separate_and_remote_no_space():
    data = small()
    data["units"][0].update(
        type="GROUP",
        participants=["student-demo-1", "student-demo-2", "student-demo-3"],
        allowed_modes=["ONLINE"],
        online_capacity=3,
    )
    result = simulate(data)
    assert result["is_complete"]
    assert (
        result["assignments"][0]["space_id"] is None
        and result["assignments"][0]["location"] == "REMOTE"
    )
    data["units"][0]["online_capacity"] = None
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_four_simultaneous_lessons_cannot_use_three_spaces():
    data = small(4)
    data["resources"] = demo_input()["resources"]
    template = data["tutors"][0]
    data["tutors"] = [{**deepcopy(template), "id": f"tutor-{i}"} for i in range(4)]
    for u in data["units"]:
        u["allowed_tutors"] = [t["id"] for t in data["tutors"]]
    assert simulate(data)["solver_status"] == "INFEASIBLE"
    data["mode"] = "COVERAGE"
    for u in data["units"]:
        u["mandatory"] = False
    result = simulate(data)
    assert (
        result["solver_status"] == "OPTIMAL"
        and len(result["assignments"]) == 3
        and len(result["unassigned"]) == 1
    )


def test_same_tutor_collision_across_modalities():
    data = small(2)
    data["units"][1]["allowed_modes"] = ["ONLINE"]
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_same_student_collision_across_groups_and_tutors():
    data = small(2)
    data["resources"] = demo_input()["resources"]
    for u in data["units"]:
        u["participants"] = ["student-demo-1"]
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_closure_overrides_service():
    data = small()
    data["closures"] = [
        {"mode": "IN_PERSON", "resource_id": None, "start": 480, "end": 540}
    ]
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_resource_specific_closure():
    data = small()
    data["closures"] = [
        {"mode": "ALL", "resource_id": "space-demo-1", "start": 480, "end": 540}
    ]
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_mode_specific_closure_does_not_close_online():
    data = small()
    data["units"][0]["allowed_modes"] = ["ONLINE"]
    data["closures"] = [
        {"mode": "IN_PERSON", "resource_id": None, "start": 480, "end": 540}
    ]
    assert simulate(data)["is_complete"]


def sequential(n=2):
    data = small(n)
    for i, u in enumerate(data["units"]):
        u["earliest_start"] = 480 + i * 60
        u["latest_end"] = 540 + i * 60
    return data


def test_adjacent_lessons_zero_pause_allowed_and_pause_enforced():
    data = sequential()
    assert simulate(data)["is_complete"]
    data["tutors"][0]["pause_minutes"] = 15
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_cleanup_buffer_occupies_space():
    data = sequential()
    for u in data["units"]:
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    data["resources"][0]["buffer_minutes"] = 15
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_transition_not_instant_and_pause_not_double_counted():
    data = sequential()
    data["units"][1]["allowed_modes"] = ["ONLINE"]
    assert simulate(data)["solver_status"] == "INFEASIBLE"
    data["units"][1].update(earliest_start=570, latest_end=630)
    data["tutors"][0]["pause_minutes"] = 15
    result = simulate(data)
    assert result["is_complete"] and result["validation"]["status"] == "PASSED"


def test_daily_load_in_minutes():
    data = sequential(3)
    data["tutors"][0]["daily_limit_minutes"] = 120
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_weekly_load_in_minutes():
    data = sequential(3)
    data["tutors"][0]["weekly_limit_minutes"] = 120
    assert simulate(data)["solver_status"] == "INFEASIBLE"


def test_online_tutor_in_center_requires_configured_space():
    data = small()
    data["units"][0]["allowed_modes"] = ["ONLINE"]
    for t in data["tutors"]:
        for w in t["availability"]:
            if w["mode"] == "ONLINE":
                w["location"] = "ON_SITE"
    for w in data["service_windows"]:
        if w["mode"] == "ONLINE":
            w["location"] = "ON_SITE"
    result = simulate(data)
    assert (
        result["is_complete"] and result["assignments"][0]["space_id"] == "space-demo-1"
    )
    data["online_onsite_requires_space"] = False
    assert simulate(data)["assignments"][0]["space_id"] is None


def test_exclusive_video_channels_parallelism():
    data = small(2)
    for u in data["units"]:
        u["allowed_modes"] = ["ONLINE"]
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    data["video_channels_required"] = True
    channel = {
        "id": "video-1",
        "kind": "VIDEO_CHANNEL",
        "student_capacity": None,
        "buffer_minutes": 0,
        "availability": [{"start": 480, "end": 840}],
    }
    data["resources"].append(channel)
    assert simulate(data)["solver_status"] == "INFEASIBLE"
    data["resources"].append({**deepcopy(channel), "id": "video-2"})
    assert simulate(data)["is_complete"]


def test_lexicographic_priority_above_lower_beneficiary_count():
    data = small(2)
    data["mode"] = "COVERAGE"
    for u in data["units"]:
        u["mandatory"] = False
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    data["units"][0]["priority"] = "P0"
    data["units"][1].update(
        type="GROUP", participants=["student-demo-2", "student-demo-3"], priority="P1"
    )
    result = simulate(data)
    assert [a["demand_key"] for a in result["assignments"]] == ["unit-1"]
    assert result["objective_values"]["P1"] == 120


def test_same_priority_counts_minutes_per_beneficiary():
    data = small(2)
    data["mode"] = "COVERAGE"
    for u in data["units"]:
        u["mandatory"] = False
        u["allowed_tutors"] = ["tutor-demo-1", "tutor-demo-2"]
    data["units"][1].update(
        type="GROUP", participants=["student-demo-2", "student-demo-3"]
    )
    assert [a["demand_key"] for a in simulate(data)["assignments"]] == ["unit-2"]


def test_mandatory_cannot_be_dropped_for_higher_priority_optional():
    data = small(2)
    data["mode"] = "COVERAGE"
    data["units"][0].update(priority="P0", mandatory=False)
    data["units"][1]["priority"] = "P2"
    result = simulate(data)
    assert [a["demand_key"] for a in result["assignments"]] == ["unit-2"]


def test_locked_assignment_preserved_even_if_optional():
    data = small()
    data["mode"] = "COVERAGE"
    data["units"][0]["mandatory"] = False
    data["units"][0]["locked_assignment"] = assignment(data)
    assert simulate(data)["assignments"] == [assignment(data)]


def test_illegal_lock_blocks_before_solving():
    data = small()
    data["units"][0]["locked_assignment"] = assignment(data, start=470, end=530)
    result = simulate(data)
    assert result["solver_status"] == "BLOCKED"
    assert result["diagnostics"][0]["code"] == "LOCKED_ILLEGAL"


def test_conflicting_locks_not_silently_moved():
    data = small(2)
    for i, u in enumerate(data["units"]):
        u["locked_assignment"] = assignment(data, i)
    result = simulate(data)
    assert (
        result["solver_status"] == "BLOCKED"
        and result["diagnostics"][0]["code"] == "LOCKED_CONFLICT"
    )


def test_unknown_is_not_infeasible(monkeypatch):
    monkeypatch.setattr(
        cp_model.CpSolver, "solve", lambda self, model: cp_model.UNKNOWN
    )
    result = simulate(small())
    assert (
        result["solver_status"] == "UNKNOWN"
        and result["validation"]["status"] == "NOT_RUN"
    )


def test_invalid_model_is_technical_failure(monkeypatch):
    monkeypatch.setattr(cp_model.CpModel, "validate", lambda self: "test-model-invalid")
    assert simulate(small())["solver_status"] == "MODEL_INVALID"


def test_candidate_limit_blocks_without_false_impossibility(monkeypatch):
    import apps.scheduling.candidates as candidates

    monkeypatch.setattr(candidates, "MAX_CANDIDATES", 1)
    result = simulate(demo_input())
    assert (
        result["solver_status"] == "BLOCKED"
        and result["diagnostics"][0]["code"] == "CANDIDATE_LIMIT"
    )


def test_independent_validator_detects_malformed_duration():
    data = small()
    bad = assignment(data, end=550)
    assert any(
        v["code"] == "DURATION_OR_WINDOW"
        for v in validate_assignments(data, [bad])["violations"]
    )


def test_independent_validator_checks_skill_from_raw_snapshot():
    data = small()
    good = simulate(data)["assignments"]
    data["tutors"][0]["skills"] = []
    assert any(
        v["code"] == "UNQUALIFIED_TUTOR"
        for v in validate_assignments(data, good)["violations"]
    )


def test_independent_validator_detects_overlap_and_missing_mandatory():
    data = small(2)
    result = validate_assignments(data, [assignment(data, 0), assignment(data, 1)])
    assert any(v["code"] == "RESOURCE_OVERLAP" for v in result["violations"])
    assert validate_assignments(data, [])["status"] == "FAILED"


@pytest.mark.parametrize(
    "changed",
    [{"start": 10**30}, {"space_id": []}, {"demand_key": {}}, {"start": True}],
)
def test_validator_handles_malformed_result_without_crashing(changed):
    data = small()
    a = assignment(data)
    a.update(changed)
    assert validate_assignments(data, [a])["status"] == "FAILED"


def test_validation_failure_discards_solver_output(monkeypatch):
    import apps.scheduling.solver as solver

    def validate(data, assignments, require_coverage=True):
        return {"status": "FAILED" if require_coverage else "PASSED", "violations": []}

    monkeypatch.setattr(solver, "validate_assignments", validate)
    result = solver.simulate(small())
    assert (
        result["solver_status"] == "VALIDATION_FAILED" and result["assignments"] == []
    )


def test_nonfinite_budget_rejected():
    data = small()
    data["budget_seconds"] = float("nan")
    with pytest.raises(InputError):
        simulate(data)


def test_feasible_level_stops_without_claiming_lower_optimality(monkeypatch):
    original = cp_model.CpSolver.solve
    calls = []

    def feasible(self, model):
        code = original(self, model)
        assert code == cp_model.OPTIMAL
        calls.append(code)
        return cp_model.FEASIBLE

    monkeypatch.setattr(cp_model.CpSolver, "solve", feasible)
    result = simulate(small())
    assert result["solver_status"] == "FEASIBLE" and result["is_complete"]
    assert result["optimality_proven_levels"] == [] and len(calls) == 1


def test_budget_expires_after_proven_level_keeps_valid_incumbent(monkeypatch):
    import apps.scheduling.solver as solver

    # Fake clock: time jumps past the budget as soon as the first level is solved.
    clock = {"now": 0.0}
    original = cp_model.CpSolver.solve

    def solve(self, model):
        code = original(self, model)
        clock["now"] = 100.0
        return code

    monkeypatch.setattr(cp_model.CpSolver, "solve", solve)
    monkeypatch.setattr(solver, "monotonic", lambda: clock["now"])
    result = solver.simulate(small())
    assert result["solver_status"] == "FEASIBLE" and result[
        "optimality_proven_levels"
    ] == ["P0"]
    assert result["validation"]["status"] == "PASSED" and result["is_complete"]
