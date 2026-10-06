"""GAP-H06 / T17: import da template versionato, dry-run, idempotenza, nessun invito da dry-run."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.education.models import Family, GuardianLink, Student
from apps.governance.models import AuditEvent
from apps.identity.models import Account, Invitation
from apps.privacy import importer
from apps.privacy.errors import PrivacyError
from apps.privacy.models import ImportBatch, InvitationTerms, StudentImportKey
from apps.privacy.testing import api, center, outsider, privacy_storage  # noqa: F401

from tests.outbox_mail import mailoutbox  # noqa: E402,F401  (consegna via outbox)

pytestmark = pytest.mark.django_db
TEMPLATE = Path(importer.__file__).parent / "import_templates" / "famiglie-v1.csv"
HEADER = ",".join(importer.TEMPLATES["1"])


def csv_rows(*rows):
    return (HEADER + "\n" + "\n".join(rows) + "\n").encode()


ROWS = csv_rows(
    "FAM-1,Contatto Uno,uno@example.invalid,,S-1,Allievo Uno,Primaria,2015-05-06,"
    "g1@example.invalid,Gen,Uno,PARENT,true,true",
    "FAM-1,Contatto Uno,uno@example.invalid,,S-2,Allievo Due,Primaria,,"
    "g1@example.invalid,Gen,Uno,PARENT,false,true",
    "FAM-2,,,,S-3,Allievo Tre,Secondaria,,,,,,,",
    "FAM-2,,,,S-3,Allievo Tre,Secondaria,,"
    "esistente@example.invalid,Es,Istente,LEGAL_GUARDIAN,true,true",
)


@pytest.fixture
def known_guardian(db):
    return Account.objects.create_user(
        username="esistente", email="esistente@example.invalid", password="x" * 16
    )


def counts():
    return (
        Family.objects.count(),
        Student.objects.count(),
        GuardianLink.objects.count(),
        Account.objects.count(),
        Invitation.objects.count(),
    )


def test_versioned_template_file_matches_definition():
    header = TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    assert header == HEADER


def test_dry_run_writes_nothing_and_never_invites(center, known_guardian):
    before = counts()
    batch = importer.run_import(
        center, ROWS, dry_run=True, verify_links=True, create_invites=True
    )
    assert batch.status == "DRY_RUN"
    assert batch.summary["families_created"] == 2
    assert batch.summary["students_created"] == 3
    assert batch.summary["links_created"] == 1  # solo il tutore con account
    assert batch.summary["invitations_created"] == 2  # simulati, poi rollback
    assert counts() == before
    assert not AuditEvent.objects.filter(category="GUARDIANSHIP").exists()
    assert ImportBatch.objects.get(pk=batch.pk).dry_run is True
    assert AuditEvent.objects.filter(operation="IMPORT_DRY_RUN").count() == 1


def test_dry_run_sends_no_mail(center, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        importer.run_import(
            center, ROWS, dry_run=True, verify_links=True, create_invites=True
        )
    assert mailoutbox == []
    assert Invitation.objects.count() == 0


def test_execute_is_idempotent(center, known_guardian):
    first = importer.run_import(center, ROWS, dry_run=False, verify_links=True)
    assert first.status == "APPLIED", first.errors
    snapshot = counts()
    assert snapshot[:3] == (2, 3, 1)
    assert StudentImportKey.objects.count() == 3
    link = GuardianLink.objects.get(student__import_key__source_key="S-3")
    assert link.verified and link.can_manage_availability
    # Il tutore senza account non viene creato: un invito identity per allievo,
    # in attesa di verifica e senza token inviato.
    assert not Account.objects.filter(email="g1@example.invalid").exists()
    invitations = Invitation.objects.all()
    assert {i.status for i in invitations} == {"PENDING_VERIFICATION"}
    assert invitations.count() == 2
    second_inv = Invitation.objects.get(student__import_key__source_key="S-2")
    assert second_inv.can_manage_availability is False
    assert (
        InvitationTerms.objects.get(invitation=second_inv).import_batch_id == first.pk
    )
    second = importer.run_import(center, ROWS, dry_run=False, verify_links=True)
    assert second.status == "APPLIED"
    assert counts() == snapshot
    assert second.summary["students_existing"] == 4  # righe, non allievi distinti
    assert second.summary["links_existing"] == 1
    assert second.summary["invitations_existing"] == 2


def test_invites_sent_only_with_flags_and_once(
    center, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        batch = importer.run_import(
            center, ROWS, dry_run=False, verify_links=True, create_invites=True
        )
    assert batch.summary["invites_sent"] == 3
    assert Invitation.objects.filter(status="SENT").count() == 3
    assert len(mailoutbox) == 3
    assert not GuardianLink.objects.filter(account__email="g1@example.invalid").exists()
    with django_capture_on_commit_callbacks(execute=True):
        again = importer.run_import(
            center, ROWS, dry_run=False, verify_links=True, create_invites=True
        )
    assert again.summary["invites_sent"] == 0
    assert Invitation.objects.count() == 3 and len(mailoutbox) == 3
    tokens = [e.details for e in AuditEvent.objects.all()]
    assert all("#token=" not in json.dumps(p) for p in tokens)


def test_unverified_links_get_no_invites(center, mailoutbox, known_guardian):
    importer.run_import(center, ROWS, dry_run=False, create_invites=True)
    assert not GuardianLink.objects.filter(verified=True).exists()
    assert not Invitation.objects.exclude(status="PENDING_VERIFICATION").exists()
    assert mailoutbox == []


def test_validation_errors_block_everything(center):
    before = counts()
    bad = csv_rows(
        "FAM-1,,mail-non-valida,,S-1,Nome,,2999-01-01,,,,UNCLE,forse,",
        "FAM-1,,,,,,,,,,,,,",
        "FAM-1,,,,S-9,Nome A,,,,,,,,",
        "FAM-2,,,,S-9,Nome B,,,,,,,,",
    )
    batch = importer.run_import(center, bad, dry_run=False)
    assert batch.status == "INVALID"
    codes = {(e["row"], e.get("field"), e["code"]) for e in batch.errors}
    assert (2, "family_contact_email", "INVALID_EMAIL") in codes
    assert (2, "student_birth_date", "INVALID_DATE") in codes
    assert (2, "guardian_relationship", "INVALID_CHOICE") in codes
    assert (2, "guardian_can_manage_availability", "INVALID_BOOLEAN") in codes
    assert (3, "student_key", "REQUIRED") in codes
    assert (5, "student_key", "INCONSISTENT_DUPLICATE") in codes
    assert counts() == before


def test_header_and_version_checks(center):
    with pytest.raises(PrivacyError) as exc:
        importer.run_import(center, b"a,b\n1,2\n", dry_run=True)
    assert exc.value.code == "HEADER_MISMATCH"
    with pytest.raises(PrivacyError) as exc:
        importer.run_import(center, ROWS, template_version="9")
    assert exc.value.code == "UNKNOWN_TEMPLATE"


def test_conflict_when_student_key_changes_family(center):
    importer.run_import(center, ROWS, dry_run=False)
    moved = csv_rows("FAM-2,,,,S-1,Allievo Uno,Primaria,,,,,,,")
    batch = importer.run_import(center, moved, dry_run=False)
    assert batch.status == "CONFLICT"
    assert batch.errors[0]["code"] == "STUDENT_FAMILY_CHANGED"
    assert Student.objects.get(import_key__source_key="S-1").family.reference == "FAM-1"


def test_command_and_api(center, outsider, tmp_path):
    path = tmp_path / "in.csv"
    path.write_bytes(ROWS)
    out = StringIO()
    call_command("privacy_import", str(path), "--actor", center.username, stdout=out)
    assert json.loads(out.getvalue())["status"] == "DRY_RUN"
    assert Student.objects.count() == 0
    with pytest.raises(CommandError):
        call_command("privacy_import", str(path), "--actor", outsider.username)
    client = api(center)
    response = client.post(
        "/api/v1/privacy/imports",
        {"content": ROWS.decode(), "dry_run": False},
        format="json",
    )
    assert response.status_code == 201 and response.data["status"] == "APPLIED"
    with path.open("rb") as handle:
        multipart = client.post(
            "/api/v1/privacy/imports",
            {"file": handle, "dry_run": "true"},
            format="multipart",
        )
    assert multipart.status_code == 201 and multipart.data["status"] == "DRY_RUN"
    template = client.get("/api/v1/privacy/imports/template/v1")
    assert template.content.decode().strip() == HEADER
    assert api(outsider).get("/api/v1/privacy/imports").status_code == 403
    invalid = client.post(
        "/api/v1/privacy/imports", {"content": "x,y\n"}, format="json"
    )
    assert invalid.status_code == 400
