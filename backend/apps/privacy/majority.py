"""Riconferma delle deleghe al compimento dei 18 anni (GAP-H11 parte tecnica, reg2 §Minori).

Al compimento della maggiore età l'accesso dei genitori non è più automatico: il job segnala
le deleghe da riconfermare con lo studente, **senza revoca silenziosa né conservazione
silenziosa**. Alla scadenza del periodo di grazia l'azione è configurabile (D07, da approvare):
``REPORT`` (default prudenziale: solo segnalazione) oppure ``SUSPEND`` (fine validità
auditata della delega, reversibile con una nuova delega).
"""

from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.education.models import GuardianLink
from apps.governance.audit import record
from apps.identity.policies import is_center

from .errors import Conflict, NotAllowed, PrivacyError
from .models import GuardianLinkDetail, StudentProfile
from .registry import require_reason, revoke_guardian_link

AGE = 18
REC = GuardianLinkDetail.Reconfirmation


def majority_date(birth):
    try:
        return birth.replace(year=birth.year + AGE)
    except ValueError:  # 29 febbraio: maggiore età il 1° marzo dell'anno non bisestile
        return date(birth.year + AGE, 3, 1)


def grace_days():
    return int(getattr(settings, "PRIVACY_MAJORITY_GRACE_DAYS", 30))


def overdue_action():
    action = getattr(settings, "PRIVACY_MAJORITY_OVERDUE_ACTION", "REPORT")
    if action not in ("REPORT", "SUSPEND"):
        raise PrivacyError("INVALID_SETTING", "PRIVACY_MAJORITY_OVERDUE_ACTION")
    return action


def run_majority_review(*, today=None, now=None, dry_run=False, actor=None):
    now = now or timezone.now()
    today = today or timezone.localdate(now)
    report = {"flagged": [], "overdue": [], "suspended": [], "dry_run": dry_run}
    adults = [
        p.student_id
        for p in StudentProfile.objects.filter(
            birth_date__isnull=False, anonymized_at__isnull=True
        )
        if majority_date(p.birth_date) <= today
    ]
    links = GuardianLink.objects.filter(student_id__in=adults, revoked_at__isnull=True)
    with transaction.atomic():
        for link in links.select_for_update():
            if link.valid_until and link.valid_until <= now:
                continue
            detail, _ = GuardianLinkDetail.objects.get_or_create(link=link)
            if detail.reconfirmation == REC.NOT_REQUIRED and (
                detail.reconfirmed_at is None
            ):
                report["flagged"].append(str(link.pk))
                if not dry_run:
                    detail.reconfirmation = REC.PENDING
                    detail.reconfirmation_flagged_at = now
                    detail.reconfirmation_due_at = now + timedelta(days=grace_days())
                    detail.save()
                    record(
                        "GUARDIANSHIP",
                        "LINK_RECONFIRMATION_REQUIRED",
                        actor=actor,
                        obj=link,
                        command="privacy_majority_review",
                        purpose="maggiore età",
                        details={"due_at": detail.reconfirmation_due_at},
                    )
            elif (
                detail.reconfirmation == REC.PENDING
                and detail.reconfirmation_due_at
                and detail.reconfirmation_due_at <= now
            ):
                report["overdue"].append(str(link.pk))
                if not dry_run and overdue_action() == "SUSPEND":
                    link.valid_until = max(now, link.valid_from + timedelta(seconds=1))
                    link.save()
                    record(
                        "GUARDIANSHIP",
                        "LINK_SUSPENDED_MAJORITY",
                        actor=actor,
                        obj=link,
                        command="privacy_majority_review",
                        purpose="maggiore età",
                        reason="riconferma non ricevuta entro il termine",
                    )
                    report["suspended"].append(str(link.pk))
        if not dry_run:
            record(
                "GUARDIANSHIP",
                "MAJORITY_REVIEW_RUN",
                actor=actor,
                command="privacy_majority_review",
                details={
                    k: len(v) if isinstance(v, list) else v for k, v in report.items()
                },
            )
    return report


def _authorize(actor, link):
    if is_center(actor):
        return
    student = link.student
    if student.account_id and student.account_id == actor.pk:
        return
    raise NotAllowed("NOT_ALLOWED", "Solo il centro o lo studente maggiorenne")


@transaction.atomic
def reconfirm(actor, link, *, confirmation, reason):
    """Lo studente maggiorenne (o il centro, che lo ha sentito) conferma la delega."""
    reason = require_reason(reason)
    confirmation = require_reason(confirmation)
    link = GuardianLink.objects.select_for_update().get(pk=link.pk)
    _authorize(actor, link)
    detail, _ = GuardianLinkDetail.objects.get_or_create(link=link)
    if link.revoked_at or detail.reconfirmation != REC.PENDING:
        raise Conflict("NOT_PENDING", "Nessuna riconferma in sospeso")
    detail.reconfirmation = REC.CONFIRMED
    detail.reconfirmed_at = timezone.now()
    detail.reconfirmed_by = actor
    detail.save()
    record(
        "GUARDIANSHIP",
        "LINK_RECONFIRMED",
        actor=actor,
        obj=link,
        reason=reason,
        purpose="maggiore età",
        details={"confirmation": confirmation},
    )
    return link


@transaction.atomic
def decline(actor, link, *, reason):
    reason = require_reason(reason)
    link = GuardianLink.objects.select_for_update().get(pk=link.pk)
    _authorize(actor, link)
    detail, _ = GuardianLinkDetail.objects.get_or_create(link=link)
    if link.revoked_at or detail.reconfirmation != REC.PENDING:
        raise Conflict("NOT_PENDING", "Nessuna riconferma in sospeso")
    revoke_guardian_link(actor, link, reason=reason, system=True)
    GuardianLinkDetail.objects.filter(pk=detail.pk).update(reconfirmation=REC.DECLINED)
    record(
        "GUARDIANSHIP",
        "LINK_RECONFIRMATION_DECLINED",
        actor=actor,
        obj=link,
        reason=reason,
        purpose="maggiore età",
    )
    return link
