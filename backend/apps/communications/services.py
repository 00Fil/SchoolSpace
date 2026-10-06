"""API pubblica del modulo comunicazioni.

Uso dagli altri stream, *dentro* la transazione del cambiamento di dominio::

    from apps.communications.services import emit, Recipient

    with transaction.atomic():
        ...  # scritture di dominio
        emit(
            "absence.recorded",
            {"absence_id": str(absence.id), "start_at": absence.start_at.isoformat()},
            [Recipient(guardian_account, {"student_names": [student.display_name]})],
            idempotency_key=f"absence:{absence.id}:v{absence.version}",
        )

``emit`` scrive ``OutboxEvent`` e le ``Delivery`` nello stesso commit; l'accodamento a
Celery avviene solo dopo il commit e, se si perde (crash, broker assente), il reconciler
lo recupera (T22). La stessa chiave con lo stesso payload è un replay senza effetti; con
un payload diverso solleva ``OutboxConflict``.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .models import (
    Category,
    Channel,
    ChannelPreference,
    Delivery,
    DeliveryAttempt,
    DeliveryStatus,
    OutboxEvent,
)
from .payloads import PayloadNotMinimal, check_context, check_payload

__all__ = [
    "emit",
    "Recipient",
    "OutboxConflict",
    "PayloadNotMinimal",
    "MarketingDisabled",
    "preferences_for",
    "set_preference",
]

EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
KEY = re.compile(r"^[\x21-\x7e]{1,200}$")
# Canale interno obbligatorio per il servizio: il portale è la fonte autorevole.
MANDATORY = {(Category.SERVICE, Channel.IN_APP)}


class OutboxConflict(Exception):
    """Stessa chiave idempotente riutilizzata con un evento differente."""


class MarketingDisabled(Exception):
    """Le comunicazioni promozionali non fanno parte della baseline."""


@dataclass
class Recipient:
    """Destinatario: un account, oppure solo ``address`` (es. invito senza account)."""

    account: object
    context: dict = field(default_factory=dict)
    address: str = ""


def _hash(event_type, category, payload):
    return hashlib.sha256(
        json.dumps(
            {"type": event_type, "category": category, "payload": payload},
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()


def _normalize(recipients):
    merged = {}
    for item in recipients:
        if not isinstance(item, Recipient):
            item = Recipient(item)
        account = item.account
        address = (item.address or "").strip().lower()
        if account is None and not address:
            continue
        key = account.pk if account is not None else "address:" + address
        current = merged.setdefault(key, Recipient(account, {}, address))
        for key, value in check_context(dict(item.context)).items():
            if isinstance(value, list):
                existing = current.context.get(key, [])
                current.context[key] = sorted(set(existing) | set(value))
            else:
                current.context[key] = value
    for recipient in merged.values():
        check_context(recipient.context)
    return list(merged.values())


def preferences_for(account):
    """Preferenze effettive {(category, channel): enabled}, con default da settings."""
    defaults = settings.COMMUNICATIONS_DEFAULT_PREFERENCES
    result = {
        (category, channel): bool(enabled)
        for category, channels in defaults.items()
        for channel, enabled in channels.items()
    }
    for pref in ChannelPreference.objects.filter(account=account):
        result[(pref.category, pref.channel)] = pref.enabled
    for mandatory in MANDATORY:
        result[mandatory] = True
    return result


def set_preference(account, category, channel, enabled):
    if (category, channel) in MANDATORY and not enabled:
        raise ValueError("Le notifiche di servizio nel portale non sono disattivabili")
    if category not in Category.values or channel not in Channel.values:
        raise ValueError("Categoria o canale non validi")
    ChannelPreference.objects.update_or_create(
        account=account,
        category=category,
        channel=channel,
        defaults={"enabled": bool(enabled)},
    )


def _email_skip_reason(account, prefs, category, context, essential=False):
    if essential:
        return ""
    if not prefs.get((category, Channel.EMAIL), False):
        return "PREFERENCE_DISABLED"
    if not account.email:
        return "EMAIL_UNAVAILABLE"
    if settings.COMMUNICATIONS_REQUIRE_VERIFIED_EMAIL and not account.email_verified:
        return "EMAIL_NOT_VERIFIED"
    if context.get("role") == "student" and not settings.COMMUNICATIONS_EMAIL_STUDENTS:
        return "STUDENT_EMAIL_DISABLED"
    return ""


def emit(
    event_type,
    payload,
    recipients,
    *,
    idempotency_key,
    category=Category.SERVICE,
    channels=(Channel.IN_APP, Channel.EMAIL),
    subject_ref="",
    audience="",
    essential=False,
    secrets=None,
    secrets_expire_at=None,
):
    """Registra un evento e le sue consegne nella transazione corrente.

    Restituisce l'``OutboxEvent`` (nuovo o già esistente in caso di replay).

    - ``audience``: autorizzatore ricontrollato all'invio (``authorization``).
    - ``essential``: messaggio di sicurezza, ignora preferenze e verifica email.
    - ``secrets``: valori riservati (es. token) disponibili solo al rendering
      dell'email; cifrati per consegna e cancellati a consegna conclusa. Richiede
      ``secrets_expire_at``. Mai nel payload, nei log o nell'audit.
    """
    if not connection.in_atomic_block:
        raise RuntimeError(
            "emit() va chiamato dentro la transazione del cambiamento di dominio"
        )
    if not EVENT_TYPE.match(event_type or "") or len(event_type) > 60:
        raise ValueError("event_type non valido (es. 'lesson.published')")
    if not KEY.match(idempotency_key or ""):
        raise ValueError("Chiave idempotente obbligatoria (ASCII stampabile, ≤200)")
    if category not in Category.values:
        raise ValueError("Categoria non valida")
    if category == Category.MARKETING and not settings.COMMUNICATIONS_MARKETING_ENABLED:
        raise MarketingDisabled("Comunicazioni promozionali non abilitate")
    channels = tuple(dict.fromkeys(channels))
    if not channels or any(c not in Channel.values for c in channels):
        raise ValueError("Canali non validi")
    check_payload(payload)
    if audience:
        from .authorization import AUTHORIZERS

        if audience not in AUTHORIZERS:
            raise ValueError("Autorizzatore non registrato")
    if secrets is not None and (
        secrets_expire_at is None or Channel.IN_APP in channels
    ):
        raise ValueError("Segreti solo per email e con scadenza")
    if len(subject_ref) > 100:
        raise ValueError("subject_ref troppo lungo")
    digest = _hash(event_type, category, payload)
    previous = OutboxEvent.objects.filter(idempotency_key=idempotency_key).first()
    if previous:
        return _replay(previous, digest)
    people = _normalize(recipients)
    try:
        with transaction.atomic():
            event = OutboxEvent.objects.create(
                event_type=event_type,
                category=category,
                idempotency_key=idempotency_key,
                payload_hash=digest,
                payload=payload,
                subject_ref=subject_ref,
                audience=audience,
                essential=essential,
                sealed=secrets is not None,
            )
    except IntegrityError:
        return _replay(OutboxEvent.objects.get(idempotency_key=idempotency_key), digest)
    now = timezone.now()
    rows, skipped = [], []
    for person in people:
        account = person.account
        prefs = preferences_for(account) if account is not None else {}
        for channel in channels:
            if (
                channel == Channel.EMAIL
                and not essential
                and account is not None
                and "EMAIL" not in getattr(settings, "COMMUNICATIONS_CHANNELS", ("IN_APP", "EMAIL"))
            ):
                continue
            reason = ""
            if account is None:
                if channel != Channel.EMAIL:
                    raise ValueError("Destinatario senza account: solo email")
            elif not account.is_active:
                reason = "RECIPIENT_INACTIVE"
            elif channel == Channel.EMAIL:
                reason = _email_skip_reason(
                    account, prefs, category, person.context, essential
                )
            elif not prefs.get((category, channel), False):
                reason = "PREFERENCE_DISABLED"
            row = Delivery(
                event=event,
                recipient=account,
                address=person.address if channel == Channel.EMAIL else "",
                channel=channel,
                context=person.context,
                next_attempt_at=now,
                status=DeliveryStatus.SKIPPED if reason else DeliveryStatus.PENDING,
                last_error_code=reason,
                completed_at=now if reason else None,
            )
            rows.append(row)
            if reason:
                skipped.append(row)
    Delivery.objects.bulk_create(rows)
    DeliveryAttempt.objects.bulk_create(
        [
            DeliveryAttempt(
                delivery=row,
                number=0,
                outcome=DeliveryAttempt.Outcome.SKIPPED,
                error_code=row.last_error_code,
            )
            for row in skipped
        ]
    )
    pending = [str(r.id) for r in rows if r.status == DeliveryStatus.PENDING]
    if secrets is not None:
        from .models import SealedSecret
        from .sealing import seal

        SealedSecret.objects.bulk_create(
            [
                SealedSecret(
                    delivery_id=row.id,
                    ciphertext=seal(secrets),
                    expires_at=secrets_expire_at,
                )
                for row in rows
                if row.status == DeliveryStatus.PENDING
            ]
        )
    if pending:
        from .dispatch import enqueue

        transaction.on_commit(lambda: enqueue(pending))
    return event


def _replay(event, digest):
    if event.payload_hash != digest:
        raise OutboxConflict("Chiave idempotente riutilizzata con evento differente")
    return event
