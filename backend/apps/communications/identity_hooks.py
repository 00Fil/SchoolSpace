"""Consegna via outbox delle email di invito e reset password (stream s1).

Attivato con ``IDENTITY_MESSAGE_SENDER = "apps.communications.identity_hooks.send"``.

Scelta (documentata in docs/communications.md): il token in chiaro non entra mai nel
payload, nei log o nell'audit. ``emit`` riceve il token come segreto: è cifrato con
Fernet in ``SealedSecret`` (una riga per consegna, scadenza = scadenza del token),
decifrato solo dal worker al momento dell'invio per comporre il link nel corpo
dell'email, e cancellato appena la consegna è conclusa. Il payload contiene solo il
riferimento (id e versione dell'invito / id del reset), così il worker ricontrolla che
il token sia ancora valido: un reinvio, una revoca o un uso annullano la consegna
precedente (``REVOKED``) invece di spedire un link morto o sostituito.
"""

from django.conf import settings

from .services import Recipient, emit


def _account(email):
    from apps.identity.models import Account

    return Account.objects.filter(email__iexact=email).first()


def send(kind, to, token, ref=None):
    if ref is None:
        raise ValueError("Riferimento all'invito o al reset obbligatorio")
    expires = ref.expires_at
    if kind == "invitation":
        account = _account(to)
        return emit(
            "identity.invitation",
            {
                "invitation_id": str(ref.id),
                "version": ref.version,
                "role": ref.role,
                "expires_at": expires.isoformat(),
            },
            [Recipient(account, {}, address=to)],
            idempotency_key=f"identity:invitation:{ref.id}:v{ref.version}",
            channels=("EMAIL",),
            audience="identity.invitation",
            essential=True,
            secrets={"token": token},
            secrets_expire_at=expires,
            subject_ref=f"invitation:{ref.id}",
        )
    if kind == "password_reset":
        return emit(
            "identity.password_reset",
            {"reset_id": str(ref.id), "expires_at": expires.isoformat()},
            [Recipient(ref.account, {}, address=to)],
            idempotency_key=f"identity:password_reset:{ref.id}",
            channels=("EMAIL",),
            audience="identity.password_reset",
            essential=True,
            secrets={"token": token},
            secrets_expire_at=expires,
            subject_ref=f"account:{ref.account_id}",
        )
    raise ValueError(f"Messaggio di identità sconosciuto: {kind}")


send.transactional = True


def render_context(event, secrets):
    """Contesto di rendering con il link: esiste solo in memoria durante l'invio."""
    from apps.identity import conf as identity_conf
    from apps.identity.delivery import build_link

    kind = event.event_type.split(".", 1)[1]
    token = secrets.get("token", "")
    return {
        "link": build_link(kind, token) if token else "",
        "hours": identity_conf.get("INVITATION_TTL_SECONDS") // 3600,
        "minutes": identity_conf.get("PASSWORD_RESET_TTL_SECONDS") // 60,
        "center_name": settings.COMMUNICATIONS_CENTER_NAME,
    }
