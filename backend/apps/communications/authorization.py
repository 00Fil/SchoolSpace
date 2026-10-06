"""Ricontrollo dell'autorizzazione al momento dell'invio.

Un evento emesso con ``audience=<nome>`` viene consegnato solo se l'autorizzatore
registrato conferma che il destinatario ha ancora diritto al contenuto; altrimenti la
consegna passa a ``REVOKED`` (nessuna email, nessuna notifica interna).

Gli altri stream registrano i propri autorizzatori con ``register_authorizer``.
Un autorizzatore riceve ``(event, delivery)`` e restituisce ``True``/``False``; se
solleva un'eccezione la consegna è ritentata (errore temporaneo).
"""

from django.utils import timezone

AUTHORIZERS = {}


def register_authorizer(name, fn):
    if not name or len(name) > 40:
        raise ValueError("Nome autorizzatore non valido")
    AUTHORIZERS[name] = fn
    return fn


def is_authorized(event, delivery):
    if not event.audience:
        return True
    fn = AUTHORIZERS.get(event.audience)
    if fn is None:
        # Autorizzatore sconosciuto: si nega (fail closed).
        return False
    return bool(fn(event, delivery))


def _lesson(event, delivery):
    from apps.calendar.models import LessonOccurrence
    from .calendar_hooks import lesson_recipients

    lesson = (
        LessonOccurrence.objects.select_related("tutor__account", "subject")
        .filter(pk=event.payload.get("lesson_id"))
        .first()
    )
    if lesson is None or delivery.recipient_id is None:
        return False
    return delivery.recipient_id in {r.account.pk for r in lesson_recipients(lesson)}


def _invitation(event, delivery):
    from apps.identity.models import Invitation

    invitation = Invitation.objects.filter(
        pk=event.payload.get("invitation_id")
    ).first()
    return bool(
        invitation
        and invitation.status == Invitation.Status.SENT
        and invitation.version == event.payload.get("version")
        and invitation.expires_at
        and invitation.expires_at > timezone.now()
        and invitation.email == delivery.address
    )


def _password_reset(event, delivery):
    from apps.identity.models import PasswordResetToken

    record = (
        PasswordResetToken.objects.select_related("account")
        .filter(pk=event.payload.get("reset_id"))
        .first()
    )
    return bool(
        record
        and record.used_at is None
        and record.expires_at > timezone.now()
        and record.account.is_active
        and record.account.email == delivery.address
        and record.account_id == delivery.recipient_id
    )


register_authorizer("calendar.lesson", _lesson)
register_authorizer("identity.invitation", _invitation)
register_authorizer("identity.password_reset", _password_reset)
