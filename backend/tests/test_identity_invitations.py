"""GAP-B02, GAP-B03 (s1-sicurezza): inviti monouso e reset password."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.identity.models import (
    Account,
    IdentityAuditEvent,
    Invitation,
    PasswordResetToken,
    UserSession,
)
from apps.identity.policies import granted_roles, visible_students
from apps.identity.tokens import hash_token
from tests.identity_helpers import PW, Api, Clock, enroll_staff, login, make_account

pytestmark = pytest.mark.django_db(transaction=True)
NEW_PW = "Password-Nuova-Sintetica-9"


@pytest.fixture(autouse=True)
def legacy_sender(settings):
    # s3: in configurazione standard i messaggi passano dall'outbox (vedi
    # tests/test_communications_identity.py); qui si verifica il sender diretto di s1.
    settings.IDENTITY_MESSAGE_SENDER = "apps.identity.delivery.send_email"


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def center(monkeypatch):
    clock = Clock(monkeypatch)
    make_account("centro@example.invalid", roles=["CENTER"])
    api = Api()
    enroll_staff(api, clock, "centro@example.invalid")
    return api


@pytest.fixture
def student():
    family = Family.objects.create(reference="SINTETICA-INV")
    return Student.objects.create(display_name="Studente sintetico", family=family)


def token_from_mail(index=-1):
    match = re.search(r"#token=([A-Za-z0-9_\-]+)", mail.outbox[index].body)
    assert match, mail.outbox[index].body
    return match.group(1)


def invite(center, **data):
    response = center.post("/api/v1/invitations", data)
    assert response.status_code == 201, response.content
    return response.json()


def test_guardian_invitation_only_after_relation_verified(center, student):
    row = invite(
        center,
        email="Genitore@Example.invalid",
        role="GUARDIAN",
        student=str(student.id),
        can_manage_availability=True,
    )
    assert (
        row["status"] == "PENDING_VERIFICATION"
        and row["email"] == "genitore@example.invalid"
    )
    assert mail.outbox == []  # nessun invio prima della verifica
    assert Invitation.objects.get().token_hash is None
    url = f"/api/v1/invitations/{row['id']}"
    assert center.post(url + "/resend").status_code == 409
    assert center.post(url + "/verify-relation", {"evidence": ""}).status_code == 400
    verified = center.post(
        url + "/verify-relation", {"evidence": "Documento verificato allo sportello"}
    )
    assert verified.status_code == 200 and verified.json()["status"] == "SENT"
    assert len(mail.outbox) == 1
    token = token_from_mail()
    stored = Invitation.objects.get()
    assert stored.token_hash == hash_token(token) and token not in str(stored.__dict__)
    assert stored.expires_at - timezone.now() > timedelta(hours=71)
    accepted = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": NEW_PW}
    )
    assert accepted.status_code == 201
    account = Account.objects.get(email="genitore@example.invalid")
    assert account.email_verified and granted_roles(account) == {"GUARDIAN"}
    link = GuardianLink.objects.get(account=account)
    assert link.verified and link.can_manage_availability and link.student == student
    assert list(visible_students(account)) == [student]
    # Monouso: il secondo uso dà lo stesso errore di un token inventato.
    again = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": NEW_PW}
    )
    fake = Api().post(
        "/api/v1/invitations/accept", {"token": "x" * 43, "password": NEW_PW}
    )
    assert again.status_code == fake.status_code == 400
    assert again.json() == fake.json() and again.json()["code"] == "INVALID_TOKEN"
    ops = list(IdentityAuditEvent.objects.values_list("operation", flat=True))
    assert {
        "invitation.created",
        "invitation.relation_verified",
        "invitation.accepted",
    } <= set(ops)
    assert not any(token in str(e.details) for e in IdentityAuditEvent.objects.all())


def test_guardian_cannot_be_tokenized_without_verification_at_db_level(student):
    actor = make_account("c@example.invalid", roles=["CENTER"])
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Invitation.objects.create(
                email="g@example.invalid",
                role="GUARDIAN",
                student=student,
                created_by=actor,
                token_hash="a" * 64,
                expires_at=timezone.now(),
                status="SENT",
            )


def test_expired_invitation_rejected(center, student):
    invite(center, email="s@example.invalid", role="STUDENT", student=str(student.id), age_confirmed=True)
    token = token_from_mail()
    Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": NEW_PW}
    )
    assert response.status_code == 400 and response.json()["code"] == "INVALID_TOKEN"
    assert not Account.objects.filter(email="s@example.invalid").exists()


def test_student_invitation_links_account(center, student):
    invite(center, email="s@example.invalid", role="STUDENT", student=str(student.id), age_confirmed=True)
    token = token_from_mail()
    weak = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": "12345678"}
    )
    assert weak.status_code == 400 and weak.json()["code"] == "WEAK_PASSWORD"
    assert (
        Api()
        .post("/api/v1/invitations/accept", {"token": token, "password": NEW_PW})
        .status_code
        == 201
    )
    student.refresh_from_db()
    assert student.account.email == "s@example.invalid"
    # Un secondo invito STUDENT per lo stesso studente è rifiutato.
    response = center.post(
        "/api/v1/invitations",
        {"email": "x@example.invalid", "role": "STUDENT", "student": str(student.id)},
    )
    assert response.status_code == 409


def test_resend_invalidates_previous_token_and_revoke(center, student):
    row = invite(center, email="t@example.invalid", role="TUTOR")
    first = token_from_mail()
    center.post(f"/api/v1/invitations/{row['id']}/resend")
    second = token_from_mail()
    assert first != second
    assert (
        Api()
        .post("/api/v1/invitations/accept", {"token": first, "password": NEW_PW})
        .status_code
        == 400
    )
    center.post(f"/api/v1/invitations/{row['id']}/revoke")
    assert (
        Api()
        .post("/api/v1/invitations/accept", {"token": second, "password": NEW_PW})
        .status_code
        == 400
    )
    assert Invitation.objects.get().status == "REVOKED"


def test_duplicate_open_invitation_rejected(center, student):
    invite(center, email="t@example.invalid", role="TUTOR")
    response = center.post(
        "/api/v1/invitations", {"email": "T@example.invalid", "role": "TUTOR"}
    )
    assert (
        response.status_code == 409 and response.json()["code"] == "INVITATION_EXISTS"
    )


def test_existing_account_must_login_to_accept(center, student):
    existing = make_account("tutor@example.invalid", roles=["TUTOR"])
    row = invite(
        center, email="tutor@example.invalid", role="GUARDIAN", student=str(student.id)
    )
    center.post(
        f"/api/v1/invitations/{row['id']}/verify-relation", {"evidence": "verificato"}
    )
    token = token_from_mail()
    anonymous = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": NEW_PW}
    )
    assert anonymous.status_code == 409 and anonymous.json()["code"] == "LOGIN_REQUIRED"
    existing.refresh_from_db()
    assert existing.check_password(PW)  # il token non cambia la password
    api = Api()
    login(api, "tutor@example.invalid")
    assert api.post("/api/v1/invitations/accept", {"token": token}).status_code == 201
    assert granted_roles(existing) == {"TUTOR", "GUARDIAN"}


def test_invitation_accept_is_rate_limited(settings):
    settings.IDENTITY_THROTTLE_RULES = {"invitation_accept": {"ip": (3, 900)}}
    api = Api()
    codes = [
        api.post(
            "/api/v1/invitations/accept", {"token": f"fake{i}", "password": NEW_PW}
        ).status_code
        for i in range(4)
    ]
    assert codes == [400, 400, 400, 429]


def test_invitation_endpoints_center_only(student):
    make_account("g@example.invalid", roles=["GUARDIAN"])
    make_account("t@example.invalid", roles=["TUTOR"])
    for email in ("g@example.invalid", "t@example.invalid"):
        api = Api()
        login(api, email)
        assert api.get("/api/v1/invitations").status_code == 403
        assert (
            api.post(
                "/api/v1/invitations", {"email": "z@example.invalid", "role": "CENTER"}
            ).status_code
            == 403
        )
    assert Api().get("/api/v1/invitations").status_code == 403


def test_center_without_mfa_cannot_invite(settings, client):
    staff = make_account("c@example.invalid", roles=["CENTER"])
    client.force_login(staff)
    assert client.get("/api/v1/invitations").json()["code"] == "MFA_REQUIRED"


# --- Reset password ------------------------------------------------------------------


def test_password_reset_flow_non_enumerating_and_revokes_sessions():
    user = make_account("f@example.invalid", roles=["GUARDIAN"])
    other_device = Api()
    login(other_device, "f@example.invalid")
    api = Api()
    exists = api.post("/api/v1/auth/password-reset", {"email": " F@Example.invalid"})
    missing = api.post(
        "/api/v1/auth/password-reset", {"email": "nessuno@example.invalid"}
    )
    assert exists.status_code == missing.status_code == 202
    assert exists.json() == missing.json()
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["f@example.invalid"]
    token = token_from_mail()
    record = PasswordResetToken.objects.get()
    assert record.token_hash == hash_token(token)
    assert (
        timedelta(minutes=29)
        < record.expires_at - timezone.now()
        <= timedelta(minutes=30)
    )
    weak = api.post(
        "/api/v1/auth/password-reset/confirm", {"token": token, "password": "password"}
    )
    assert weak.status_code == 400 and weak.json()["code"] == "WEAK_PASSWORD"
    done = api.post(
        "/api/v1/auth/password-reset/confirm", {"token": token, "password": NEW_PW}
    )
    assert done.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PW)
    assert other_device.get("/api/v1/me").status_code == 403
    assert not UserSession.objects.filter(revoked_at__isnull=True).exists()
    reuse = api.post(
        "/api/v1/auth/password-reset/confirm",
        {"token": token, "password": NEW_PW + "x"},
    )
    assert reuse.status_code == 400 and reuse.json()["code"] == "INVALID_TOKEN"


def test_new_reset_request_invalidates_previous_and_expiry():
    make_account("f@example.invalid", roles=["GUARDIAN"])
    api = Api()
    api.post("/api/v1/auth/password-reset", {"email": "f@example.invalid"})
    first = token_from_mail()
    api.post("/api/v1/auth/password-reset", {"email": "f@example.invalid"})
    second = token_from_mail()
    assert (
        api.post(
            "/api/v1/auth/password-reset/confirm", {"token": first, "password": NEW_PW}
        ).status_code
        == 400
    )
    PasswordResetToken.objects.filter(used_at__isnull=True).update(
        expires_at=timezone.now()
    )
    assert (
        api.post(
            "/api/v1/auth/password-reset/confirm", {"token": second, "password": NEW_PW}
        ).status_code
        == 400
    )


def test_reset_not_sent_to_inactive_or_unverified_passwordless(settings):
    inactive = make_account("i@example.invalid")
    inactive.is_active = False
    inactive.save()
    Account.objects.create_user(
        username="seed", email="seed@example.invalid"
    )  # senza password
    api = Api()
    for email in ("i@example.invalid", "seed@example.invalid"):
        assert (
            api.post("/api/v1/auth/password-reset", {"email": email}).status_code == 202
        )
    assert mail.outbox == []


def test_password_reset_is_rate_limited_per_identity():
    make_account("f@example.invalid")
    api = Api()
    codes = [
        api.post(
            "/api/v1/auth/password-reset", {"email": "f@example.invalid"}
        ).status_code
        for _ in range(4)
    ]
    assert codes == [202, 202, 202, 429]
    assert len(mail.outbox) == 3
