"""Rilevazione automatica di ConflictCase dopo modifiche ai dati (FR18, T41).

Solo post-commit e solo se esistono lezioni future pubblicate; mai modifiche al
calendario. Gli update massivi (QuerySet.update) non emettono segnali: il comando
``detect_calendar_conflicts`` e il job dell'orizzonte coprono questi casi."""

from django.conf import settings
from config import features
from django.db import transaction
from django.db.models.signals import post_save, post_delete


def _schedule(instance, **kwargs):
    if not getattr(settings, "CALENDAR_AUTO_CONFLICT_DETECTION", False):
        return
    if not features.calendar_enabled():
        return
    from .conflicts import on_data_change

    tutor = getattr(instance, "tutor_id", None)
    student = getattr(instance, "student_id", None)
    everyone = tutor is None and student is None
    transaction.on_commit(
        lambda: on_data_change(
            tutor_ids=[tutor] if tutor else [],
            student_ids=[student] if student else [],
            everyone=everyone,
        )
    )


def connect():
    from apps.availability.models import (
        AvailabilityRule,
        AvailabilityException,
        AvailabilityDeclaration,
        AvailabilityConflict,
    )
    from apps.scheduling.models import Closure, ServiceWindow

    for model in (
        AvailabilityRule,
        AvailabilityException,
        AvailabilityDeclaration,
        AvailabilityConflict,
        Closure,
        ServiceWindow,
    ):
        uid = f"calendar-conflicts-{model._meta.label_lower}"
        post_save.connect(_schedule, sender=model, dispatch_uid=uid + "-save")
        post_delete.connect(_schedule, sender=model, dispatch_uid=uid + "-delete")
