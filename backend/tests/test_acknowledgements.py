"""P3 (DC-APPROVAZIONI): presa visione e controproposta del tutor, decisione del centro.

Usa i dati di una pubblicazione reale: richiede PostgreSQL come gli altri test di
pubblicazione. Su SQLite i test vengono saltati.
"""

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.calendar.models import ChangeRequest, LessonOccurrence, TutorAcknowledgement
from apps.identity.models import Account, RoleGrant

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="serve PostgreSQL"),
]


@pytest.fixture(autouse=True)
def debug_for_seed(settings):
    # seed_planning_demo e riservato allo sviluppo: serve DEBUG come negli altri test calendario
    settings.DEBUG = True


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def grant(user, role):
    RoleGrant.objects.create(account=user, role=role, valid_from=timezone.now())


@pytest.fixture
def published(settings, monkeypatch):
    """Pubblica una settimana dal seed sintetico, come i test del calendario."""
    from datetime import date, datetime, timezone as tz
    from io import StringIO

    from django.core.management import call_command

    from apps.scheduling.models import PlanningPolicy
    from tests.calendar_helpers import publish_week

    settings.EXPERIMENTAL_DB_PLANNING = True
    settings.EXPERIMENTAL_CALENDAR = True
    monkeypatch.setattr("apps.scheduling.runs.dispatch_one", lambda run_id: False)
    monkeypatch.setattr("apps.calendar.services.now", lambda: datetime(2026, 9, 30, tzinfo=tz.utc))
    actor = Account.objects.create_superuser(username="ack-center", email="ack-center@example.invalid", password="synthetic-test-password")
    call_command("seed_planning_demo", actor=actor.username, days="0", stdout=StringIO())
    publish_week((actor, PlanningPolicy.objects.get(), None), date(2026, 10, 5), "ack")
    lesson = LessonOccurrence.objects.select_related("tutor").first()
    assert lesson is not None
    return lesson


def tutor_client(lesson, email="tutor@example.test"):
    user = Account.objects.create_user(username=email, email=email, password="x-Strong-pass-91")
    grant(user, "TUTOR")
    lesson.tutor.account = user
    lesson.tutor.save()
    return client(user)


def center_client():
    user = Account.objects.create_user(username="g@example.test", email="g@example.test", password="x-Strong-pass-91")
    grant(user, "CENTER")
    return client(user)


def test_tutor_sees_only_own_and_acknowledges(published):
    t = tutor_client(published)
    rows = t.get("/api/v1/schedule-acks").json()["results"]
    assert rows and all(r["tutor"] == str(published.tutor_id) for r in rows)
    ack = rows[0]
    r = t.post(f"/api/v1/schedule-acks/{ack['id']}/acknowledge", {"expected_version": ack["version"]}, format="json")
    assert r.status_code == 200 and r.json()["state"] == "ACKNOWLEDGED"
    again = t.post(f"/api/v1/schedule-acks/{ack['id']}/acknowledge", {"expected_version": ack["version"]}, format="json")
    assert again.status_code == 409


def test_other_tutor_cannot_touch_ack_bola(published):
    tutor_client(published)
    center = center_client()
    ack = center.get("/api/v1/schedule-acks").json()["results"][0]
    other = Account.objects.create_user(username="o@example.test", email="o@example.test", password="x-Strong-pass-91")
    grant(other, "TUTOR")
    r = client(other).post(f"/api/v1/schedule-acks/{ack['id']}/acknowledge", {"expected_version": 1}, format="json")
    assert r.status_code in (403, 404)
    guardian = Account.objects.create_user(username="p@example.test", email="p@example.test", password="x-Strong-pass-91")
    grant(guardian, "GUARDIAN")
    assert client(guardian).get("/api/v1/schedule-acks").status_code == 403
    r = client(guardian).post(f"/api/v1/schedule-acks/{ack['id']}/decide", {"expected_version": 1, "decision": "ACCEPTED", "reason": "x"}, format="json")
    assert r.status_code == 403


def test_counter_then_center_asks_guardians(published):
    t = tutor_client(published)
    ack = t.get("/api/v1/schedule-acks").json()["results"][0]
    lesson = ack["lessons"][0]["id"]
    r = t.post(f"/api/v1/schedule-acks/{ack['id']}/counter", {"expected_version": ack["version"], "note": "Il martedì ho lezione all'università", "items": [{"lesson_id": lesson, "proposal": "Spostare a mercoledì stessa ora"}]}, format="json")
    assert r.status_code == 200 and r.json()["state"] == "COUNTER"
    center = center_client()
    r = center.post(f"/api/v1/schedule-acks/{ack['id']}/decide", {"expected_version": 2, "decision": "ASK_GUARDIANS", "reason": "Proposta ragionevole, sentiamo la famiglia"}, format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["state"] == "RESOLVED" and len(body["change_requests"]) == 1
    cr = ChangeRequest.objects.get(pk=body["change_requests"][0])
    assert cr.origin == "TUTOR" and cr.proposal["guardians_confirmation_required"] is True


def test_rejected_counter_returns_to_pending(published):
    t = tutor_client(published)
    ack = t.get("/api/v1/schedule-acks").json()["results"][0]
    t.post(f"/api/v1/schedule-acks/{ack['id']}/counter", {"expected_version": ack["version"], "items": [{"lesson_id": ack["lessons"][0]["id"], "proposal": "Un'ora dopo"}]}, format="json")
    r = center_client().post(f"/api/v1/schedule-acks/{ack['id']}/decide", {"expected_version": 2, "decision": "REJECTED", "reason": "Aula non disponibile"}, format="json")
    assert r.status_code == 200 and r.json()["state"] == "PENDING"
    assert TutorAcknowledgement.objects.get(pk=ack["id"]).decision == "REJECTED"


def test_counter_rejects_foreign_lesson(published):
    t = tutor_client(published)
    ack = t.get("/api/v1/schedule-acks").json()["results"][0]
    r = t.post(f"/api/v1/schedule-acks/{ack['id']}/counter", {"expected_version": ack["version"], "items": [{"lesson_id": "00000000-0000-0000-0000-000000000000", "proposal": "x"}]}, format="json")
    assert r.status_code == 422
