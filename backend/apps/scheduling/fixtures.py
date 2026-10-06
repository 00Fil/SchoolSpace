"""A small synthetic week, not actual students, availability or school hours."""

from copy import deepcopy


def demo_input():
    windows = [
        {"mode": "IN_PERSON", "location": "ON_SITE", "start": 480, "end": 840},
        {"mode": "ONLINE", "location": "REMOTE", "start": 480, "end": 840},
    ]
    tutors = []
    for n in (1, 2):
        tutors.append(
            {
                "id": f"tutor-demo-{n}",
                "availability_state": "APPROVED",
                "availability": deepcopy(windows),
                "skills": [
                    {
                        "subject": subject,
                        "level": "DEMO",
                        "mode": mode,
                        "start": 0,
                        "end": 10080,
                    }
                    for subject in ("math-demo", "science-demo")
                    for mode in ("IN_PERSON", "ONLINE")
                ],
                "daily_limit_minutes": 300,
                "weekly_limit_minutes": 600,
                "pause_minutes": 0,
                "transition_minutes": {
                    "ON_SITE": {"ON_SITE": 0, "REMOTE": 30},
                    "REMOTE": {"ON_SITE": 30, "REMOTE": 0},
                },
            }
        )
    students = [
        {
            "id": f"student-demo-{n}",
            "availability_state": "APPROVED",
            "availability": [
                {"mode": mode, "start": 480, "end": 840}
                for mode in ("IN_PERSON", "ONLINE")
            ],
        }
        for n in range(1, 5)
    ]
    units = []
    for subject in ("math-demo", "science-demo"):
        for pair in (0, 1):
            for serial in range(1, 3 if subject == "math-demo" else 2):
                units.append(
                    {
                        "demand_key": f"{subject}/week-2026-10-05/group-{pair + 1}/{serial}",
                        "type": "GROUP",
                        "subject": subject,
                        "level": "DEMO",
                        "participants": [
                            f"student-demo-{pair * 2 + 1}",
                            f"student-demo-{pair * 2 + 2}",
                        ],
                        "duration_minutes": 60,
                        "priority": "P1",
                        "mandatory": True,
                        "allowed_modes": ["IN_PERSON"],
                        "allowed_tutors": ["tutor-demo-1", "tutor-demo-2"],
                        "online_capacity": None,
                        "earliest_start": 480,
                        "latest_end": 840,
                        "locked_assignment": None,
                    }
                )
    return {
        "schema_version": "0.4",
        "policy_version": "SYNTHETIC-NOT-APPROVED",
        "epoch": "2026-10-05T00:00:00Z",
        "timezone": "Europe/Rome",
        "horizon_days": 7,
        "horizon_minutes": 10080,
        "grid_minutes": 15,
        "duration_catalog": [60, 90, 120],
        "mode": "STRICT",
        "budget_seconds": 3,
        "online_onsite_requires_space": True,
        "video_channels_required": False,
        "allow_cross_local_midnight": False,
        "student_buffer_minutes": 0,
        "objective_order": ["P0", "P1", "P2"],
        "unsupported_constraints": [],
        "students": students,
        "tutors": tutors,
        "resources": [
            {
                "id": f"space-demo-{n}",
                "kind": "SPACE",
                "student_capacity": 2,
                "buffer_minutes": 0,
                "availability": [{"start": 480, "end": 840}],
            }
            for n in (1, 2, 3)
        ],
        "service_windows": deepcopy(windows),
        "closures": [],
        "units": units,
    }
