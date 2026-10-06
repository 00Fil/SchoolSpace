"""GAP-H04: matrice D09 configurabile, job con dry-run e ricevuta, audit append-only."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.education.models import Family, Student
from apps.governance.audit import record, redact
from apps.governance.models import AuditEvent, CommandReceipt
from apps.identity.models import Invitation
from apps.privacy import retention
from apps.privacy.errors import PrivacyError
from apps.privacy.models import ImportBatch, RetentionPolicy, RetentionRun
from apps.privacy.testing import (  # noqa: F401
    api,
    center,
    make_account,
    outsider,
    privacy_storage,
)

pytestmark = pytest.mark.django_db


def old_receipt(actor, days):
    receipt = CommandReceipt.objects.create(
        actor=actor, operation="x", key=f"k{days}", body_hash="0" * 64, response={}
    )
    CommandReceipt.objects.filter(pk=receipt.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )
    return receipt


def approve(actor, category):
    policy = RetentionPolicy.objects.get(category=category)
    return retention.approve_policy(
        actor,
        policy,
        expected_version=policy.version,
        reference="Verbale D09 sintetico",
        reason="approvazione di prova",
    )


def result(run, category):
    return next(r for r in run.results if r["category"] == category)


def test_default_matrix_is_seeded_as_to_be_approved():
    categories = set(RetentionPolicy.objects.values_list("category", flat=True))
    assert {c[0] for c in retention.DEFAULT_MATRIX} <= categories
    assert set(RetentionPolicy.objects.values_list("status", flat=True)) == {"PROPOSED"}
    idem = RetentionPolicy.objects.get(category="idempotency_keys")
    assert idem.duration_days == 30 and idem.action == "DELETE"
    assert RetentionPolicy.objects.get(category="audit_events").duration_days is None
    assert retention.seed_default_matrix() == 0  # idempotente


def test_dry_run_counts_without_changes_and_signs_receipt(center):
    old_receipt(center, 40)
    old_receipt(center, 5)
    run = retention.run_retention(actor=center, dry_run=True)
    entry = result(run, "idempotency_keys")
    assert entry["outcome"] == "DRY_RUN" and entry["eligible"] == 1
    assert CommandReceipt.objects.count() == 2
    assert result(run, "audit_events")["outcome"] == "DURATION_UNDEFINED"
    assert result(run, "diagnostic_logs")["outcome"] == "EXTERNAL"
    assert len(run.receipt_hash) == 64
    assert RetentionRun.objects.get(pk=run.pk).receipt_hash == run.receipt_hash
    assert AuditEvent.objects.filter(operation="RETENTION_DRY_RUN").count() == 1


def test_execution_requires_approval(center):
    old_receipt(center, 40)
    run = retention.run_retention(actor=center, dry_run=False)
    assert result(run, "idempotency_keys")["outcome"] == "NOT_APPROVED"
    assert CommandReceipt.objects.count() == 1
    approve(center, "idempotency_keys")
    run = retention.run_retention(actor=center, dry_run=False)
    entry = result(run, "idempotency_keys")
    assert entry["outcome"] == "APPLIED" and entry["affected"] == 1
    assert CommandReceipt.objects.count() == 0
    event = AuditEvent.objects.get(
        operation="RETENTION_EXECUTED", object_id=str(run.pk)
    )
    assert event.details["applied"] == {"idempotency_keys": 1}
    assert event.details["receipt_hash"] == run.receipt_hash


def test_executed_run_goes_to_external_ledger(center, privacy_storage):
    from apps.privacy import ledger

    approve(center, "idempotency_keys")
    run = retention.run_retention(actor=center, dry_run=False)
    entries = ledger.read_entries()
    assert entries[-1]["event"] == "RETENTION_EXECUTED"
    assert entries[-1]["receipt"] == run.receipt_hash
    assert ledger.verify_chain() == (True, None)


def test_policy_update_resets_approval_and_validates(center):
    policy = approve(center, "invitations")
    assert policy.status == "APPROVED" and policy.approved_by == center
    policy = retention.update_policy(
        center,
        policy,
        expected_version=policy.version,
        changes={"duration_days": 14},
        reason="nuova proposta",
    )
    assert policy.status == "PROPOSED" and policy.approved_at is None
    with pytest.raises(PrivacyError):
        retention.update_policy(
            center,
            policy,
            expected_version=policy.version,
            changes={"category": "x"},
            reason="no",
        )
    with pytest.raises(PrivacyError):
        approve(center, "audit_events")  # durata non definita


def test_retention_api_permissions_and_flow(center, outsider):
    assert api(outsider).get("/api/v1/privacy/retention-policies").status_code == 403
    client = api(center)
    listing = client.get("/api/v1/privacy/retention-policies").data["results"]
    policy = next(p for p in listing if p["category"] == "import_reports")
    stale = client.patch(
        f"/api/v1/privacy/retention-policies/{policy['id']}",
        {"expected_version": 99, "duration_days": 60, "reason": "x"},
        format="json",
    )
    assert stale.status_code == 409
    patched = client.patch(
        f"/api/v1/privacy/retention-policies/{policy['id']}",
        {"expected_version": policy["version"], "duration_days": 60, "reason": "x"},
        format="json",
    )
    assert patched.status_code == 200 and patched.data["duration_days"] == 60
    approved = client.post(
        f"/api/v1/privacy/retention-policies/{policy['id']}/approve",
        {
            "expected_version": patched.data["version"],
            "reference": "Verbale",
            "reason": "ok",
        },
        format="json",
    )
    assert approved.status_code == 200 and approved.data["status"] == "APPROVED"
    batch = ImportBatch.objects.create(
        template_version="1",
        file_sha256="0" * 64,
        dry_run=False,
        status="APPLIED",
        errors=[{"row": 2, "code": "X"}],
    )
    ImportBatch.objects.filter(pk=batch.pk).update(
        created_at=timezone.now() - timedelta(days=61)
    )
    run = client.post(
        "/api/v1/privacy/retention-runs",
        {"dry_run": False, "categories": ["import_reports"]},
        format="json",
    )
    assert run.status_code == 201
    assert run.data["results"][0]["affected"] == 1
    batch.refresh_from_db()
    assert batch.errors == [] and batch.minimized_at
    unknown = client.post(
        "/api/v1/privacy/retention-runs", {"categories": ["nope"]}, format="json"
    )
    assert unknown.status_code == 400
    assert client.get("/api/v1/privacy/retention-runs").data["count"] == 1


def test_invitations_purge_keeps_pending_valid(center):
    now = timezone.now()
    old = now - timedelta(days=60)
    student = Student.objects.create(family=Family.objects.create(reference="F-inv"))
    common = {"role": "GUARDIAN", "student": student, "created_by": center}
    accepted = Invitation.objects.create(
        email="a@example.invalid", status="ACCEPTED", accepted_at=old, **common
    )
    revoked = Invitation.objects.create(
        email="b@example.invalid", status="REVOKED", revoked_at=old, **common
    )
    pending = Invitation.objects.create(email="c@example.invalid", **common)
    fresh = Invitation.objects.create(
        email="d@example.invalid",
        status="ACCEPTED",
        accepted_at=now,
        **common,
    )
    approve(center, "invitations")
    retention.run_retention(dry_run=False, categories=["invitations"])
    remaining = set(Invitation.objects.values_list("pk", flat=True))
    assert remaining == {pending.pk, fresh.pk}
    assert accepted.pk not in remaining and revoked.pk not in remaining


def test_revoked_accounts_are_minimized(center):
    from apps.identity.models import RoleGrant

    gone = make_account("s4-gone", "GUARDIAN", first_name="Nome", last_name="Cognome")
    RoleGrant.objects.filter(account=gone).update(
        revoked_at=timezone.now() - timedelta(days=100)
    )
    type(gone).objects.filter(pk=gone.pk).update(
        is_active=False, last_login=timezone.now() - timedelta(days=100)
    )
    recent = make_account("s4-recent", "GUARDIAN")
    RoleGrant.objects.filter(account=recent).update(revoked_at=timezone.now())
    type(recent).objects.filter(pk=recent.pk).update(is_active=False)
    approve(center, "revoked_accounts")
    run = retention.run_retention(dry_run=False, categories=["revoked_accounts"])
    assert result(run, "revoked_accounts")["affected"] == 1
    gone.refresh_from_db()
    recent.refresh_from_db()
    assert gone.email.endswith("@anonimizzato.invalid") and gone.first_name == ""
    assert not recent.email.endswith("@anonimizzato.invalid")


def test_audit_minimization_after_approval(center):
    event = record("ADMIN", "OLD", actor=center, details={"field": "x"})
    AuditEvent.objects.filter(pk=event.pk)  # nessuna modifica via ORM consentita
    policy = RetentionPolicy.objects.get(category="audit_events")
    retention.update_policy(
        center,
        policy,
        expected_version=policy.version,
        changes={"duration_days": 0},
        reason="test",
    )
    approve(center, "audit_events")
    retention.run_retention(dry_run=False, categories=["audit_events"])
    minimized = AuditEvent.objects.get(pk=event.pk)
    assert minimized.actor is None and minimized.details == {"minimized": True}
    assert minimized.operation == "OLD"


def test_command_defaults_to_dry_run(center):
    old_receipt(center, 40)
    approve(center, "idempotency_keys")
    out = StringIO()
    call_command("privacy_retention", stdout=out)
    data = json.loads(out.getvalue())
    assert data["dry_run"] is True and CommandReceipt.objects.count() == 1
    out = StringIO()
    call_command(
        "privacy_retention",
        "--execute",
        "--category",
        "idempotency_keys",
        "--actor",
        center.username,
        stdout=out,
    )
    data = json.loads(out.getvalue())
    assert data["results"][0]["outcome"] == "APPLIED"
    assert CommandReceipt.objects.count() == 0


def test_audit_event_is_append_only(center):
    event = record("ADMIN", "X", actor=center)
    with pytest.raises(PermissionError):
        event.save()
    with pytest.raises(PermissionError):
        event.delete()
    with pytest.raises(PermissionError):
        AuditEvent.objects.filter(pk=event.pk).update(operation="Y")
    with pytest.raises(PermissionError):
        AuditEvent.objects.all().delete()


def test_redaction_of_synthetic_secrets():
    """T42: segreti redatti nell'audit."""
    data = redact(
        {
            "password": "Synthetic-Pass",
            "token": "abc",
            "video_url": "https://video.example.invalid/room/1",
            "notes": "nota libera sensibile",
            "nested": [{"api_key": "k", "session_id": "s", "ok": "valore"}],
            "free": "vedi https://example.invalid/x e token tLkq0Q9yQxS1C3zXr8wqmFQ2xkQ0HCw7f9b4",
            "student": "1d9c8f8e-2b9b-4c1e-9d2f-8a1b2c3d4e5f",
            "sha": "a" * 64,
        }
    )
    assert data["password"] == data["token"] == data["video_url"] == "[REDATTO]"
    assert data["notes"] == "[REDATTO]"
    assert data["nested"][0]["api_key"] == "[REDATTO]"
    assert data["nested"][0]["ok"] == "valore"
    assert "https://" not in data["free"] and "tLkq0Q9" not in data["free"]
    assert data["student"] == "1d9c8f8e-2b9b-4c1e-9d2f-8a1b2c3d4e5f"
    assert data["sha"] == "a" * 64
