"""Synthetic T34 benchmark fixture: 10 tutors, 80 students in 50 families, three
spaces, 120 sessions per week over six local weeks = 720 demand units.

Entirely synthetic and deterministic (seeded).  Not real students, schools or
availability; not an importer.  The six weeks start on 2026-10-05 and include
the end of DST (2026-10-25), so the horizon is 42 days + 60 minutes.
"""

from datetime import date, datetime, time, timedelta, timezone
import random
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Rome")
SUBJECTS = ["math", "italian", "english", "science", "physics"]
LEVELS = ["MEDIE", "SUPERIORI"]
FIRST_MONDAY = date(2026, 10, 5)


def _minute(epoch, day, clock):
    local = datetime.combine(day, clock).replace(tzinfo=ZONE)
    return int((local.astimezone(timezone.utc) - epoch).total_seconds() // 60)


def benchmark_input(weeks=6, seed=20261005, sessions_per_week=120, budget=30.0):
    rng = random.Random(seed)
    epoch = (
        datetime.combine(FIRST_MONDAY, time.min)
        .replace(tzinfo=ZONE)
        .astimezone(timezone.utc)
    )
    end = (
        datetime.combine(FIRST_MONDAY + timedelta(days=7 * weeks), time.min)
        .replace(tzinfo=ZONE)
        .astimezone(timezone.utc)
    )
    horizon = int((end - epoch).total_seconds() // 60)
    days = [FIRST_MONDAY + timedelta(days=i) for i in range(7 * weeks)]

    def span(day, a, b):
        return _minute(epoch, day, time(*a)), _minute(epoch, day, time(*b))

    service = []
    for day in days:
        if day.weekday() < 5:
            s, e = span(day, (14, 0), (20, 0))
            service += [
                {"mode": "IN_PERSON", "location": "ON_SITE", "start": s, "end": e},
                {"mode": "ONLINE", "location": "ON_SITE", "start": s, "end": e},
            ]
            s2, e2 = span(day, (14, 0), (21, 0))
            service.append(
                {"mode": "ONLINE", "location": "REMOTE", "start": s2, "end": e2}
            )
        elif day.weekday() == 5:
            s, e = span(day, (9, 0), (13, 0))
            service += [
                {"mode": "IN_PERSON", "location": "ON_SITE", "start": s, "end": e},
                {"mode": "ONLINE", "location": "ON_SITE", "start": s, "end": e},
            ]
    tutors = []
    teaches = {}
    for n in range(10):
        tid = f"bench-tutor-{n + 1:02d}"
        subjects = [SUBJECTS[n % 5], SUBJECTS[(n + 2) % 5]]
        teaches[tid] = subjects
        availability = []
        remote_days = {n % 5, (n + 3) % 5}
        for day in days:
            if day.weekday() < 5:
                s, e = span(day, (14, 0), (20, 0))
                availability.append(
                    {"mode": "IN_PERSON", "location": "ON_SITE", "start": s, "end": e}
                )
                if day.weekday() in remote_days:
                    s2, e2 = span(day, (14, 0), (21, 0))
                    availability.append(
                        {"mode": "ONLINE", "location": "REMOTE", "start": s2, "end": e2}
                    )
                else:
                    availability.append(
                        {"mode": "ONLINE", "location": "ON_SITE", "start": s, "end": e}
                    )
            elif day.weekday() == 5 and n % 2 == 0:
                s, e = span(day, (9, 0), (13, 0))
                availability.append(
                    {"mode": "IN_PERSON", "location": "ON_SITE", "start": s, "end": e}
                )
        tutors.append(
            {
                "id": tid,
                "availability_state": "APPROVED",
                "availability": availability,
                "skills": [
                    {
                        "subject": sub,
                        "level": lvl,
                        "mode": mode,
                        "start": 0,
                        "end": horizon,
                    }
                    for sub in subjects
                    for lvl in LEVELS
                    for mode in ("IN_PERSON", "ONLINE")
                ],
                "daily_limit_minutes": 300,
                "weekly_limit_minutes": 1200,
                "pause_minutes": 0 if n % 3 else 15,
                "transition_minutes": {
                    "ON_SITE": {"ON_SITE": 0, "REMOTE": 30},
                    "REMOTE": {"ON_SITE": 30, "REMOTE": 0},
                },
            }
        )
    # 50 families: 20 with one child, 30 with two -> 80 students.
    families = []
    sid = 0
    for f in range(50):
        size = 1 if f < 20 else 2
        families.append([f"bench-student-{sid + i + 1:02d}" for i in range(size)])
        sid += size
    students = []
    student_days = {}
    for family in families:
        family_days = sorted(rng.sample(range(5), 3))
        for s_id in family:
            student_days[s_id] = family_days
            windows = []
            onsite_online = rng.random() < 0.15
            for day in days:
                if day.weekday() in family_days:
                    s, e = span(day, (15, 0), (19, 0))
                    windows.append({"mode": "IN_PERSON", "start": s, "end": e})
                    windows.append(
                        {"mode": "ONLINE", "location": "REMOTE", "start": s, "end": e}
                    )
                    if onsite_online:
                        windows.append(
                            {
                                "mode": "ONLINE",
                                "location": "ON_SITE",
                                "start": s,
                                "end": e,
                            }
                        )
            students.append(
                {"id": s_id, "availability_state": "APPROVED", "availability": windows}
            )
    all_students = [s for family in families for s in family]
    level_of = {s: LEVELS[i % 2] for i, s in enumerate(all_students)}
    # Weekly requests: 20 pairs (group lessons) + 100 individual sessions.
    pairs = []
    pool = [s for s in all_students]
    for i in range(20):
        a, b = pool[2 * i], pool[2 * i + 41]
        pairs.append((a, b))
    requests = []
    for i, (a, b) in enumerate(pairs):
        requests.append(("GROUP", [a, b], SUBJECTS[i % 5], level_of[a], 60))
    for i, s in enumerate(all_students):
        sessions = 2 if i < 20 else 1
        for k in range(sessions):
            requests.append(
                (
                    "INDIVIDUAL",
                    [s],
                    SUBJECTS[(i + k * 2) % 5],
                    level_of[s],
                    90 if i % 7 == 0 else 60,
                )
            )
    requests = requests[:sessions_per_week]
    for i, (_, participants, _, _, _) in enumerate(requests):
        if any(level_of[p] != level_of[participants[0]] for p in participants):
            # Pairs share a level; adjust synthetically.
            level_of[participants[1]] = level_of[participants[0]]
    units, series = [], []
    for r, (kind, participants, subject, level, duration) in enumerate(requests):
        priority = "P0" if r % 5 == 0 else ("P1" if r % 5 in (1, 2) else "P2")
        modes = (
            ["IN_PERSON"]
            if r % 10 < 6
            else (["ONLINE"] if r % 10 < 8 else ["IN_PERSON", "ONLINE"])
        )
        if kind == "GROUP":
            modes = ["IN_PERSON"]
        allowed = sorted(t for t, subs in teaches.items() if subject in subs)
        keys = []
        for w in range(weeks):
            monday = FIRST_MONDAY + timedelta(days=7 * w)
            key = f"bench/req-{r + 1:03d}/w{w + 1}"
            keys.append(key)
            units.append(
                {
                    "demand_key": key,
                    "type": kind,
                    "subject": subject,
                    "level": level,
                    "participants": list(participants),
                    "duration_minutes": duration,
                    "priority": priority,
                    "mandatory": priority == "P0",
                    "allowed_modes": modes,
                    "allowed_tutors": allowed,
                    "online_capacity": 2 if kind == "GROUP" else None,
                    "earliest_start": _minute(epoch, monday, time.min),
                    "latest_end": _minute(epoch, monday + timedelta(days=7), time.min),
                    "locked_assignment": None,
                }
            )
        series.append(
            {
                "series_key": f"bench/series-{r + 1:03d}",
                "units": keys,
                "stability": "PREFERRED",
                "preferred_slot": None,
            }
        )
    family_constraints = []
    for f, family in enumerate(families[20:30]):
        # Siblings at the same lesson start in the first week (synchronisation).
        keys = []
        for s_id in family:
            for r, (kind, participants, *_rest) in enumerate(requests):
                if kind == "INDIVIDUAL" and participants == [s_id]:
                    keys.append(f"bench/req-{r + 1:03d}/w1")
                    break
        if len(keys) == 2:
            family_constraints.append(
                {
                    "constraint_id": f"bench/family-{f + 1:02d}",
                    "kind": "SAME_DAY",
                    "units": keys,
                }
            )
    preferences = [
        {
            "subject_kind": "STUDENT",
            "subject_id": s_id,
            "windows": [
                {"start": a, "end": b}
                for day in days
                if day.weekday() in student_days[s_id]
                for a, b in [span(day, (15, 0), (17, 0))]
            ],
            "weight": 1,
        }
        for s_id in all_students[:30]
    ]
    return {
        "schema_version": "0.5",
        "policy_version": "BENCHMARK-SYNTHETIC-NOT-APPROVED",
        "epoch": epoch.isoformat().replace("+00:00", "Z"),
        "timezone": "Europe/Rome",
        "horizon_days": 7 * weeks,
        "horizon_minutes": horizon,
        "grid_minutes": 15,
        "duration_catalog": [60, 90, 120],
        "mode": "COVERAGE",
        "budget_seconds": budget,
        "online_onsite_requires_space": True,
        "video_channels_required": False,
        "allow_cross_local_midnight": False,
        "student_buffer_minutes": 0,
        "objective_order": ["P0", "P1", "P2", "F", "C", "R", "P", "G"],
        "unsupported_constraints": [],
        "fairness_policy": default_fairness_policy(),
        "students": students,
        "tutors": tutors,
        "resources": [
            {
                "id": f"bench-space-{n}",
                "kind": "SPACE",
                "student_capacity": 2,
                "buffer_minutes": 0,
                "availability": [
                    {"start": w["start"], "end": w["end"]}
                    for w in service
                    if w["mode"] == "IN_PERSON"
                ],
            }
            for n in (1, 2, 3)
        ],
        "service_windows": service,
        "closures": [],
        "units": units,
        "series": series,
        "family_constraints": family_constraints,
        "preferences": preferences,
    }


def default_fairness_policy():
    from .policies import fairness_policy

    return fairness_policy()
