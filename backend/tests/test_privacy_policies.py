"""Integrazione s1/s4: policy di accesso con riconferma alla maggiore età e permessi delega."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import StudentAccessPolicy
from apps.identity.policies import (
    can_request_student_changes,
    notification_guardian_links,
    visible_students,
)
from apps.privacy import registry
from apps.privacy.models import GuardianLinkDetail
from apps.privacy.testing import center, family, make_account, student  # noqa: F401

pytestmark = pytest.mark.django_db


def guardian_link(center, student, name="tutore", **permissions):
    account = make_account(name, "GUARDIAN")
    link = registry.create_guardian_link(
        center, student=student, account=account, permissions=permissions, reason="r"
    )
    link = registry.verify_guardian_link(
        center, link, expected_version=link.version, method="doc", reason="ok"
    )
    return account, link


def adult(center, student, access):
    StudentAccessPolicy.objects.create(
        student=student,
        adult_confirmed=True,
        guardian_access=access,
        confirmed_by=center,
    )


def set_reconfirmation(link, state, due=None):
    GuardianLinkDetail.objects.filter(link=link).update(
        reconfirmation=state, reconfirmation_due_at=due
    )


def test_consent_required_allows_only_reconfirmed_links(center, student):
    confirmed, link_a = guardian_link(center, student, "conf")
    other, _ = guardian_link(center, student, "altro")
    adult(center, student, "CONSENT_REQUIRED")
    assert not visible_students(confirmed).exists()
    set_reconfirmation(link_a, "CONFIRMED")
    assert list(visible_students(confirmed)) == [student]
    # Il consenso è per singola delega: l'altro tutore resta escluso.
    assert not visible_students(other).exists()


def test_none_excludes_even_reconfirmed_links(center, student):
    account, link = guardian_link(center, student)
    set_reconfirmation(link, "CONFIRMED")
    adult(center, student, "NONE")
    assert not visible_students(account).exists()


def test_declined_reconfirmation_excluded(center, student):
    account, link = guardian_link(center, student)
    set_reconfirmation(link, "DECLINED")
    assert not visible_students(account).exists()


def test_overdue_pending_follows_configured_action(center, student, settings):
    account, link = guardian_link(center, student)
    set_reconfirmation(link, "PENDING", due=timezone.now() - timedelta(days=1))
    settings.PRIVACY_MAJORITY_OVERDUE_ACTION = "REPORT"
    assert list(visible_students(account)) == [student]
    settings.PRIVACY_MAJORITY_OVERDUE_ACTION = "SUSPEND"
    assert not visible_students(account).exists()
    set_reconfirmation(link, "PENDING", due=timezone.now() + timedelta(days=1))
    assert list(visible_students(account)) == [student]


def test_notifications_respect_can_receive_notifications(center, student):
    yes, _ = guardian_link(center, student, "si")
    no, link_no = guardian_link(center, student, "no", can_receive_notifications=False)
    accounts = {link.account_id for link in notification_guardian_links([student.pk])}
    assert accounts == {yes.pk}
    set_reconfirmation(link_no, "CONFIRMED")
    adult(center, student, "NONE")
    assert not notification_guardian_links([student.pk]).exists()


def test_can_request_changes_defaults_to_denied(center, student):
    account, link = guardian_link(center, student)
    assert can_request_student_changes(center, student)
    assert not can_request_student_changes(account, student)
    GuardianLinkDetail.objects.filter(link=link).update(can_request_changes=True)
    assert can_request_student_changes(account, student)
    registry.revoke_guardian_link(center, link, reason="fine")
    assert not can_request_student_changes(account, student)
