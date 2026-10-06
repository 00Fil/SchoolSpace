"""GAP-B06: API auditate per famiglie, studenti, deleghe e inviti (FR01, FR02, FR23)."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.education.models import GuardianLink, Student
from apps.governance.models import AuditEvent
from apps.identity.models import Account, Invitation
from apps.identity.policies import visible_students
from apps.privacy.models import GuardianLinkDetail
from apps.privacy.testing import (  # noqa: F401
    api,
    center,
    family,
    make_account,
    outsider,
    privacy_storage,
    student,
)

from tests.outbox_mail import mailoutbox  # noqa: E402,F401  (consegna via outbox)

pytestmark = pytest.mark.django_db


def ops(**filters):
    return list(
        AuditEvent.objects.filter(**filters).values_list("operation", flat=True)
    )


def test_non_center_cannot_use_registry(outsider, family, student):
    client = api(outsider)
    for url in (
        "/api/v1/registry/families",
        "/api/v1/registry/students",
        "/api/v1/registry/guardian-links",
        "/api/v1/registry/invitations",
        f"/api/v1/registry/students/{student.pk}",
    ):
        assert client.get(url).status_code == 403
    response = client.post(
        "/api/v1/registry/families", {"reference": "X", "reason": "x"}, format="json"
    )
    assert response.status_code == 403
    assert api().get("/api/v1/registry/families").status_code == 403


def test_family_and_student_lifecycle_is_audited(center):
    client = api(center)
    response = client.post(
        "/api/v1/registry/families",
        {
            "reference": "FAM-API-1",
            "contact_name": "Contatto",
            "contact_email": "Contatto@Example.invalid",
            "reason": "nuova iscrizione",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    fam = response.data
    assert fam["contact_email"] == "contatto@example.invalid"
    duplicate = client.post(
        "/api/v1/registry/families",
        {"reference": "FAM-API-1", "reason": "doppione"},
        format="json",
    )
    assert duplicate.status_code == 409
    response = client.post(
        "/api/v1/registry/students",
        {
            "family": fam["id"],
            "display_name": "Allievo",
            "birth_date": "2012-03-04",
            "reason": "iscrizione",
        },
        format="json",
    )
    assert response.status_code == 201
    stu = response.data
    assert stu["birth_date"] == "2012-03-04"
    stale = client.patch(
        f"/api/v1/registry/students/{stu['id']}",
        {"expected_version": stu["version"] + 5, "level": "X", "reason": "r"},
        format="json",
    )
    assert stale.status_code == 409
    ok = client.patch(
        f"/api/v1/registry/students/{stu['id']}",
        {"expected_version": stu["version"], "level": "Primaria", "reason": "r"},
        format="json",
    )
    assert ok.status_code == 200 and ok.data["level"] == "Primaria"
    missing_reason = client.patch(
        f"/api/v1/registry/families/{fam['id']}",
        {"expected_version": fam["version"], "contact_phone": "1"},
        format="json",
    )
    # Il motivo non è più richiesto: senza motivo vale il testo standard.
    assert missing_reason.status_code == 200
    extra = client.post(
        "/api/v1/registry/students",
        {"family": fam["id"], "display_name": "Y", "reason": "r", "is_admin": True},
        format="json",
    )
    assert extra.status_code == 400
    assert ops(category="FAMILY") == [
        "FAMILY_CREATED",
        "STUDENT_CREATED",
        "STUDENT_UPDATED",
        "FAMILY_UPDATED",
    ]
    family_event = AuditEvent.objects.get(operation="FAMILY_UPDATED")
    assert family_event.reason == "Operazione dal gestionale"
    event = AuditEvent.objects.get(operation="STUDENT_UPDATED")
    assert event.actor == center and event.reason == "r"
    assert event.details == {"changed_fields": ["level"]}


def test_guardian_link_create_verify_revoke_controls_scope(center, student):
    client = api(center)
    pre = make_account("genitore")
    pre.is_active = False
    pre.save()
    response = client.post(
        "/api/v1/registry/guardian-links",
        {
            "student": str(student.pk),
            "guardian_email": "Genitore@example.invalid",
            "relationship": "LEGAL_GUARDIAN",
            "permissions": {"can_manage_availability": True},
            "reason": "modulo iscrizione",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    link = response.data
    assert link["verified"] is False and link["active"] is False
    assert link["relationship"] == "LEGAL_GUARDIAN"
    guardian = Account.objects.get(email="genitore@example.invalid")
    assert guardian.pk == pre.pk  # account esistente riusato, mai creato dal registro
    # Non verificata: nessun accesso ai dati del minore.
    guardian.is_active = True
    guardian.save()
    assert not visible_students(guardian).exists()
    again = client.post(
        "/api/v1/registry/guardian-links",
        {"student": str(student.pk), "account": str(guardian.pk), "reason": "bis"},
        format="json",
    )
    assert again.status_code == 409
    verify = client.post(
        f"/api/v1/registry/guardian-links/{link['id']}/verify",
        {
            "expected_version": link["version"],
            "method": "documento visionato in sede",
            "reason": "verifica",
        },
        format="json",
    )
    assert verify.status_code == 200 and verify.data["active"] is True
    assert list(visible_students(guardian)) == [student]
    perms = client.post(
        f"/api/v1/registry/guardian-links/{link['id']}/permissions",
        {
            "expected_version": verify.data["version"],
            "permissions": {"can_request_changes": True, "can_view": True},
            "reason": "richiesta famiglia",
        },
        format="json",
    )
    assert perms.status_code == 200 and perms.data["can_request_changes"] is True
    revoke = client.post(
        f"/api/v1/registry/guardian-links/{link['id']}/revoke",
        {"reason": "fine rapporto"},
        format="json",
    )
    assert revoke.status_code == 200 and revoke.data["revoked_at"]
    # Revoca immediata nel live.
    assert not visible_students(guardian).exists()
    assert (
        client.post(
            f"/api/v1/registry/guardian-links/{link['id']}/revoke",
            {"reason": "ancora"},
            format="json",
        ).status_code
        == 409
    )
    assert ops(category="GUARDIANSHIP") == [
        "LINK_CREATED",
        "LINK_VERIFIED",
        "LINK_PERMISSIONS_CHANGED",
        "LINK_REVOKED",
    ]
    changed = AuditEvent.objects.get(operation="LINK_PERMISSIONS_CHANGED").details
    assert changed["before"]["can_request_changes"] is False
    assert changed["after"]["can_request_changes"] is True
    # Dopo la revoca si può creare una nuova delega per la stessa coppia.
    new = client.post(
        "/api/v1/registry/guardian-links",
        {"student": str(student.pk), "account": str(guardian.pk), "reason": "nuova"},
        format="json",
    )
    assert new.status_code == 201


def test_two_guardians_same_student_different_rights(center, student):
    """FR02: due tutori dello stesso studente possono avere diritti differenti."""
    from apps.identity.policies import can_manage_student_availability
    from apps.privacy import registry

    first = make_account("s4-g1", "GUARDIAN")
    second = make_account("s4-g2", "GUARDIAN")
    for account, manage in ((first, True), (second, False)):
        link = registry.create_guardian_link(
            center,
            student=student,
            account=account,
            permissions={"can_manage_availability": manage},
            reason="test",
        )
        registry.verify_guardian_link(
            center, link, expected_version=link.version, method="doc", reason="ok"
        )
    assert can_manage_student_availability(first, student)
    assert not can_manage_student_availability(second, student)
    assert list(visible_students(second)) == [student]


def test_student_cannot_self_delegate(center, student):
    from apps.privacy import registry
    from apps.privacy.errors import PrivacyError

    account = make_account("s4-self", "STUDENT")
    Student.objects.filter(pk=student.pk).update(account=account)
    student.refresh_from_db()
    with pytest.raises(PrivacyError):
        registry.create_guardian_link(
            center, student=student, account=account, reason="no"
        )


def _verified_link(center, student, email="invitato@example.invalid"):
    from apps.privacy import registry

    account = registry.existing_account(email) or make_account(email.split("@")[0])
    link = registry.create_guardian_link(
        center, student=student, account=account, reason="r"
    )
    return registry.verify_guardian_link(
        center, link, expected_version=link.version, method="doc", reason="ok"
    )


TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_\-]+)")


def _token(mailoutbox):
    return TOKEN_RE.search(mailoutbox[-1].body).group(1)


STRONG = "Synthetic-Strong-Pass-2026"


def test_guardian_link_for_new_email_becomes_identity_invitation(center, student):
    response = api(center).post(
        "/api/v1/registry/guardian-links",
        {
            "student": str(student.pk),
            "guardian_email": "Nuovo@example.invalid",
            "relationship": "LEGAL_GUARDIAN",
            "permissions": {"can_manage_availability": True},
            "reason": "modulo iscrizione",
        },
        format="json",
    )
    assert response.status_code == 202, response.data
    assert response.data["link"] is None
    body = response.data["invitation"]
    assert body["status"] == "PENDING_VERIFICATION" and "token" not in body
    assert body["relationship"] == "LEGAL_GUARDIAN"
    # Nessun account "fantasma" creato dal registro.
    assert not Account.objects.filter(email__iexact="nuovo@example.invalid").exists()
    assert not GuardianLink.objects.filter(student=student).exists()


def test_invitation_flow_uses_identity_and_secret_never_audited(
    center, student, mailoutbox, django_capture_on_commit_callbacks
):
    client = api(center)
    created = client.post(
        "/api/v1/registry/invitations",
        {
            "student": str(student.pk),
            "email": "pre@example.invalid",
            "relationship": "DELEGATE",
            "permissions": {
                "can_manage_availability": True,
                "can_receive_notifications": False,
                "can_request_changes": True,
            },
            "reason": "invito",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["status"] == "PENDING_VERIFICATION"
    assert mailoutbox == []  # nessun token prima della verifica della relazione
    pk = created.data["id"]
    with django_capture_on_commit_callbacks(execute=True):
        verified = client.post(
            f"/api/v1/registry/invitations/{pk}/verify-relation",
            {"evidence": "documento visionato"},
            format="json",
        )
    assert verified.status_code == 200, verified.data
    assert verified.data["status"] == "SENT" and "token" not in verified.data
    token = _token(mailoutbox)
    invitation = Invitation.objects.get(pk=pk)
    assert invitation.token_hash != token and len(invitation.token_hash) == 64
    listing = client.get("/api/v1/registry/invitations")
    assert "token" not in listing.data["results"][0]
    anon = api()
    weak = anon.post(
        "/api/v1/invitations/accept", {"token": token, "password": "123"}, format="json"
    )
    assert weak.status_code == 400
    ok = anon.post(
        "/api/v1/invitations/accept",
        {"token": token, "password": STRONG},
        format="json",
    )
    assert ok.status_code == 201, ok.content
    account = Account.objects.get(email="pre@example.invalid")
    link = GuardianLink.objects.get(account=account, student=student)
    assert link.verified and link.can_manage_availability
    detail = GuardianLinkDetail.objects.get(link=link)
    assert detail.relationship == "DELEGATE"
    assert detail.can_receive_notifications is False and detail.can_request_changes
    assert list(visible_students(account)) == [student]
    reuse = anon.post(
        "/api/v1/invitations/accept",
        {"token": token, "password": STRONG + "x"},
        format="json",
    )
    bogus = anon.post(
        "/api/v1/invitations/accept",
        {"token": "x" * 43, "password": STRONG + "x"},
        format="json",
    )
    assert reuse.status_code == bogus.status_code == 400
    assert reuse.json() == bogus.json() and reuse.json()["code"] == "INVALID_TOKEN"
    dump = str(list(AuditEvent.objects.values()))
    assert token not in dump and STRONG not in dump
    assert "INVITE_CREATED" in ops(category="INVITE")


def test_expired_and_revoked_invitations(
    center, student, mailoutbox, django_capture_on_commit_callbacks
):
    from apps.privacy import registry

    def sent(email):
        invitation = registry.invite_guardian(
            center, student=student, email=email, reason="r"
        )
        with django_capture_on_commit_callbacks(execute=True):
            invitation = registry.verify_invitation_relation(
                center, invitation, evidence="doc"
            )
        return invitation, _token(mailoutbox)

    def accept(token):
        return api().post(
            "/api/v1/invitations/accept",
            {"token": token, "password": STRONG},
            format="json",
        )

    first, token1 = sent("scaduto@example.invalid")
    Invitation.objects.filter(pk=first.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert accept(token1).json()["code"] == "INVALID_TOKEN"
    second, token2 = sent("revocato@example.invalid")
    revoked = api(center).post(
        f"/api/v1/registry/invitations/{second.pk}/revoke",
        {"reason": "errore"},
        format="json",
    )
    assert revoked.status_code == 200 and revoked.data["status"] == "REVOKED"
    assert accept(token2).json()["code"] == "INVALID_TOKEN"
    # Revoca di una delega: revoca anche l'invito aperto per stessa email e allievo.
    link = _verified_link(center, student, email="doppio@example.invalid")
    Account.objects.filter(pk=link.account_id).update(email="altro@example.invalid")
    third, token3 = sent("doppio@example.invalid")
    Account.objects.filter(pk=link.account_id).update(email="doppio@example.invalid")
    registry.revoke_guardian_link(center, link, reason="revoca")
    assert Invitation.objects.get(pk=third.pk).status == "REVOKED"
    assert accept(token3).json()["code"] == "INVALID_TOKEN"
    assert not Account.objects.filter(
        email__in=["scaduto@example.invalid", "revocato@example.invalid"]
    ).exists()


def test_existing_account_must_log_in_to_accept(
    center, student, mailoutbox, django_capture_on_commit_callbacks
):
    from apps.privacy import registry

    make_account("gia")
    invitation = registry.invite_guardian(
        center, student=student, email="gia@example.invalid", reason="r"
    )
    with django_capture_on_commit_callbacks(execute=True):
        registry.verify_invitation_relation(center, invitation, evidence="doc")
    response = api().post(
        "/api/v1/invitations/accept",
        {"token": _token(mailoutbox), "password": STRONG},
        format="json",
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LOGIN_REQUIRED"


def test_link_list_filters_and_detail(center, student):
    link = _verified_link(center, student)
    client = api(center)
    active = client.get("/api/v1/registry/guardian-links?state=active")
    assert [r["id"] for r in active.data["results"]] == [str(link.pk)]
    detail = client.get(f"/api/v1/registry/students/{student.pk}")
    assert detail.data["guardian_links"][0]["id"] == str(link.pk)
    assert GuardianLinkDetail.objects.get(link=link).verified_by == center
    assert (
        client.post(
            f"/api/v1/registry/guardian-links/{link.pk}/unknown", {}, format="json"
        ).status_code
        == 404
    )


def test_student_deactivation_disables_student_account(center, student):
    account = make_account("s4-stud-acc", "STUDENT")
    Student.objects.filter(pk=student.pk).update(account=account)
    student.refresh_from_db()
    response = api(center).patch(
        f"/api/v1/registry/students/{student.pk}",
        {"expected_version": student.version, "active": False, "reason": "ritiro"},
        format="json",
    )
    assert response.status_code == 200
    account.refresh_from_db()
    assert not account.is_active


def test_admin_actions_are_audited(center, family):
    from django.contrib.admin.models import CHANGE, LogEntry
    from django.contrib.contenttypes.models import ContentType

    LogEntry.objects.create(
        user=center,
        content_type=ContentType.objects.get_for_model(family),
        object_id=str(family.pk),
        object_repr="x",
        action_flag=CHANGE,
        change_message='[{"changed": {"fields": ["reference"]}}]',
    )
    event = AuditEvent.objects.get(category="ADMIN")
    assert event.operation == "ADMIN_CHANGE"
    assert event.object_type == "education.family"
    assert event.actor == center and event.purpose == "emergenza"


def test_guardian_link_rows_unique_active_per_pair(center, student):
    from apps.privacy import registry
    from apps.privacy.errors import Conflict

    link = _verified_link(center, student)
    with pytest.raises(Conflict):
        registry.create_guardian_link(
            center, student=student, account=link.account, reason="dup"
        )
    assert GuardianLink.objects.filter(student=student).count() == 1
