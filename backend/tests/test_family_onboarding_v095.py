"""v0.9.5: iscrizione partendo dal genitore, invito di famiglia, QR e accesso immediato."""

import re
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.education.models import GuardianLink
from apps.governance.models import AuditEvent
from apps.identity.models import Account, Invitation
from apps.identity.policies import visible_students
from apps.privacy.models import FamilyGuardian, GuardianLinkDetail
from apps.privacy.testing import api, center, make_account, outsider, privacy_storage  # noqa: F401

from tests.outbox_mail import mailoutbox  # noqa: F401

pytestmark = pytest.mark.django_db
TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_\-]+)")
STRONG = "Synthetic-Strong-Pass-2026"


def onboard(client, email="mamma@example.invalid", evidence="documento visto in sede", children=None):
    return client.post(
        "/api/v1/registry/families/onboard",
        {
            "reference": "Famiglia Bianchi",
            "reason": "iscrizione",
            "guardian": {
                "name": "Maria Bianchi",
                "email": email,
                "phone": "+39 333 0000000",
                "relationship": "PARENT",
                "permissions": {"can_request_changes": False},
                "evidence": evidence,
            },
            "children": children if children is not None else [{"display_name": "Luca Bianchi", "level": "2ª media"}],
        },
        format="json",
    )


def token_of(mailoutbox):
    return TOKEN_RE.search(mailoutbox[-1].body).group(1)


def test_onboard_creates_family_guardian_children_and_sends_invite(
    center, mailoutbox, django_capture_on_commit_callbacks
):
    client = api(center)
    with django_capture_on_commit_callbacks(execute=True):
        res = onboard(client)
    assert res.status_code == 201, res.data
    fam, g = res.data["family"], res.data["guardian"]
    assert fam["contact_name"] == "Maria Bianchi"
    assert [c["display_name"] for c in fam["children"]] == ["Luca Bianchi"]
    assert g["status"] == "INVITED" and g["invitation"]["family"] == fam["id"]
    assert g["permissions"] == {
        "can_manage_availability": True,
        "can_receive_notifications": True,
        "can_request_changes": False,
    }
    assert len(mailoutbox) == 1
    listing = client.get("/api/v1/registry/families?expand=1&q=maria").data["results"]
    assert [f["id"] for f in listing] == [fam["id"]]
    assert listing[0]["guardians"][0]["name"] == "Maria Bianchi"

    # Accetta dal link email: account creato, deleghe su tutti i figli, accesso immediato.
    anon = api()
    ok = anon.post("/api/v1/invitations/accept", {"token": token_of(mailoutbox), "password": STRONG}, format="json")
    assert ok.status_code == 201, ok.content
    assert ok.json()["signed_in"] is True
    account = Account.objects.get(email="mamma@example.invalid")
    assert account.first_name == "Maria" and account.last_name == "Bianchi"
    link = GuardianLink.objects.get(account=account)
    assert link.verified and link.can_manage_availability
    detail = GuardianLinkDetail.objects.get(link=link)
    assert detail.verification_method == "documento visto in sede"
    assert detail.can_request_changes is False
    me = anon.get("/api/v1/me")
    assert me.status_code == 200

    # Un figlio aggiunto dopo è subito visibile al genitore.
    res = client.post(
        "/api/v1/registry/students",
        {"family": fam["id"], "display_name": "Sara Bianchi", "reason": "iscrizione"},
        format="json",
    )
    assert res.status_code == 201
    assert {s.display_name for s in visible_students(account)} == {"Luca Bianchi", "Sara Bianchi"}
    full = client.get(f"/api/v1/registry/families/{fam['id']}").data
    assert full["guardians"][0]["status"] == "ACTIVE"
    assert len(full["guardians"][0]["students"]) == 2


def test_family_without_children_and_unverified_relation(center, mailoutbox):
    client = api(center)
    res = onboard(client, evidence="", children=[])
    assert res.status_code == 201, res.data
    g = res.data["guardian"]
    assert g["status"] == "TO_VERIFY" and mailoutbox == []
    # Nessun QR prima della verifica.
    qr = client.post(f"/api/v1/registry/invitations/{g['invitation']['id']}/qr", {}, format="json")
    assert qr.status_code == 409
    ok = client.post(
        f"/api/v1/registry/invitations/{g['invitation']['id']}/verify-relation",
        {"evidence": "telefonata"},
        format="json",
    )
    assert ok.status_code == 200 and ok.data["status"] == "SENT"


