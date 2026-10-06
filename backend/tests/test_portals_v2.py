"""Portali v2 (s6-frontend): riepilogo multi-figlio, scope, eccezioni a cursore, presenze."""

from datetime import datetime, timedelta, timezone as tz
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.availability.models import AvailabilityException
from apps.calendar.models import LessonOccurrence
from apps.education.models import GuardianLink, Student, Tutor
from apps.identity.models import Account
from tests.test_calendar import center, publish  # noqa: F401  (fixture riusata)

pytestmark = pytest.mark.django_db(transaction=True)
OVERVIEW = "/api/v1/portal/overview?week=2026-10-07"
EXC = "/api/v1/portal/availability-exceptions"


@pytest.fixture
def portals(center):  # noqa: F811
    publish(center)
    call_command("seed_portal_demo", actor=center[0].username, stdout=StringIO())
    return {
        name: Account.objects.get(username=name)
        for name in (
            "tutor-planning-demo-1",
            "portale-famiglia-demo",
            "portale-studente-demo",
        )
    }


def client_for(user):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client


def get(user, url=OVERVIEW):
    return client_for(user).get(url)


def minutes(rows):
    return sum(int((x.end_at - x.start_at).total_seconds() // 60) for x in rows)


def test_guardian_overview_lists_each_child_with_permissions(portals):
    family = portals["portale-famiglia-demo"]
    data = get(family).json()
    assert data["week"] == {"from": "2026-10-05", "until": "2026-10-12"}
    assert data["calendar_enabled"] is True and data["tutor"] is None
    linked = set(
        GuardianLink.objects.filter(account=family).values_list("student_id", flat=True)
    )
    assert {c["student_id"] for c in data["children"]} == {str(s) for s in linked}
    for child in data["children"]:
        assert child["relation"] == "GUARDIAN"
        # Delega del seed: gestione disponibilità sì, richieste di modifica no (default negato).
        assert child["permissions"]["can_manage_availability"] is True
        assert child["permissions"]["can_request_changes"] is False
        assert child["read_only"] is False
        expected = (
            LessonOccurrence.objects.filter(
                participants__student_id=child["student_id"]
            )
            .exclude(state="CANCELLED")
            .distinct()
        )
        assert child["week"]["lessons"] == expected.count()
        assert child["week"]["minutes"] == minutes(expected)


def test_view_only_delegation_is_read_only_and_revocation_is_immediate(portals):
    family = portals["portale-famiglia-demo"]
    links = list(GuardianLink.objects.filter(account=family).order_by("id"))
    GuardianLink.objects.filter(pk=links[0].pk).update(can_manage_availability=False)
    rows = {c["student_id"]: c for c in get(family).json()["children"]}
    assert rows[str(links[0].student_id)]["read_only"] is True
    assert rows[str(links[1].student_id)]["read_only"] is False
    GuardianLink.objects.filter(pk=links[1].pk).update(revoked_at=timezone.now())
    rows = get(family).json()["children"]
    assert [c["student_id"] for c in rows] == [str(links[0].student_id)]


def test_can_request_changes_follows_delegation_detail(portals):
    from apps.privacy.models import GuardianLinkDetail

    family = portals["portale-famiglia-demo"]
    link = GuardianLink.objects.filter(account=family).order_by("id").first()
    GuardianLinkDetail.objects.update_or_create(
        link=link, defaults={"can_request_changes": True}
    )
    rows = {c["student_id"]: c for c in get(family).json()["children"]}
    assert rows[str(link.student_id)]["permissions"]["can_request_changes"] is True


def test_student_sees_only_self_and_policy_is_pending_approval(portals, settings):
    user = portals["portale-studente-demo"]
    own = Student.objects.get(account=user)
    data = get(user).json()
    assert [c["student_id"] for c in data["children"]] == [str(own.id)]
    child = data["children"][0]
    assert child["relation"] == "SELF"
    assert child["permissions"]["can_request_changes"] is False
    assert data["policies"]["status"] == "DA_APPROVARE"
    settings.PORTAL_STUDENT_CAN_REQUEST_CHANGES = True
    assert get(user).json()["children"][0]["permissions"]["can_request_changes"]


def test_tutor_load_in_minutes(portals):
    user = portals["tutor-planning-demo-1"]
    tutor = Tutor.objects.get(account=user)
    data = get(user).json()
    assert data["children"] == []
    block = data["tutor"]
    assert block["tutor_id"] == str(tutor.id)
    lessons = LessonOccurrence.objects.filter(tutor=tutor).exclude(state="CANCELLED")
    assert block["week"]["scheduled_minutes"] == minutes(lessons) > 0
    assert sum(d["minutes"] for d in block["week"]["by_day"]) == minutes(lessons)
    assert len(block["week"]["by_day"]) == 7
    assert block["limits"]["weekly_limit_minutes"] > 0


def test_center_gets_empty_portal_blocks_and_anonymous_is_refused(portals, center):  # noqa: F811
    data = center[2].get(OVERVIEW).json()
    assert data["children"] == [] and data["tutor"] is None
    assert data["context"] == "CENTER"
    assert get(None).status_code == 403
    nobody = Account.objects.create_user(
        username="portal-v2-nobody", email="portal-v2-nobody@example.invalid"
    )
    data = get(nobody).json()
    assert data["children"] == [] and data["tutor"] is None


def test_invalid_week_is_rejected(portals):
    assert (
        get(
            portals["portale-studente-demo"], "/api/v1/portal/overview?week=x"
        ).status_code
        == 400
    )


def test_calendar_disabled_hides_lesson_figures(portals, settings):
    settings.FEATURE_CALENDAR = False
    data = get(portals["portale-famiglia-demo"]).json()
    assert data["calendar_enabled"] is False
    assert all(c["week"] is None for c in data["children"])
    tutor = portals["tutor-planning-demo-1"]
    assert get(tutor, "/api/v1/portal/attendance-pending").status_code == 503


def _exceptions(student, n):
    base = timezone.now() + timedelta(days=1)
    for i in range(n):
        AvailabilityException.objects.create(
            student=student,
            start_at=base + timedelta(days=i),
            end_at=base + timedelta(days=i, hours=2),
            mode="ONLINE",
            location="REMOTE",
            kind="REMOVE_AVAILABLE",
        )


def test_exceptions_cursor_pagination_and_scope(portals):
    family = portals["portale-famiglia-demo"]
    mine = GuardianLink.objects.filter(account=family).order_by("id").first().student
    other = Student.objects.get(account=portals["portale-studente-demo"])
    _exceptions(mine, 23)
    _exceptions(other, 2)
    client = client_for(family)
    url, seen, pages = f"{EXC}?student={mine.id}", [], 0
    while url:
        page = client.get(url).json()
        if page["next"]:
            assert "cursor=" in page["next"] and "page=" not in page["next"]
        seen += [r["start_at"] for r in page["results"]]
        url, pages = page["next"], pages + 1
    assert len(seen) == 23 and pages == 2 and seen == sorted(seen)
    # Studente non delegato, UUID non valido, tutor altrui: nessuna enumerazione.
    assert client.get(f"{EXC}?student={other.id}").status_code == 404
    assert client.get(f"{EXC}?student=x").status_code == 404
    assert client.get(EXC).status_code == 400
    tutor = Tutor.objects.get(account=portals["tutor-planning-demo-1"])
    assert client.get(f"{EXC}?tutor={tutor.id}").status_code == 404
    own = client_for(portals["tutor-planning-demo-1"]).get(f"{EXC}?tutor={tutor.id}")
    assert own.status_code == 200


def test_attendance_pending_lists_only_finished_unrecorded_lessons(
    portals, monkeypatch
):
    user = portals["tutor-planning-demo-1"]
    client = client_for(user)
    assert client.get("/api/v1/portal/attendance-pending").json()["results"] == []
    later = datetime(2026, 10, 10, 12, tzinfo=tz.utc)
    monkeypatch.setattr("api.portals_v2.current_time", lambda: later)
    rows = client.get("/api/v1/portal/attendance-pending").json()["results"]
    expected = LessonOccurrence.objects.filter(
        tutor__account=user, state="PUBLISHED", end_at__lte=later
    )
    assert {r["lesson_id"] for r in rows} == {str(x.id) for x in expected}
    assert rows and all(r["participants"] and r["version"] >= 1 for r in rows)
    family = portals["portale-famiglia-demo"]
    assert (
        client_for(family).get("/api/v1/portal/attendance-pending").status_code == 404
    )


def test_contract_matches_live_responses(portals):
    yaml = pytest.importorskip("yaml")
    jsonschema = pytest.importorskip("jsonschema")
    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml").read_text()
    )

    def check(name, data):
        schema = {
            "components": spec["components"],
            "$ref": f"#/components/schemas/{name}",
        }
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(data))
        assert not errors, [e.message for e in errors]

    for path in (
        "/portal/overview",
        "/portal/availability-exceptions",
        "/portal/attendance-pending",
        "/auth/context",
        "/auth/mfa/verify",
        "/change-requests/",
        "/occurrences/{pk}/attendance/",
    ):
        assert "get" in spec["paths"][path] or "post" in spec["paths"][path]
    check("PortalOverview", get(portals["portale-famiglia-demo"]).json())
    check("PortalOverview", get(portals["tutor-planning-demo-1"]).json())
    check("PortalOverview", get(portals["portale-studente-demo"]).json())
    family = portals["portale-famiglia-demo"]
    student = GuardianLink.objects.filter(account=family).first().student
    _exceptions(student, 1)
    check(
        "PortalExceptionPage",
        client_for(family).get(f"{EXC}?student={student.id}").json(),
    )
    check(
        "PortalAttendancePage",
        client_for(portals["tutor-planning-demo-1"])
        .get("/api/v1/portal/attendance-pending")
        .json(),
    )


def test_may_request_changes_follows_delegation_and_d07(portals, settings):
    """Permesso applicato anche lato server all'invio (s2 conflicts.submit_change_request)."""
    from apps.calendar.conflicts import may_request_changes
    from apps.privacy.models import GuardianLinkDetail

    user = portals["portale-famiglia-demo"]
    link = GuardianLink.objects.filter(account=user).order_by("id").first()
    student = link.student_id
    GuardianLinkDetail.objects.update_or_create(
        link=link, defaults={"can_request_changes": False}
    )
    assert may_request_changes(user, "CENTER", None)
    assert may_request_changes(user, "TUTOR", None)
    assert not may_request_changes(user, "GUARDIAN", student)
    assert not may_request_changes(user, "GUARDIAN", None)
    GuardianLinkDetail.objects.update_or_create(
        link=link, defaults={"can_request_changes": True}
    )
    assert may_request_changes(user, "GUARDIAN", student)
    settings.PORTAL_STUDENT_CAN_REQUEST_CHANGES = False
    assert not may_request_changes(user, "STUDENT", student)
    settings.PORTAL_STUDENT_CAN_REQUEST_CHANGES = True
    assert may_request_changes(user, "STUDENT", student)
    assert not may_request_changes(user, None, student)
