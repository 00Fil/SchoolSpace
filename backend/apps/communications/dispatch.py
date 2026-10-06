"""Dispatcher, worker di consegna e reconciler (GAP-F01, GAP-F02, T22, T23).

Macchina a stati di ``Delivery``::

    PENDING --(worker)--> SENDING --accettata--> SENT
       ^                     |--errore temporaneo, tentativi < max--> PENDING (+backoff)
       |                     |--errore permanente o tentativi esauriti--> DEAD
       |                     |--risposta persa / lease scaduto (email)--> AMBIGUOUS
       |                                                                  |
       +-------- lookup NOT_FOUND o provider idempotente <----------------+
                 lookup Accepted ----------------------------------------> SENT
                 esito ignoto e provider non idempotente ----------------> DEAD

``DEAD`` è la dead-letter "da verificare": nessun nuovo invio automatico, il centro
decide (``resolve_delivery``). In-app: idempotente per vincolo DB, mai ambiguo.
"""

import logging
import random
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .authorization import is_authorized
from .models import (
    Channel,
    Delivery,
    DeliveryAttempt,
    DeliveryStatus as S,
    Notification,
    SealedSecret,
)
from .sealing import SealError, unseal
from .providers import (
    NOT_FOUND,
    Accepted,
    AmbiguousError,
    OutgoingEmail,
    PermanentError,
    TransientError,
    get_backend,
)
from .rendering import render_email, render_email_html, render_notification

log = logging.getLogger("apps.communications")
Outcome = DeliveryAttempt.Outcome
QUEUE = "notifications"
TERMINAL = (S.SENT, S.DEAD, S.SKIPPED, S.CANCELLED, S.REVOKED, S.EXPIRED)
NOT_AUTHORIZED = "RECIPIENT_NOT_AUTHORIZED"


def conf(name):
    return settings.COMMUNICATIONS_DELIVERY[name]


def backoff_seconds(attempt, rng=random):
    """Backoff esponenziale con "equal jitter": metà fissa, metà casuale.

    attempt=1 → [base/2, base]; raddoppia a ogni tentativo fino a ``BACKOFF_MAX``.
    """
    ceiling = min(
        conf("BACKOFF_MAX_SECONDS"),
        conf("BACKOFF_BASE_SECONDS") * 2 ** max(attempt - 1, 0),
    )
    return ceiling / 2 + rng.uniform(0, ceiling / 2)


def _attempt(delivery, outcome, code="", provider_id="", actor=None, note=""):
    DeliveryAttempt.objects.create(
        delivery=delivery,
        number=delivery.attempts,
        outcome=outcome,
        error_code=code[:60],
        provider_message_id=provider_id[:200],
        actor=actor,
        note=note[:200],
    )


def enqueue(delivery_ids):
    """Accoda dopo il commit. Un fallimento del broker non perde nulla: resta PENDING."""
    from .tasks import deliver

    sent = 0
    for delivery_id in delivery_ids:
        try:
            deliver.apply_async(args=[str(delivery_id)], queue=QUEUE, retry=False)
        except Exception:  # broker non raggiungibile: recupero del reconciler
            log.warning("communications.enqueue_failed delivery=%s", delivery_id)
            continue
        Delivery.objects.filter(pk=delivery_id, status=S.PENDING).update(
            enqueued_at=timezone.now()
        )
        sent += 1
    return sent


def _finish(delivery, status, code="", provider_id=""):
    delivery.status = status
    delivery.lease_until = None
    delivery.last_error_code = code[:60]
    if provider_id:
        delivery.provider_message_id = provider_id[:200]
    if status in TERMINAL:
        delivery.completed_at = timezone.now()
    delivery.save()
    if status in TERMINAL:
        # Il segreto effimero non sopravvive alla consegna (nemmeno in dead-letter).
        SealedSecret.objects.filter(delivery_id=delivery.pk).delete()


def _retry_or_dead(delivery, code, rng=random):
    if delivery.attempts >= conf("MAX_ATTEMPTS"):
        _finish(delivery, S.DEAD, code)
        return S.DEAD
    delivery.next_attempt_at = timezone.now() + timedelta(
        seconds=backoff_seconds(delivery.attempts, rng)
    )
    delivery.enqueued_at = None
    _finish(delivery, S.PENDING, code)
    return S.PENDING


