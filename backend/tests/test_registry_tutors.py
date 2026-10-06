"""P1 (guida v3.1): API tutor (T2) e utenti del centro (T3), con controlli BOLA e DEBUG=0."""

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.education.models import Tutor
from apps.governance.models import AuditEvent
from apps.identity.models import Account, Invitation, RoleGrant

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("nodebug")]


@pytest.fixture
def nodebug(settings):
    settings.DEBUG = False


def account(email, *roles):
    user = Account.objects.create_user(username=email, email=email, password="x-Strong-pass-91")
    for role in roles:
        RoleGrant.objects.create(account=user, role=role, valid_from=timezone.now())
    return user


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def center():
    return account("gestore@example.test", "CENTER")


def test_create_update_deactivate_tutor_with_audit(center):
    c = client_for(center)
    r = c.post("/api/v1/registry/tutors", {"display_name": "Anna", "email": "Anna@Example.test", "reason": "assunzione"}, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["email"] == "anna@example.test" and body["has_account"] is False
    tid, version = body["id"], body["version"]
    r = c.patch(f"/api/v1/registry/tutors/{tid}", {"display_name": "Anna B.", "reason": "refuso", "expected_version": version + 7}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "VERSION_CONFLICT"
    r = c.patch(f"/api/v1/registry/tutors/{tid}", {"display_name": "Anna B.", "reason": "refuso", "expected_version": version}, format="json")
    assert r.status_code == 200 and r.json()["display_name"] == "Anna B."
    r = c.post(f"/api/v1/registry/tutors/{tid}/deactivate", {"reason": "fine contratto", "expected_version": r.json()["version"]}, format="json")
    assert r.status_code == 200 and r.json()["active"] is False
    ops = set(AuditEvent.objects.filter(category="STAFF").values_list("operation", flat=True))
    assert {"TUTOR_CREATED", "TUTOR_UPDATED", "TUTOR_DEACTIVATED"} <= ops


def test_reason_optional(center):
    r = client_for(center).post("/api/v1/registry/tutors", {"display_name": "X", "reason": " "}, format="json")
    assert r.status_code == 201
    r = client_for(center).post("/api/v1/registry/tutors", {"display_name": "Y"}, format="json")
    assert r.status_code == 201
    event = AuditEvent.objects.filter(operation="TUTOR_CREATED").latest("id")
    assert event.reason == "Operazione dal gestionale"


def test_tutor_invitation_links_account_on_accept(center):
    from apps.identity import services

    c = client_for(center)
    r = c.post("/api/v1/registry/tutors", {"display_name": "Bruno", "email": "bruno@example.test", "reason": "nuovo", "invite": True}, format="json")
    assert r.status_code == 201, r.content
    inv = Invitation.objects.get(email="bruno@example.test", role="TUTOR")
    assert inv.status == Invitation.Status.SENT
    # Token in chiaro non disponibile: si riemette per il test con l'helper interno.
    from apps.identity.tokens import new_token

    token, digest = new_token()
    inv.token_hash = digest
    inv.save()
    acc = services.accept_invitation(token, password="Una-password-lunga-42")
    tutor = Tutor.objects.get(pk=r.json()["id"])
    assert tutor.account_id == acc.pk
    assert RoleGrant.objects.filter(account=acc, role="TUTOR", revoked_at__isnull=True).exists()


@pytest.mark.parametrize("roles", [("TUTOR",), ("GUARDIAN",), ("STUDENT",)])
def test_bola_non_center_forbidden(center, roles):
    other = account("altro-%s@example.test" % roles[0].lower(), *roles)
    tutor = Tutor.objects.create(display_name="T", email="t@example.test")
    c = client_for(other)
    assert c.get("/api/v1/registry/tutors").status_code == 403
    assert c.post("/api/v1/registry/tutors", {"display_name": "Y", "reason": "x"}, format="json").status_code == 403
    assert c.patch(f"/api/v1/registry/tutors/{tutor.pk}", {"display_name": "Z", "reason": "x", "expected_version": 1}, format="json").status_code == 403
    assert c.get("/api/v1/identity/center-users").status_code == 403
    assert c.post("/api/v1/identity/center-invitations", {"email": "a@b.it", "role": "CENTER", "reason": "x"}, format="json").status_code == 403


def test_center_users_and_last_center_protection(center):
    c = client_for(center)
    account("tutor1@example.test", "TUTOR")
    account("famiglia@example.test", "GUARDIAN")
    emails = {u["email"] for u in c.get("/api/v1/identity/center-users").json()["results"]}
    assert emails == {"gestore@example.test", "tutor1@example.test"}
    r = c.post(f"/api/v1/identity/center-users/{center.pk}/revoke-role", {"role": "CENTER", "reason": "x"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "SELF_REVOKE"
    second = account("secondo@example.test", "CENTER")
    r = c.post(f"/api/v1/identity/center-users/{second.pk}/revoke-role", {"role": "CENTER", "reason": "uscita"}, format="json")
    assert r.status_code == 200 and r.json()["roles"] == []


def test_invite_center_user(center):
    r = client_for(center).post("/api/v1/identity/center-invitations", {"email": "nuovo@example.test", "role": "CENTER", "reason": "secondo gestore"}, format="json")
    assert r.status_code == 201, r.content
    assert Invitation.objects.filter(email="nuovo@example.test", role="CENTER", status="SENT").exists()
    r = client_for(center).post("/api/v1/identity/center-invitations", {"email": "t@example.test", "role": "TUTOR", "reason": "x"}, format="json")
    assert r.status_code == 400
