from io import StringIO
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.education.models import Student, GuardianLink
from apps.calendar.models import LessonOccurrence
from tests.test_calendar import center, publish  # noqa: F401  (fixture riusata)

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/my/lessons?from=2026-10-05&until=2026-10-12"


@pytest.fixture
def portals(center):  # noqa: F811
    publish(center)
    for _ in range(2):
        call_command("seed_portal_demo", actor=center[0].username, stdout=StringIO())
    return {
        name: Account.objects.get(username=name)
        for name in (
            "tutor-planning-demo-1",
            "portale-famiglia-demo",
            "portale-studente-demo",
        )
    }


def get(user, url=URL):
    client = APIClient()
    if user:
        client.force_authenticate(user)
    return client.get(url)


def test_seed_portal_accounts_are_unusable_and_idempotent(portals):
    assert all(not a.has_usable_password() for a in portals.values())
    family = portals["portale-famiglia-demo"]
    assert GuardianLink.objects.filter(account=family, verified=True).count() == 2
    assert Student.objects.filter(account=portals["portale-studente-demo"]).count() == 1


def test_tutor_sees_only_own_lessons(portals):
    user = portals["tutor-planning-demo-1"]
    rows = get(user).data["results"]
    expected = LessonOccurrence.objects.filter(tutor__account=user).count()
    assert len(rows) == expected > 0
    assert all(r["as_tutor"] and r["other_participants"] == 0 for r in rows)


def test_guardian_sees_children_and_hides_other_names(portals):
    family = portals["portale-famiglia-demo"]
    mine = set(
        GuardianLink.objects.filter(account=family).values_list("student_id", flat=True)
    )
    rows = get(family).data["results"]
    expected = (
        LessonOccurrence.objects.filter(participants__student_id__in=mine)
        .distinct()
        .count()
    )
    assert len(rows) == expected > 0
    names = set(
        Student.objects.filter(id__in=mine).values_list("display_name", flat=True)
    )
    for row in rows:
        assert not row["as_tutor"]
        assert {p["name"] for p in row["participants"]} <= names
        assert row["participants"]
    hidden = sum(r["other_participants"] for r in rows)
    total = sum(
        LessonOccurrence.objects.get(pk=r["id"]).participants.count() for r in rows
    )
    assert hidden == total - sum(len(r["participants"]) for r in rows)


def test_student_sees_only_own_lessons(portals):
    user = portals["portale-studente-demo"]
    own = Student.objects.get(account=user)
    rows = get(user).data["results"]
    assert (
        len(rows) == LessonOccurrence.objects.filter(participants__student=own).count()
    )
    assert all(
        [p["name"] for p in r["participants"]] == [own.display_name] for r in rows
    )


def test_revoked_link_and_roleless_account_see_nothing(portals):
    from django.utils import timezone

    family = portals["portale-famiglia-demo"]
    GuardianLink.objects.filter(account=family).update(revoked_at=timezone.now())
    assert get(family).data["results"] == []
    nobody = Account.objects.create_user(
        username="portal-nobody", email="portal-nobody@example.invalid"
    )
    assert get(nobody).data["results"] == []
    assert get(None).status_code == 403


def test_my_lessons_guards(portals, settings):
    user = portals["portale-studente-demo"]
    assert (
        get(user, "/api/v1/my/lessons?from=2026-10-05&until=2026-12-31").status_code
        == 400
    )
    settings.FEATURE_CALENDAR = False
    assert get(user).status_code == 503