def _claim(delivery_id):
    """Passa a SENDING con lease; None se non dovuta (duplicato di coda, già fatta)."""
    with transaction.atomic():
        delivery = (
            Delivery.objects.select_for_update(of=("self",))
            .select_related("event", "recipient")
            .filter(pk=delivery_id)
            .first()
        )
        now = timezone.now()
        if (
            not delivery
            or delivery.status != S.PENDING
            or delivery.next_attempt_at > now
        ):
            return None
        delivery.status = S.SENDING
        delivery.attempts += 1
        delivery.lease_until = now + timedelta(seconds=conf("LEASE_SECONDS"))
        delivery.save()
        return delivery


def _deliver_in_app(delivery_id):
    with transaction.atomic():
        delivery = (
            Delivery.objects.select_for_update(of=("self",))
            .select_related("event", "recipient")
            .filter(pk=delivery_id)
            .first()
        )
        if not delivery or delivery.status not in (S.PENDING, S.SENDING):
            return delivery.status if delivery else None
        delivery.attempts += 1
        event = delivery.event
        if not is_authorized(event, delivery):
            _attempt(delivery, Outcome.REVOKED, NOT_AUTHORIZED)
            _finish(delivery, S.REVOKED, NOT_AUTHORIZED)
            return S.REVOKED
        title, body = render_notification(event, delivery)
        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    recipient=delivery.recipient,
                    event=event,
                    category=event.category,
                    kind=event.event_type,
                    title=title,
                    body=body,
                    subject_ref=event.subject_ref,
                )
            outcome = Outcome.ACCEPTED
        except IntegrityError:
            note = Notification.objects.get(event=event, recipient=delivery.recipient)
            outcome = Outcome.DUPLICATE_SUPPRESSED
        delivery.provider = "in_app"
        _finish(delivery, S.SENT, provider_id=str(note.id))
        _attempt(delivery, outcome, provider_id=str(note.id))
        return S.SENT


def _deliver_email(delivery_id, rng=random):
    delivery = _claim(delivery_id)
    if delivery is None:
        return None
    recipient = delivery.recipient
    event = delivery.event
    try:
        authorized = is_authorized(event, delivery)
    except Exception:
        log.exception("communications.authorizer_failed delivery=%s", delivery.id)
        return _settle(delivery, "transient", "AUTHORIZER_FAILED", rng=rng)
    if not authorized:
        return _settle(delivery, "revoked", NOT_AUTHORIZED)
    to = delivery.address or (recipient.email if recipient else "")
    if (recipient is not None and not recipient.is_active) or not to:
        return _settle(delivery, "skipped", "RECIPIENT_UNAVAILABLE")
    extra = {}
    if event.sealed:
        sealed = SealedSecret.objects.filter(delivery_id=delivery.pk).first()
        if sealed is None or sealed.expires_at <= timezone.now():
            return _settle(delivery, "expired", "SECRET_EXPIRED")
        try:
            secrets = unseal(sealed.ciphertext)
        except SealError:
            return _settle(delivery, "expired", "SECRET_UNREADABLE")
        if event.event_type.startswith("identity."):
            from .identity_hooks import render_context

            extra = render_context(event, secrets)
    try:
        backend = get_backend()
    except Exception:
        log.exception("communications.backend_unavailable")
        return _settle(delivery, "transient", "BACKEND_MISCONFIGURED", rng=rng)
    subject, body = render_email(event, delivery, extra)
    try:
        html = render_email_html(event, delivery, extra, subject)
    except Exception:  # la versione testuale basta: l'HTML non deve bloccare l'invio
        log.exception("communications.html_render_failed delivery=%s", delivery.id)
        html = ""
    message = OutgoingEmail(
        to=to,
        subject=subject,
        body=body,
        html=html,
        idempotency_key=delivery.idempotency_key,
        headers={"X-Delivery-Id": str(delivery.id)},
    )
    del extra  # il chiaro resta solo nel corpo del messaggio in uscita
    try:
        result = backend.send(message)
    except TransientError as exc:
        return _settle(delivery, "transient", exc.code, backend=backend.name, rng=rng)
    except PermanentError as exc:
        return _settle(delivery, "permanent", exc.code, backend=backend.name)
    except AmbiguousError as exc:
        return _settle(delivery, "ambiguous", exc.code, backend=backend.name, rng=rng)
    except Exception:
        log.exception("communications.provider_unexpected delivery=%s", delivery.id)
        return _settle(
            delivery, "ambiguous", "PROVIDER_UNEXPECTED", backend=backend.name, rng=rng
        )
    return _settle(
        delivery,
        "accepted",
        provider_id=result.provider_message_id,
        backend=backend.name,
    )


