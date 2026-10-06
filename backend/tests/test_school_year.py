"""P2 (guida v3.1): anno scolastico, pause come chiusure, approvazione in blocco, orari da griglia."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import Account, RoleGrant
from apps.scheduling.models import Closure, ServiceWindow

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def nodebug(settings):
    settings.DEBUG = False


def account(email, *roles):
    user = Account.objects.create_user(username=email, email=email, password="x-Strong-pass-91")
    for role in roles:
        RoleGrant.objects.create(account=user, role=role, valid_from=timezone.now())
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def center():
    return account("gestore@example.test", "CENTER")


def make_year(c):
    r = c.post("/api/v1/planning/school-years", {"name": "2026/27", "start_date": "2026-09-14", "end_date": "2027-08-31", "reason": "nuovo anno"}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def add(c, y, kind, start, end):
    return c.post(f"/api/v1/planning/school-years/{y['id']}/periods", {"kind": kind, "start_date": start, "end_date": end, "reason": "calendario"}, format="json")


def test_breaks_create_closures_recovery_does_not(center):
    y = make_year(center)
    r = add(center, y, "CHRISTMAS", "2026-12-23", "2027-01-06")
    assert r.status_code == 201 and r.json()["closes_center"] is True
    assert Closure.objects.filter(mode="ALL", reason__startswith="Pausa natalizia").count() == 1
    r = add(center, y, "RECOVERY", "2027-06-14", "2027-06-30")
    assert r.status_code == 201 and r.json()["closes_center"] is False
    r = add(center, y, "SUMMER", "2027-06-20", "2027-08-31")
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_OVERLAP"


def test_period_update_and_delete_follow_closure(center):
    y = make_year(center)
    p = add(center, y, "EASTER", "2027-03-25", "2027-03-30").json()
    r = center.patch(f"/api/v1/planning/study-periods/{p['id']}", {"end_date": "2027-03-31", "expected_version": p["version"], "reason": "correzione"}, format="json")
    assert r.status_code == 200
    new_version = r.json()["version"]
    r = center.post(f"/api/v1/planning/study-periods/{p['id']}/delete", {"expected_version": p["version"] - 1, "reason": "x"}, format="json")
    assert r.status_code == 409
    r = center.post(f"/api/v1/planning/study-periods/{p['id']}/delete", {"expected_version": new_version, "reason": "x"}, format="json")
    assert r.status_code == 204 and Closure.objects.count() == 0


def test_period_outside_year_rejected(center):
    y = make_year(center)
    r = add(center, y, "BREAK", "2027-09-02", "2027-09-03")
    assert r.status_code == 409 and r.json()["code"] == "PERIOD_OUTSIDE_YEAR"


def test_service_windows_replace(center):
    body = {"mode": "IN_PERSON", "period_start": "2026-09-14", "period_end": "2027-06-30", "reason": "orari", "slots": [{"weekday": 0, "start": 900, "end": 1140}, {"weekday": 2, "start": 900, "end": 1080}]}
    assert center.post("/api/v1/planning/service-windows/replace", body, format="json").json() == {"created": 2, "removed": 0}
    body["slots"] = body["slots"][:1]
    assert center.post("/api/v1/planning/service-windows/replace", body, format="json").json() == {"created": 1, "removed": 2}
    assert ServiceWindow.objects.count() == 1


@pytest.mark.parametrize("role", ["TUTOR", "GUARDIAN", "STUDENT"])
def test_bola_writes_are_center_only(center, role):
    y = make_year(center)
    other = account(f"x-{role.lower()}@example.test", role)
    assert other.get("/api/v1/planning/school-years").status_code == 200  # lettura per i portali
    assert other.post("/api/v1/planning/school-years", {"name": "x", "start_date": "2028-09-01", "end_date": "2029-06-30", "reason": "x"}, format="json").status_code == 403
    assert add(other, y, "BREAK", "2026-11-01", "2026-11-02").status_code == 403
    assert other.post("/api/v1/availability/bulk-review", {"ids": ["00000000-0000-0000-0000-000000000000"], "status": "APPROVED", "reason": "x"}, format="json").status_code == 403
    assert other.post("/api/v1/planning/service-windows/replace", {"mode": "ONLINE", "period_start": "2026-09-14", "period_end": "2027-06-30", "slots": [], "reason": "x"}, format="json").status_code == 403
