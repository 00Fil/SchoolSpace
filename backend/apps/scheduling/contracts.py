"""Closed, bounded DTO validation for a synthetic simulation, not a database snapshot.

Two contract versions are accepted:
- ``0.4``: historical one-week baseline (only P0/P1/P2, no new fields);
- ``0.5``: up to six local weeks, full lexicographic vector, H11/H12, local
  replanning, student buffer, students online from the centre and optional
  lessons across local midnight.  Every new feature is explicit and opt-in.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import math
import json
from jsonschema import Draft202012Validator, FormatChecker, validators

SCHEMA = json.loads(
    (Path(__file__).parent / "schemas/planning-input.schema.json").read_text()
)
Checker = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda checker, value: type(value) is int
)
Validator = validators.extend(Draft202012Validator, type_checker=Checker)


class InputError(ValueError):
    def __init__(self, code, message, fields=None):
        self.code, self.message, self.fields = code, message, fields or []
        super().__init__(message)


def parse_input(value):
    errors = list(Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        # Do not echo payload values, IDs or private content in errors.
        raise InputError(
            "INVALID_INPUT",
            "DTO non valido: correggere struttura, tipi o campi",
            ["/" + "/".join(map(str, e.absolute_path)) for e in errors[:20]],
        )
    data = deepcopy(value)
    if not math.isfinite(data["budget_seconds"]):
        raise InputError("INVALID_BUDGET", "Budget numerico finito richiesto")
    try:
        epoch = datetime.fromisoformat(data["epoch"].replace("Z", "+00:00"))
    except ValueError:
        raise InputError("INVALID_EPOCH", "Epoca ISO 8601 non valida")
    if epoch.utcoffset() is None or epoch.utcoffset().total_seconds() != 0:
        raise InputError(
            "UTC_EPOCH_REQUIRED",
            "L'epoca deve essere un istante UTC con offset esplicito",
        )
    if epoch.minute % data["grid_minutes"]:
        raise InputError(
            "EPOCH_GRID_ALIGNMENT", "Epoca UTC non allineata alla griglia dichiarata"
        )
    if epoch.second or epoch.microsecond:
        raise InputError(
            "MINUTE_PRECISION_REQUIRED", "L'epoca deve avere precisione al minuto"
        )
    maximum = data["horizon_minutes"]
    if abs(maximum - data["horizon_days"] * 1440) > 60:
        raise InputError(
            "INVALID_HORIZON", "Orizzonte incoerente con il numero di giorni locali"
        )
    collections = [data["students"], data["tutors"], data["resources"]]
    for items in collections:
        if len({item["id"] for item in items}) != len(items):
            raise InputError(
                "DUPLICATE_ID", "Identificatori duplicati nello stesso tipo di risorsa"
            )
    if len({u["demand_key"] for u in data["units"]}) != len(data["units"]):
        raise InputError("DUPLICATE_DEMAND", "Unità canoniche duplicate")
    students = {s["id"] for s in data["students"]}
    tutors = {t["id"] for t in data["tutors"]}
    resources = {r["id"] for r in data["resources"]}
    for items in collections + [data["service_windows"], data["closures"]]:
        for item in items:
            windows = (
                item.get("availability", []) + item.get("skills", [])
                if "id" in item
                else [item]
            )
            for w in windows:
                if w["start"] >= w["end"] or w["end"] > maximum:
                    raise InputError(
                        "INVALID_INTERVAL", "Finestre non positive o oltre l'orizzonte"
                    )
                if (
                    w.get("mode") == "IN_PERSON"
                    and w.get("location", "ON_SITE") != "ON_SITE"
                ):
                    raise InputError("INVALID_LOCATION", "La presenza richiede la sede")
            if (
                "availability_state" in item
                and item["availability_state"] == "DECLARED_NONE"
                and item["availability"]
            ):
                raise InputError(
                    "CONTRADICTORY_AVAILABILITY",
                    "DECLARED_NONE richiede finestre vuote",
                )
    for tutor in data["tutors"]:
        if any(
            tutor["transition_minutes"][location][location] != 0
            for location in ("ON_SITE", "REMOTE")
        ):
            raise InputError(
                "DIAGONAL_TRANSITION",
                "Transizione stessa localizzazione non supportata: usare la pausa esplicita",
            )
    for resource in data["resources"]:
        if resource["kind"] == "SPACE" and resource["student_capacity"] != 2:
            raise InputError(
                "BASELINE_CAPACITY", "Lo spazio della baseline ha capienza due"
            )
        if resource["kind"] == "VIDEO_CHANNEL" and (
            resource["student_capacity"] is not None or resource["buffer_minutes"] != 0
        ):
            raise InputError(
                "VIDEO_RESOURCE_INVALID",
                "Canale video esclusivo: nessuna capienza-studente o buffer implicito",
            )
    if sum(r["kind"] == "SPACE" for r in data["resources"]) > 3:
        raise InputError("BASELINE_SPACES", "La baseline non ammette più di tre spazi")
    for closure in data["closures"]:
        if closure["resource_id"] and closure["resource_id"] not in resources:
            raise InputError("UNKNOWN_RESOURCE", "Chiusura su risorsa inesistente")
    for u in data["units"]:
        if (
            not set(u["participants"]) <= students
            or not set(u["allowed_tutors"]) <= tutors
        ):
            raise InputError(
                "UNKNOWN_PARTICIPANT", "Partecipante o tutor non presente nel DTO"
            )
        if (
            u["duration_minutes"] not in data["duration_catalog"]
            or u["duration_minutes"] % data["grid_minutes"]
        ):
            raise InputError(
                "DURATION_OUTSIDE_CATALOG", "Durata fuori catalogo o griglia"
            )
        if u["earliest_start"] >= u["latest_end"] or u["latest_end"] > maximum:
            raise InputError("INVALID_DEMAND_PERIOD", "Periodo dell'unità non valido")
        if (u["type"] == "INDIVIDUAL" and len(u["participants"]) != 1) or (
            u["type"] == "GROUP" and len(u["participants"]) < 2
        ):
            raise InputError(
                "INVALID_GROUP", "Individuale: un partecipante; gruppo: almeno due"
            )
        if (
            u["locked_assignment"]
            and u["locked_assignment"]["demand_key"] != u["demand_key"]
        ):
            raise InputError(
                "LOCKED_KEY_MISMATCH",
                "L'appuntamento bloccato deve riferire l'unità corretta",
            )
    check_version_features(data)
    if data["schema_version"] == "0.5":
        check_v05(data)
    return data


V04_ONLY_ABSENT = (
    "limits",
    "search_workers",
    "fairness_policy",
    "series",
    "family_constraints",
    "sequences",
    "enrollments",
    "preferences",
    "replanning",
)
FULL_VECTOR = ["P0", "P1", "P2", "F", "C", "R", "P", "G"]
# Historical prototype caps (v0.4) and benchmark-reviewed defaults (v0.5, T34).
DEFAULT_LIMITS = {
    "0.4": {
        "max_units": 40,
        "max_tutors": 10,
        "max_students": 120,
        "max_candidates": 3000,
    },
    "0.5": {
        "max_units": 720,
        "max_tutors": 10,
        "max_students": 120,
        "max_candidates": 150000,
    },
}
ASSIGNMENT_BASE_FIELDS = frozenset(
    {
        "demand_key",
        "tutor_id",
        "mode",
        "location",
        "space_id",
        "video_id",
        "start",
        "end",
    }
)
ASSIGNMENT_STUDENT_FIELDS = frozenset({"student_location", "student_space_id"})


def effective_limits(data):
    return data.get("limits") or DEFAULT_LIMITS[data["schema_version"]]


def check_version_features(data):
    if data["schema_version"] != "0.4":
        return
    if any(key in data for key in V04_ONLY_ABSENT):
        raise InputError(
            "VERSION_FEATURE", "Campi v0.5 non ammessi in un DTO 0.4", ["/"]
        )
    if (
        data["horizon_days"] > 7
        or data["horizon_minutes"] > 10140
        or data["budget_seconds"] > 10
        or data["objective_order"] != ["P0", "P1", "P2"]
        or data["allow_cross_local_midnight"] is not False
        or data["student_buffer_minutes"] != 0
        or len(data["units"]) > 40
        or len(data["tutors"]) > 10
    ):
        raise InputError(
            "VERSION_FEATURE",
            "Il contratto 0.4 resta limitato a una settimana e a P0/P1/P2",
        )
    for student in data["students"]:
        if any("location" in w for w in student["availability"]):
            raise InputError("VERSION_FEATURE", "Localizzazione studente solo in 0.5")
    for unit in data["units"]:
        lock = unit["locked_assignment"]
        if "previous_assignment" in unit or "preferred_tutors" in unit or (
            lock and set(lock) & ASSIGNMENT_STUDENT_FIELDS
        ):
            raise InputError("VERSION_FEATURE", "Campi assegnazione v0.5 in DTO 0.4")


def check_assignment_shape(data, a):
    student_fields = set(a) & ASSIGNMENT_STUDENT_FIELDS
    if student_fields and student_fields != ASSIGNMENT_STUDENT_FIELDS:
        raise InputError(
            "ASSIGNMENT_SHAPE", "student_location e student_space_id vanno insieme"
        )


def check_v05(data):
    order = data["objective_order"]
    if [term for term in order if term in ("P0", "P1", "P2")] != ["P0", "P1", "P2"]:
        raise InputError(
            "OBJECTIVE_ORDER",
            "P0, P1 e P2 sono obbligatori e in quest'ordine; gli altri termini sono opzionali",
        )
    if "F" in order and "fairness_policy" not in data:
        raise InputError(
            "FAIRNESS_POLICY_REQUIRED",
            "Il termine F richiede una policy di equità versionata (D03)",
        )
    limits = effective_limits(data)
    if (
        len(data["units"]) > limits["max_units"]
        or len(data["tutors"]) > limits["max_tutors"]
        or len(data["students"]) > limits["max_students"]
    ):
        raise InputError(
            "SIZE_LIMIT",
            "DTO oltre i limiti configurati: nessuna domanda troncata",
        )
    if data["horizon_minutes"] > data["horizon_days"] * 1440 + 60:
        raise InputError("INVALID_HORIZON", "Orizzonte oltre i giorni dichiarati")
    units = {u["demand_key"]: u for u in data["units"]}
    students = {s["id"] for s in data["students"]}
    tutors = {t["id"] for t in data["tutors"]}
    for student in data["students"]:
        for w in student["availability"]:
            if w.get("location") == "REMOTE" and w["mode"] == "IN_PERSON":
                raise InputError("INVALID_LOCATION", "La presenza richiede la sede")
    for unit in data["units"]:
        if not set(unit.get("preferred_tutors", [])) <= set(unit["allowed_tutors"]):
            raise InputError(
                "PREFERRED_TUTOR_NOT_ALLOWED",
                "Il tutor preferito deve essere tra quelli ammessi per l'unità",
            )
        for field in ("locked_assignment", "previous_assignment"):
            if unit.get(field):
                check_assignment_shape(data, unit[field])
                if unit[field]["demand_key"] != unit["demand_key"]:
                    raise InputError(
                        "LOCKED_KEY_MISMATCH",
                        "L'assegnazione deve riferire l'unità corretta",
                    )
        if unit.get("previous_assignment") and unit["locked_assignment"]:
            raise InputError(
                "LOCK_AND_PREVIOUS",
                "Un'unità bloccata non può essere contemporaneamente sbloccata",
            )

    def known(keys, where):
        if not set(keys) <= set(units):
            raise InputError("UNKNOWN_UNIT", f"Unità inesistente in {where}")

    seen_series = set()
    for series in data.get("series", []):
        known(series["units"], "series")
        if set(series["units"]) & seen_series:
            raise InputError("SERIES_OVERLAP", "Un'unità appartiene a una sola serie")
        seen_series |= set(series["units"])
        if series["stability"] == "REQUIRED" and series["preferred_slot"] is None:
            pass  # Same slot for every date, chosen by the solver.
    ids = set()
    for item in data.get("family_constraints", []):
        known(item["units"], "family_constraints")
        if item["constraint_id"] in ids:
            raise InputError("DUPLICATE_CONSTRAINT", "Identificatore vincolo duplicato")
        ids.add(item["constraint_id"])
        if (
            item["kind"] == "SAME_INTERVAL"
            and len({units[k]["duration_minutes"] for k in item["units"]}) != 1
        ):
            raise InputError(
                "SYNC_DURATION",
                "SAME_INTERVAL richiede la stessa durata: usare SAME_START",
            )
        if item["kind"] in ("SAME_START", "SAME_INTERVAL") and any(
            set(units[a]["participants"]) & set(units[b]["participants"])
            for a in item["units"]
            for b in item["units"]
            if a < b
        ):
            raise InputError(
                "SYNC_SAME_STUDENT",
                "Una sincronizzazione non può riguardare lo stesso studente due volte",
            )
    for item in data.get("sequences", []):
        known(item["units"], "sequences")
        if item["sequence_id"] in ids:
            raise InputError("DUPLICATE_CONSTRAINT", "Identificatore vincolo duplicato")
        ids.add(item["sequence_id"])
        if (
            item["max_gap_minutes"] is not None
            and item["max_gap_minutes"] < item["min_gap_minutes"]
        ):
            raise InputError("SEQUENCE_GAP", "Intervallo di sequenza non valido")
    enrolled = set()
    for item in data.get("enrollments", []):
        if item["student_id"] not in students or item["student_id"] in enrolled:
            raise InputError("UNKNOWN_PARTICIPANT", "Iscrizione non valida o duplicata")
        enrolled.add(item["student_id"])
        for w in item["periods"]:
            if w["start"] >= w["end"] or w["end"] > data["horizon_minutes"]:
                raise InputError("INVALID_INTERVAL", "Periodo di iscrizione non valido")
    for item in data.get("preferences", []):
        pool = students if item["subject_kind"] == "STUDENT" else tutors
        if item["subject_id"] not in pool:
            raise InputError(
                "UNKNOWN_PARTICIPANT", "Preferenza su soggetto inesistente"
            )
        for w in item["windows"]:
            if w["start"] >= w["end"] or w["end"] > data["horizon_minutes"]:
                raise InputError(
                    "INVALID_INTERVAL", "Finestra di preferenza non valida"
                )
    previous = {k for k, u in units.items() if u.get("previous_assignment")}
    replanning = data.get("replanning")
    if replanning:
        unlocked = [item["demand_key"] for item in replanning["unlocked"]]
        known(unlocked, "replanning")
        if len(set(unlocked)) != len(unlocked) or set(unlocked) != previous:
            raise InputError(
                "UNLOCK_AUTHORIZATION",
                "Ogni appuntamento sbloccato richiede un'autorizzazione e un'assegnazione precedente",
            )
        known(replanning["expansion_candidates"], "replanning")
        if any(
            not units[k]["locked_assignment"]
            for k in replanning["expansion_candidates"]
        ):
            raise InputError(
                "EXPANSION_CANDIDATE",
                "L'allargamento dell'ambito può riguardare solo appuntamenti oggi bloccati",
            )
    elif previous:
        raise InputError(
            "UNLOCK_AUTHORIZATION",
            "Assegnazioni precedenti ammesse solo con sblocco autorizzato",
        )


def input_hash(data):
    return hashlib.sha256(
        json.dumps(
            data, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def utc_epoch(data):
    return datetime.fromisoformat(data["epoch"].replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
