"""Scope per comandi non riservati al centro (richieste di modifica, presenze)."""

from django.conf import settings
from config import features
from apps.identity.policies import is_center, active_roles, visible_students
from apps.education.path_services import DomainError
from .services import supported


def authorize_any(actor):
    """Flag sperimentali e database supportato, senza richiedere il ruolo centro."""
    if not actor.is_authenticated or not actor.is_active:
        raise DomainError("FORBIDDEN", "Autenticazione necessaria")
    if not features.calendar_enabled():
        raise DomainError(features.DISABLED_CODE, "Calendario disattivato (FEATURE_CALENDAR)")
    if not supported():
        raise DomainError(
            "POSTGRES_REQUIRED", "Comando disabilitato: PostgreSQL reale necessario"
        )


def is_lesson_tutor(actor, lesson):
    return (
        "TUTOR" in active_roles(actor)
        and lesson.tutor.account_id is not None
        and lesson.tutor.account_id == actor.id
    )


def lesson_relation(actor, lesson):
    """Ruolo dell'attore rispetto alla lezione, o None se fuori scope."""
    if is_center(actor):
        return "CENTER", None
    if is_lesson_tutor(actor, lesson):
        return "TUTOR", None
    participants = set(lesson.participants.values_list("student_id", flat=True))
    visible = set(visible_students(actor).values_list("id", flat=True)) & participants
    if not visible:
        return None, set()
    roles = active_roles(actor)
    return ("GUARDIAN" if "GUARDIAN" in roles else "STUDENT"), visible
