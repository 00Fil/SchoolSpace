"""GAP-H11 (parte tecnica): riconferma delle deleghe ai 18 anni, senza revoca silenziosa."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.education.models import GuardianLink, Student
from apps.governance.models import AuditEvent
from apps.identity.policies import visible_students
from apps.privacy import majority, registry
from apps.privacy.errors import Conflict, NotAllowed
from apps.privacy.models import GuardianLinkDetail, StudentProfile
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
def adult_link(center, student):
    today = timezone.localdate()
    StudentProfile.objects.filter(student=student).update(
        birth_date=date(today.year - 18, today.month, 1)
        if today.day > 1
        else date(today.year - 19, 1, 1)
    )
    guardian = make_account("s4-maj-parent", "GUARDIAN")
    link = registry.create_guardian_link(
        center, student=student, account=guardian, reason="r"
    )
    return registry.verify_guardian_link(
        center, link, expected_version=link.version, method="doc", reason="ok"
    )


def test_majority_date_handles_leap_day():
    assert majority.majority_date(date(2008, 2, 29)) == date(2026, 3, 1)
    assert majority.majority_date(date(2008, 5, 4)) == date(2026, 5, 4)


def test_minor_not_flagged(center, student):
    StudentProfile.objects.filter(student=student).update(
        birth_date=timezone.localdate() - timedelta(days=365 * 10)
    )
    guardian = make_account("s4-minor-parent", "GUARDIAN")
    registry.create_guardian_link(center, student=student, account=guardian, reason="r")
    assert majority.run_majority_review()["flagged"] == []


def test_flags_without_silent_revocation(adult_link):
    dry = majority.run_majority_review(dry_run=True)
    assert dry["flagged"] == [str(adult_link.pk)]
    assert (
        GuardianLinkDetail.objects.get(link=adult_link).reconfirmation == "NOT_REQUIRED"
    )
    report = majority.run_majority_review()
    assert report["flagged"] == [str(adult_link.pk)]
    detail = GuardianLinkDetail.objects.get(link=adult_link)
    assert detail.reconfirmation == "PENDING" and detail.reconfirmation_due_at
    link = GuardianLink.objects.get(pk=adult_link.pk)
    assert link.revoked_at is None and link.valid_until is None
    assert list(visible_students(link.account))  # nessuna revoca silenziosa
    assert (
        AuditEvent.objects.filter(operation="LINK_RECONFIRMATION_REQUIRED").count() == 1
    )
    # Idempotente: una seconda esecuzione non segnala di nuovo.
    assert majority.run_majority_review()["flagged"] == []


def test_overdue_report_only_by_default(adult_link):
    majority.run_majority_review()
    later = timezone.now() + timedelta(days=majority.grace_days() + 1)
    report = majority.run_majority_review(now=later)
    assert report["overdue"] == [str(adult_link.pk)] and report["suspended"] == []
    assert GuardianLink.objects.get(pk=adult_link.pk).valid_until is None


def test_overdue_suspend_is_audited(adult_link, settings):
    settings.PRIVACY_MAJORITY_OVERDUE_ACTION = "SUSPEND"
    majority.run_majority_review()
    later = timezone.now() + timedelta(days=majority.grace_days() + 1)
    report = majority.run_majority_review(now=later)
    assert report["suspended"] == [str(adult_link.pk)]
    assert GuardianLink.objects.get(pk=adult_link.pk).valid_until is not None
    assert AuditEvent.objects.filter(operation="LINK_SUSPENDED_MAJORITY").exists()


def test_adult_student_reconfirms_or_declines(center, adult_link, outsider):
    student = adult_link.student
    student_account = make_account("s4-adult", "STUDENT")
    Student.objects.filter(pk=student.pk).update(account=student_account)
    majority.run_majority_review()
    with pytest.raises(NotAllowed):
        majority.reconfirm(outsider, adult_link, confirmation="x", reason="x")
    response = api(student_account).post(
        f"/api/v1/registry/guardian-links/{adult_link.pk}/reconfirm",
        {"confirmation": "confermo l'accesso del genitore", "reason": "riconferma"},
        format="json",
    )
    assert (
        response.status_code == 200 and response.data["reconfirmation"] == "CONFIRMED"
    )
    with pytest.raises(Conflict):
        majority.decline(student_account, adult_link, reason="tardi")
    # Un secondo tutore: lo studente rifiuta e la delega è revocata in modo auditato.
    other = make_account("s4-maj-other", "GUARDIAN")
    link = registry.create_guardian_link(
        center, student=student, account=other, reason="r"
    )
    majority.run_majority_review()
    response = api(student_account).post(
        f"/api/v1/registry/guardian-links/{link.pk}/decline",
        {"reason": "non autorizzo"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["reconfirmation"] == "DECLINED" and response.data["revoked_at"]
    assert AuditEvent.objects.filter(operation="LINK_RECONFIRMATION_DECLINED").exists()


def test_api_and_command(center, adult_link, outsider):
    from io import StringIO

    from django.core.management import call_command

    assert (
        api(outsider)
        .post("/api/v1/privacy/majority-review", {}, format="json")
        .status_code
        == 403
    )
    response = api(center).post("/api/v1/privacy/majority-review", {}, format="json")
    assert response.data["dry_run"] is True and response.data["flagged"]
    out = StringIO()
    call_command("privacy_majority_review", stdout=out)
    assert str(adult_link.pk) in out.getvalue()
    pending = api(center).get("/api/v1/registry/guardian-links?reconfirmation=PENDING")
    assert pending.data["count"] == 1
