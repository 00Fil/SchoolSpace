from celery import shared_task
from django.conf import settings
from config import features


@shared_task(name="apps.calendar.tasks.propose_horizon")
def propose_horizon_task():
    """No-op se calendario o operatore non configurati (CALENDAR_HORIZON_ACTOR)."""
    username = getattr(settings, "CALENDAR_HORIZON_ACTOR", "")
    if not (features.calendar_enabled() and username):
        return "DISABLED"
    from apps.identity.models import Account
    from apps.identity.policies import is_center
    from .lifecycle import propose_horizon

    actor = Account.objects.filter(username=username).first()
    if not actor or not is_center(actor):
        return "ACTOR_INVALID"
    return [row.state for row in propose_horizon(actor)]


@shared_task(name="apps.calendar.tasks.detect_conflicts")
def detect_conflicts_task():
    if not features.calendar_enabled():
        return "DISABLED"
    from django.db import transaction
    from .conflicts import detect_conflicts

    with transaction.atomic():
        return len(detect_conflicts())