def _settle(delivery, kind, code="", provider_id="", backend="", rng=random):
    """Registra l'esito solo se il lease è ancora nostro (nessun doppio esito)."""
    with transaction.atomic():
        current = Delivery.objects.select_for_update().get(pk=delivery.pk)
        if current.status != S.SENDING or current.attempts != delivery.attempts:
            log.warning("communications.lease_lost delivery=%s", delivery.pk)
            return current.status
        current.provider = backend or current.provider
        if kind == "accepted":
            _finish(current, S.SENT, provider_id=provider_id)
            _attempt(current, Outcome.ACCEPTED, provider_id=provider_id)
        elif kind == "transient":
            _attempt(current, Outcome.TRANSIENT_ERROR, code)
            _retry_or_dead(current, code, rng)
        elif kind == "permanent":
            _attempt(current, Outcome.PERMANENT_ERROR, code)
            _finish(current, S.DEAD, code)
        elif kind == "ambiguous":
            _mark_ambiguous(current, Outcome.AMBIGUOUS, code, rng)
        elif kind == "skipped":
            _attempt(current, Outcome.SKIPPED, code)
            _finish(current, S.SKIPPED, code)
        elif kind == "revoked":
            _attempt(current, Outcome.REVOKED, code)
            _finish(current, S.REVOKED, code)
        elif kind == "expired":
            _attempt(current, Outcome.EXPIRED, code)
            _finish(current, S.EXPIRED, code)
        return current.status


def _mark_ambiguous(delivery, outcome, code, rng=random):
    _attempt(delivery, outcome, code)
    delivery.next_attempt_at = timezone.now() + timedelta(
        seconds=backoff_seconds(1, rng)
    )
    _finish(delivery, S.AMBIGUOUS, code)


def process_delivery(delivery_id, rng=random):
    """Corpo del task Celery. Idempotente: un task duplicato non produce effetti."""
    channel = (
        Delivery.objects.filter(pk=delivery_id)
        .values_list("channel", flat=True)
        .first()
    )
    if channel == Channel.IN_APP:
        return _deliver_in_app(delivery_id)
    if channel == Channel.EMAIL:
        return _deliver_email(delivery_id, rng)
    return None


def recover_expired_leases():
    """Worker morto durante SENDING: in-app si ritenta, email diventa AMBIGUOUS."""
    recovered = 0
    now = timezone.now()
    ids = list(
        Delivery.objects.filter(status=S.SENDING, lease_until__lt=now).values_list(
            "pk", flat=True
        )[:500]
    )
    for delivery_id in ids:
        with transaction.atomic():
            delivery = Delivery.objects.select_for_update().get(pk=delivery_id)
            if delivery.status != S.SENDING or delivery.lease_until >= now:
                continue
            if delivery.channel == Channel.IN_APP:
                _attempt(delivery, Outcome.LEASE_EXPIRED, "LEASE_EXPIRED")
                delivery.next_attempt_at = now
                delivery.enqueued_at = None
                _finish(delivery, S.PENDING, "LEASE_EXPIRED")
            else:
                _mark_ambiguous(delivery, Outcome.LEASE_EXPIRED, "LEASE_EXPIRED")
            recovered += 1
    return recovered


