from pathlib import Path
import json
from jsonschema import Draft202012Validator
from apps.scheduling.contracts import SCHEMA, parse_input
from apps.scheduling.fixtures import demo_input
from apps.scheduling.solver import simulate

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_input_schema_matches_documented_fixture():
    contract = json.loads((ROOT / "contracts/planning-input.schema.json").read_text())
    fixture = json.loads((ROOT / "contracts/fixtures/planning-demo.json").read_text())
    assert contract == SCHEMA
    assert parse_input(fixture) == demo_input()


def test_output_fixture_and_live_solver_match_result_contract():
    schema = json.loads((ROOT / "contracts/planning-result.schema.json").read_text())
    validator = Draft202012Validator(schema)
    fixture = json.loads(
        (ROOT / "contracts/fixtures/planning-demo-result.json").read_text()
    )
    validator.validate(fixture)
    validator.validate(simulate(demo_input()))
