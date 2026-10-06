"""Integrazione s1/s4: dati di identity (sessioni, MFA, audit con IP) in diritti e retention."""

from datetime import timedelta

import pytest
from django.db import models
from django.utils import timezone

from apps.identity.models import (
    IdentityAuditEvent,
    RecoveryCode,
    TOTPDevice,
    UserSession,
)
from apps.privacy import retention, subjects
from apps.privacy.models import RetentionPolicy
from apps.privacy.testing import center, make_account  # noqa: F401

pytestmark = pytest.mark.django_db


def identity_event(account, ip="198.51.100.7", days_ago=0):
    event = IdentityAuditEvent.objects.create(
        operation="LOGIN_SUCCEEDED", actor=account, subject=account, ip=ip
    )
    if days_ago:
        # Solo per preparare il dato (retrodatazione): su PostgreSQL passa dalla stessa
        # manutenzione governata della retention (SET LOCAL app.audit_maintenance).
        from apps.privacy.retention import _maintenance_update

        _maintenance_update(
            IdentityAuditEvent.objects.filter(pk=event.pk),
            occurred_at=timezone.now() - timedelta(days=days_ago),
        )
    return event


def with_credentials(account):
    now = timezone.now()
    UserSession.objects.create(
        account=account, last_seen_at=now, ip="198.51.100.7", user_agent="Synth/1.0"
    )
    TOTPDevice.objects.create(account=account, secret="S" * 32, confirmed_at=now)
    RecoveryCode.objects.create(account=account, code_hash="c" * 64)
    identity_event(account)


def test_account_export_includes_security_data(center):
    account = make_account("s4-exp", "GUARDIAN")
    with_credentials(account)
    payload = subjects.collect_account(account)
    assert payload["sessions"][0]["ip"] == "198.51.100.7"
    assert payload["security_audit"][0]["operation"] == "LOGIN_SUCCEEDED"
    text = str(payload)
    assert "S" * 32 not in text and "c" * 64 not in text  # mai segreti MFA


def test_anonymize_account_clears_identity_credentials(center):
    account = make_account("s4-anon", "GUARDIAN")
    with_credentials(account)
    event = identity_event(account)
    subjects.anonymize_account(account, reason="art. 17", actor=center)
    session = UserSession.objects.get(account=account)
    assert session.revoked_at and session.ip is None and session.user_agent == ""
    assert not TOTPDevice.objects.filter(account=account).exists()
    assert not RecoveryCode.objects.filter(account=account).exists()
    # L'evento resta (append-only) ma senza IP.
    assert IdentityAuditEvent.objects.get(pk=event.pk).ip is None
    account.refresh_from_db()
    assert not account.is_active and account.email.startswith("anon-")
    with pytest.raises(TypeError):
        event.delete()


def test_identity_audit_ip_retention(center):
    account = make_account("s4-ip")
    old = identity_event(account, days_ago=120)
    recent = identity_event(account, days_ago=10)
    policy = RetentionPolicy.objects.get(category="identity_audit_ip")
    assert policy.status == "PROPOSED" and policy.action == "MINIMIZE"
    dry = retention.run_retention(dry_run=True, categories=["identity_audit_ip"])
    assert IdentityAuditEvent.objects.get(pk=old.pk).ip  # dry-run non modifica
    assert dry.results
    retention.approve_policy(
        center,
        policy,
        expected_version=policy.version,
        reference="Verbale D09 sintetico",
        reason="approvazione di prova",
    )
    retention.run_retention(dry_run=False, categories=["identity_audit_ip"])
    assert IdentityAuditEvent.objects.get(pk=old.pk).ip is None
    assert IdentityAuditEvent.objects.get(pk=recent.pk).ip == "198.51.100.7"
