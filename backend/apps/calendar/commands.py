"""Infrastruttura comune dei comandi s2-calendario: lock, ricevute, audit ed eventi.

Ogni comando: autorizzazione ripetuta sotto lock globale della revisione, attore
riletto con lock, CommandReceipt (replay esatto, corpo diverso → 409), audit
append-only ed evento di dominio nello stesso commit; nessuna chiamata esterna.
"""

from django.db import transaction
from apps.identity.models import Account
from apps.education.path_services import DomainError, Conflict
from apps.scheduling.revision import lock_revision
from .models import CalendarAudit, CalendarEvent
from . import services
from .services import authorize, receipt, record
from apps.reasons import reason_or_default


def now():
    """Indiretto su services.now: un solo orologio, sostituibile nei test."""
    return services.now()


class Command:
    """Contesto di un comando idempotente (da usare dentro transaction.atomic)."""

    def __init__(self, actor, operation, key, body, authorizer=authorize):
        if not transaction.get_connection().in_atomic_block:
            raise RuntimeError("Comando fuori transazione")
        authorizer(actor)
        self.revision = lock_revision()
        self.actor = Account.objects.select_for_update().get(pk=actor.id)
        authorizer(self.actor)
        self.operation = operation
        self.key = key
        self.digest, previous = receipt(self.actor, operation, key, body)
        self.replay = previous.response if previous else None

    def done(self, response):
        return record(self.actor, self.operation, self.key, self.digest, response)


def audit(actor, operation, reason, *, lesson=None, obj=None, before=None, after=None):
    return CalendarAudit.objects.create(
        actor=actor if actor is not None and not isinstance(actor, str) else None,
        system_actor=actor if isinstance(actor, str) else "",
        operation=operation,
        lesson=lesson,
        publication=lesson.publication if lesson is not None else None,
        object_type=type(obj).__name__ if obj is not None else "",
        object_id=obj.pk if obj is not None else None,
        reason=(reason or "")[:200],
        before=before or {},
        after=after or {},
    )


def event(kind, key, payload):
    """Registro di dominio interno; le notifiche passano da notifications (outbox s3)."""
    return CalendarEvent.objects.get_or_create(
        event_key=key[:100],
        defaults={"kind": kind[:30], "payload": {**payload, "experimental": True}},
    )[0]


def require_reason(command):
    """Il motivo non si chiede più: se manca si registra il testo standard."""
    return reason_or_default(command.get("reason"))


def check_version(obj, expected, code="VERSION_CONFLICT"):
    if obj.version != expected:
        raise Conflict(code, "Oggetto cambiato: ricaricare")


__all__ = [
    "Command",
    "audit",
    "event",
    "require_reason",
    "check_version",
    "now",
    "DomainError",
    "Conflict",
]
