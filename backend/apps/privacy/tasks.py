"""Job periodici privacy (Celery beat). Idempotenti; nessun invio esterno."""

from celery import shared_task


@shared_task(name="apps.privacy.tasks.majority_review", ignore_result=True)
def majority_review():
    from .majority import run_majority_review

    run_majority_review()


@shared_task(name="apps.privacy.tasks.retention", ignore_result=True)
def retention():
    """Esegue solo le categorie APPROVED; le altre finiscono in ricevuta come NOT_APPROVED."""
    from django.conf import settings

    from .retention import run_retention

    run_retention(dry_run=not getattr(settings, "PRIVACY_RETENTION_AUTORUN", False))