def reconcile_ambiguous(backend=None):
    """Riconciliazione idempotente degli esiti ambigui (T23)."""
    now = timezone.now()
    ids = list(
        Delivery.objects.filter(status=S.AMBIGUOUS, next_attempt_at__lte=now)
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:200]
    )
    if not ids:
        return {}
    backend = backend or get_backend()
    summary = {}
    for delivery_id in ids:
        key = f"delivery-{delivery_id}"
        found = backend.lookup(key)  # chiamata esterna fuori dalla transazione
        with transaction.atomic():
            delivery = Delivery.objects.select_for_update().get(pk=delivery_id)
            if delivery.status != S.AMBIGUOUS:
                continue
            if isinstance(found, Accepted):
                _attempt(
                    delivery,
                    Outcome.RECONCILED_SENT,
                    provider_id=found.provider_message_id,
                )
                _finish(delivery, S.SENT, provider_id=found.provider_message_id)
            elif found == NOT_FOUND:
                _attempt(delivery, Outcome.RECONCILED_NOT_FOUND, "NOT_FOUND")
                _requeue_or_dead(delivery, "AMBIGUOUS_NOT_FOUND")
            elif (
                backend.supports_idempotency
                or settings.COMMUNICATIONS_AMBIGUOUS_POLICY == "retry"
            ):
                # Provider idempotente: il reinvio con la stessa chiave non duplica.
                # Policy "retry" (da approvare): at-least-once, possibile duplicato.
                _attempt(delivery, Outcome.RECONCILED_UNKNOWN, "RETRY_AFTER_AMBIGUOUS")
                _requeue_or_dead(delivery, "AMBIGUOUS_RETRY")
            else:
                _attempt(delivery, Outcome.RECONCILED_UNKNOWN, "AMBIGUOUS_OUTCOME")
                _finish(delivery, S.DEAD, "AMBIGUOUS_OUTCOME")
            summary[delivery.status] = summary.get(delivery.status, 0) + 1
    return summary


def _requeue_or_dead(delivery, code):
    if delivery.attempts >= conf("MAX_ATTEMPTS"):
        _finish(delivery, S.DEAD, code)
        return
    delivery.next_attempt_at = timezone.now()
    delivery.enqueued_at = None
    _finish(delivery, S.PENDING, code)


def due_deliveries(limit=500, include_enqueued=False):
    """PENDING dovute e non accodate (o accodate da troppo: job perso in Redis).

    ``include_enqueued`` (consegna inline senza broker) include anche quelle già
    accodate: il worker è idempotente, quindi un doppione non ha effetti.
    """
    now = timezone.now()
    stale = now - timedelta(seconds=conf("ENQUEUE_STALE_SECONDS"))
    rows = Delivery.objects.filter(status=S.PENDING, next_attempt_at__lte=now)
    if not include_enqueued:
        rows = rows.filter(Q(enqueued_at__isnull=True) | Q(enqueued_at__lt=stale))
    return list(rows.order_by("next_attempt_at").values_list("pk", flat=True)[:limit])


def reconcile(inline=False):
    """Job periodico (beat): lease scaduti, esiti ambigui, outbox non accodata (T22).

    ``inline=True`` consegna direttamente senza broker (comando di emergenza).
    """
    leases = recover_expired_leases()
    purged = SealedSecret.objects.filter(expires_at__lte=timezone.now()).delete()[0]
    ambiguous = reconcile_ambiguous()
    due = due_deliveries(include_enqueued=inline)
    if inline:
        dispatched = sum(1 for d in due if process_delivery(d) is not None)
    else:
        dispatched = enqueue(due)
    return {
        "leases_recovered": leases,
        "expired_secrets_purged": purged,
        "ambiguous": ambiguous,
        "due": len(due),
        "dispatched": dispatched,
    }


def resolve_delivery(delivery_id, actor, resolution, note):
    """Decisione manuale del centro su una consegna DEAD o AMBIGUOUS."""
    with transaction.atomic():
        delivery = Delivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status not in (S.DEAD, S.AMBIGUOUS):
            raise ValueError("Solo consegne in dead-letter o ambigue")
        _attempt(delivery, Outcome.MANUAL, resolution, actor=actor, note=note)
        if resolution == "MARK_SENT":
            _finish(delivery, S.SENT, "MANUAL_MARK_SENT")
        elif resolution == "RETRY":
            delivery.attempts = 0
            delivery.next_attempt_at = timezone.now()
            delivery.enqueued_at = None
            _finish(delivery, S.PENDING, "MANUAL_RETRY")
        elif resolution == "ABANDON":
            _finish(delivery, S.CANCELLED, "MANUAL_ABANDON")
        else:
            raise ValueError("Risoluzione non valida")
        pending = delivery.status == S.PENDING
    if pending:
        enqueue([delivery.pk])
    return delivery
