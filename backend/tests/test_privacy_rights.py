"""GAP-H05 / FR24: accesso, rettifica, cancellazione governata, portabilità e registro esterno."""

import csv
import io
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.governance.models import AuditEvent
from apps.privacy import ledger, reconcile, registry
from apps.privacy import requests as rights
from apps.privacy.errors import Conflict, PrivacyError
from apps.privacy.models import FamilyProfile, PrivacyRequest, StudentProfile
from apps.privacy.testing import (  # noqa: F401
    api,
    center,
    family,
    make_account,
    outsider,
    privacy_storage,
    student,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def guardian(center, student):
    account = make_account(
        "s4-parent", "GUARDIAN", first_name="Genitore", last_name="Sintetico"
    )
    link = registry.create_guardian_link(
        center, student=student, account=account, reason="r"
    )
    registry.verify_guardian_link(
        center, link, expected_version=link.version, method="doc", reason="ok"
    )
    FamilyProfile.objects.create(
        family=student.family,
        contact_name="Genitore Sintetico",
        contact_email="parent@example.invalid",
    )
    return account


def opened(center, kind, subject, subject_type="STUDENT"):
    req = rights.open_request(
        center,
        kind=kind,
        subject_type=subject_type,
        subject_id=subject.pk,
        channel="email dedicata",
        requester_role="genitore",
    )
    return rights.verify_identity(center, req, method="documento e delega verificata")


def download(user, export, token):
    return api(user).post(
        f"/api/v1/privacy/exports/{export['id']}/download",
        {"token": token},
        format="json",
    )


def test_request_register_deadlines_and_extension(center, student):
    req = rights.open_request(
        center,
        kind="ACCESS",
        subject_type="STUDENT",
        subject_id=student.pk,
        channel="pec",
        requester_role="genitore",
    )
    assert req.due_at.month == rights.add_months(req.received_at, 1).month
    assert req.subject_pseudonym and str(student.pk) not in req.subject_pseudonym
    with pytest.raises(Conflict):
        rights.fulfil_export(center, req, audience=center)  # identità non verificata
    req = rights.extend(center, req, reason="richiesta complessa")
    assert req.status == "EXTENDED"
    assert req.due_at == rights.add_months(rights.add_months(req.received_at, 1), 2)
    with pytest.raises(Conflict):
        rights.extend(center, req, reason="ancora")
    assert (
        rights.add_months(
            timezone.datetime(2027, 1, 31, tzinfo=timezone.get_current_timezone()), 1
        ).day
        == 28
    )


def test_access_export_json_and_csv(center, student, guardian):
    client = api(center)
    req = opened(center, "ACCESS", student)
    response = client.post(
        f"/api/v1/privacy/requests/{req.pk}/export",
        {"audience": str(guardian.pk), "format": "json"},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["request"]["status"] == "COMPLETED"
    export = response.data["export"]
    # Il centro non è l'audience: non può scaricare.
    assert download(center, export, export["token"]).status_code == 403
    file = download(guardian, export, export["token"])
    assert file.status_code == 200
    assert file["Cache-Control"] == "no-store"
    assert "attachment" in file["Content-Disposition"]
    body = json.loads(file.content)
    assert body["schema"] == "privacy-export/1"
    data = body["data"]
    assert data["student"]["display_name"] == "Studente Sintetico"
    assert data["family"]["profile"]["contact_email"] == "parent@example.invalid"
    assert data["guardian_links"][0]["guardian_email"] == guardian.email
    assert "privacy.studentprofile" in data["related"]
    assert "password" not in file.content.decode()
    # CSV per una seconda richiesta di accesso.
    req2 = opened(center, "ACCESS", student)
    response = client.post(
        f"/api/v1/privacy/requests/{req2.pk}/export",
        {"audience": str(guardian.pk), "format": "csv"},
        format="json",
    )
    export = response.data["export"]
    file = download(guardian, export, export["token"])
    rows = list(csv.reader(io.StringIO(file.content.decode("utf-8-sig"))))
    assert rows[0] == ["section", "record", "field", "value"]
    assert [
        "data.student",
        str(student.pk),
        "display_name",
        "Studente Sintetico",
    ] in rows


def test_portability_requires_json_and_account_export(center, guardian):
    req = opened(center, "PORTABILITY", guardian, subject_type="ACCOUNT")
    with pytest.raises(PrivacyError):
        rights.fulfil_export(center, req, audience=guardian, fmt="csv")
    export, token = rights.fulfil_export(center, req, audience=guardian, fmt="json")
    from apps.privacy.exports import consume

    _, content = consume(export.pk, user=guardian, token=token)
    data = json.loads(content)["data"]
    assert data["account"]["email"] == guardian.email
    assert "password" not in data["account"]
    assert data["guardian_links"][0]["student_name"] == "Studente Sintetico"
    assert {"GUARDIAN"} == {g["role"] for g in data["role_grants"]}


def test_rectification_is_audited(center, student):
    req = opened(center, "RECTIFICATION", student)
    response = api(center).post(
        f"/api/v1/privacy/requests/{req.pk}/rectify",
        {
            "changes": {"display_name": "Nome Corretto", "birth_date": "2011-02-03"},
            "reason": "errore di battitura",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["outcome"] == "RECTIFIED"
    student.refresh_from_db()
    assert student.display_name == "Nome Corretto"
    assert str(StudentProfile.objects.get(student=student).birth_date) == "2011-02-03"
    event = AuditEvent.objects.get(operation="RECTIFIED")
    assert event.details["changed_fields"] == ["birth_date", "display_name"]
    bad = opened(center, "RECTIFICATION", student)
    response = api(center).post(
        f"/api/v1/privacy/requests/{bad.pk}/rectify",
        {"changes": {"active": True}, "reason": "x"},
        format="json",
    )
    assert response.status_code == 400


def test_erasure_anonymizes_and_register_survives(
    center, student, guardian, django_capture_on_commit_callbacks
):
    student_account = make_account("s4-student-acc", "STUDENT")
    Student.objects.filter(pk=student.pk).update(account=student_account)
    req = opened(center, "ERASURE", student)
    with django_capture_on_commit_callbacks(execute=True):
        response = api(center).post(
            f"/api/v1/privacy/requests/{req.pk}/erase",
            {"motivation": "presenze conservate per contestazioni (D09)"},
            format="json",
        )
    assert response.status_code == 200, response.data
    student.refresh_from_db()
    assert student.display_name.startswith("Studente anonimizzato ")
    assert not student.active and student.level == ""
    assert StudentProfile.objects.get(student=student).anonymized_at
    student_account.refresh_from_db()
    assert not student_account.is_active
    assert student_account.email.endswith("@anonimizzato.invalid")
    assert not student_account.has_usable_password()
    assert GuardianLink.objects.get(student=student).revoked_at is not None
    family = Family.objects.get(pk=student.family_id)
    assert family.reference.startswith("ANON-")
    assert FamilyProfile.objects.get(family=family).contact_email == ""
    # Il registro sopravvive: nessuna FK verso l'interessato.
    kept = PrivacyRequest.objects.get(pk=req.pk)
    assert kept.outcome == "ANONYMIZED" and "D09" in kept.motivation
    events = [e["event"] for e in ledger.read_entries()]
    assert "REQUEST_COMPLETED" in events and "LINK_REVOKED" in events
    assert ledger.verify_chain() == (True, None)
    assert "Studente Sintetico" not in ledger.ledger_path().read_text()


def test_restore_reconciliation_reapplies_erasure_and_revocation(
    center, student, guardian, django_capture_on_commit_callbacks
):
    req = opened(center, "ERASURE", student)
    with django_capture_on_commit_callbacks(execute=True):
        rights.fulfil_erasure(center, req, motivation="richiesta art. 17")
    # Simula un restore a un istante precedente la cancellazione.
    Student.objects.filter(pk=student.pk).update(display_name="Studente Sintetico")
    StudentProfile.objects.filter(student=student).update(anonymized_at=None)
    GuardianLink.objects.filter(student=student).update(revoked_at=None)
    PrivacyRequest.objects.filter(pk=req.pk).delete()
    actions = reconcile.plan()
    kinds = sorted(a["action"] for a in actions)
    assert kinds == ["ANONYMIZE", "MISSING_REQUEST", "REVOKE_LINK"]
    out = StringIO()
    with django_capture_on_commit_callbacks(execute=True):
        call_command("privacy_reconcile", "--apply", stdout=out)
    student.refresh_from_db()
    assert student.display_name.startswith("Studente anonimizzato ")
    assert GuardianLink.objects.get(student=student).revoked_at is not None
    remaining = [a["action"] for a in reconcile.plan()]
    assert remaining == ["MISSING_REQUEST"]


def test_tampered_ledger_blocks_reconciliation(center, student):
    ledger.append("LINK_REVOKED", link="x", student=str(student.pk))
    ledger.append("LINK_REVOKED", link="y", student=str(student.pk))
    path = ledger.ledger_path()
    path.write_text(path.read_text().replace('"link": "x"', '"link": "z"'))
    assert ledger.verify_chain() == (False, 0)
    with pytest.raises(Exception):
        call_command("privacy_reconcile", stdout=StringIO())
    with pytest.raises(Exception):
        call_command("privacy_ledger_verify", stdout=StringIO())


def test_manual_close_and_reject(center, student):
    req = opened(center, "OBJECTION", student)
    response = api(center).post(
        f"/api/v1/privacy/requests/{req.pk}/close",
        {"outcome": "OBJECTION_REJECTED", "motivation": "base contrattuale 6.1.b"},
        format="json",
    )
    assert response.status_code == 200 and response.data["status"] == "COMPLETED"
    again = api(center).post(
        f"/api/v1/privacy/requests/{req.pk}/reject",
        {"motivation": "x"},
        format="json",
    )
    assert again.status_code == 409
    other = rights.open_request(
        center,
        kind="ACCESS",
        subject_type="STUDENT",
        subject_id=student.pk,
        channel="email",
        requester_role="terzo",
    )
    rejected = api(center).post(
        f"/api/v1/privacy/requests/{other.pk}/reject",
        {"motivation": "identità non dimostrata"},
        format="json",
    )
    assert rejected.data["status"] == "REJECTED"


def test_request_api_validation_and_permissions(center, outsider, student):
    client = api(center)
    assert api(outsider).get("/api/v1/privacy/requests").status_code == 403
    bad = client.post(
        "/api/v1/privacy/requests",
        {
            "kind": "ACCESS",
            "subject_type": "STUDENT",
            "subject_id": "00000000-0000-0000-0000-000000000000",
            "channel": "email",
            "requester_role": "genitore",
        },
        format="json",
    )
    assert bad.status_code == 400 and bad.data["code"] == "SUBJECT_NOT_FOUND"
    ok = client.post(
        "/api/v1/privacy/requests",
        {
            "kind": "ERASURE",
            "subject_type": "STUDENT",
            "subject_id": str(student.pk),
            "channel": "email",
            "requester_role": "genitore",
        },
        format="json",
    )
    assert ok.status_code == 201
    early = client.post(
        f"/api/v1/privacy/requests/{ok.data['id']}/erase",
        {"motivation": "x"},
        format="json",
    )
    assert early.status_code == 409 and early.data["code"] == "IDENTITY_NOT_VERIFIED"
    verify = client.post(
        f"/api/v1/privacy/requests/{ok.data['id']}/verify-identity",
        {"method": "documento"},
        format="json",
    )
    assert verify.data["status"] == "VERIFIED"
    assert client.get("/api/v1/privacy/requests?status=open").data["count"] == 1
    assert client.get("/api/v1/privacy/requests?status=overdue").data["count"] == 0