def test_qr_link_is_short_lived_and_keeps_email_valid(
    center, mailoutbox, django_capture_on_commit_callbacks
):
    client = api(center)
    with django_capture_on_commit_callbacks(execute=True):
        g = onboard(client).data["guardian"]
    inv_id = g["invitation"]["id"]
    email_token = token_of(mailoutbox)
    before = Invitation.objects.get(pk=inv_id)
    res = client.post(f"/api/v1/registry/invitations/{inv_id}/qr", {}, format="json")
    assert res.status_code == 200 and res["Cache-Control"] == "no-store"
    qr_token = res.data["url"].split("#token=")[1]
    after = Invitation.objects.get(pk=inv_id)
    assert after.version == before.version and after.token_hash == before.token_hash
    assert qr_token not in str(list(AuditEvent.objects.values()))
    # Scaduto il QR, il token non vale più; l'email sì.
    Invitation.objects.filter(pk=inv_id).update(qr_expires_at=timezone.now() - timedelta(seconds=1))
    late = api().post("/api/v1/invitations/accept", {"token": qr_token, "password": STRONG}, format="json")
    assert late.json()["code"] == "INVALID_TOKEN"
    fresh = client.post(f"/api/v1/registry/invitations/{inv_id}/qr", {}, format="json").data["url"].split("#token=")[1]
    ok = api().post("/api/v1/invitations/accept", {"token": fresh, "password": STRONG}, format="json")
    assert ok.status_code == 201 and ok.json()["signed_in"] is True
    # Accettato: anche il link email smette di valere.
    reuse = api().post("/api/v1/invitations/accept", {"token": email_token, "password": STRONG}, format="json")
    assert reuse.json()["code"] == "INVALID_TOKEN"


def test_remove_guardian_revokes_links_and_open_invite(
    center, mailoutbox, django_capture_on_commit_callbacks
):
    client = api(center)
    with django_capture_on_commit_callbacks(execute=True):
        data = onboard(client).data
    fam, g = data["family"], data["guardian"]
    api().post("/api/v1/invitations/accept", {"token": token_of(mailoutbox), "password": STRONG}, format="json")
    second = client.post(
        f"/api/v1/registry/families/{fam['id']}/guardians",
        {"guardian": {"name": "Paolo Bianchi", "email": "papa@example.invalid", "evidence": "doc"}, "reason": "secondo genitore"},
        format="json",
    )
    assert second.status_code == 201, second.data
    dup = client.post(
        f"/api/v1/registry/families/{fam['id']}/guardians",
        {"guardian": {"name": "Paolo", "email": "PAPA@example.invalid"}, "reason": "doppione"},
        format="json",
    )
    assert dup.status_code == 409
    account = Account.objects.get(email="mamma@example.invalid")
    res = client.post(f"/api/v1/registry/family-guardians/{g['id']}/remove", {"reason": "separazione"}, format="json")
    assert res.status_code == 200
    assert list(visible_students(account)) == []
    res = client.post(f"/api/v1/registry/family-guardians/{second.data['id']}/remove", {"reason": "errore"}, format="json")
    assert Invitation.objects.get(pk=second.data["invitation"]["id"]).status == "REVOKED"
    assert client.get(f"/api/v1/registry/families/{fam['id']}").data["guardians"] == []
    assert FamilyGuardian.objects.filter(revoked_at__isnull=False).count() == 2


def test_update_guardian_permissions_follow_links(
    center, mailoutbox, django_capture_on_commit_callbacks
):
    client = api(center)
    with django_capture_on_commit_callbacks(execute=True):
        g = onboard(client).data["guardian"]
    api().post("/api/v1/invitations/accept", {"token": token_of(mailoutbox), "password": STRONG}, format="json")
    res = client.patch(
        f"/api/v1/registry/family-guardians/{g['id']}",
        {"expected_version": FamilyGuardian.objects.get(pk=g["id"]).version, "permissions": {"can_manage_availability": False}, "reason": "richiesta"},
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["permissions"]["can_manage_availability"] is False
    assert GuardianLink.objects.get(account__email="mamma@example.invalid").can_manage_availability is False


def test_onboard_is_atomic_and_center_only(center, outsider):
    client = api(center)
    bad = onboard(client, email="non-una-email")
    assert bad.status_code == 400
    from apps.education.models import Family

    assert not Family.objects.exists()
    assert onboard(api(outsider)).status_code == 403
    assert api(outsider).post("/api/v1/registry/family-guardians/00000000-0000-0000-0000-000000000000/remove", {"reason": "x"}, format="json").status_code == 403
