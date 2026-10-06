"""Servizi auditati per tutor e utenti del centro (guida v3.1, P1: T2 e T3).

Regole (come ``apps.privacy.registry``):
* scrive solo il centro; ogni modifica ha motivo, versione attesa ed evento di audit;
* il tutor esiste prima dell'account: l'invito di ruolo TUTOR lo collega all'accettazione;
* la disattivazione non cancella nulla (le lezioni passate restano), revoca il ruolo e
  chiude gli inviti aperti.
"""

from django.db import transaction
from django.utils import timezone

from apps.governance.audit import record
from apps.identity.models import Account, Invitation, RoleGrant
from apps.identity.policies import is_center
from apps.privacy.errors import Conflict, NotAllowed, PrivacyError

from .models import Tutor
from apps.reasons import reason_or_default

STAFF_ROLES = ("CENTER", "TUTOR")


def require_center(actor):
    if not is_center(actor):
        raise NotAllowed("CENTER_ONLY", "Operazione riservata al centro")


def require_reason(reason):
    """Il motivo non si chiede più: se manca si registra il testo standard."""
    return reason_or_default(reason)


def check_version(obj, expected):
    if obj.version != expected:
        raise Conflict("VERSION_CONFLICT", "Versione non aggiornata")


def _identity(func, *args, **kwargs):
    from apps.identity.services import ServiceError

    try:
        return func(*args, **kwargs)
    except ServiceError as exc:
        raise PrivacyError(exc.code, exc.message or exc.code, status=exc.status)


def _email_taken(email, exclude=None):
    query = Tutor.objects.filter(email__iexact=email)
    if exclude is not None:
        query = query.exclude(pk=exclude.pk)
    return email and query.exists()


# --- Tutor ---------------------------------------------------------------------


@transaction.atomic
def create_tutor(actor, *, display_name, email="", reason, invite=False, request=None):
    require_center(actor)
    reason = require_reason(reason)
    email = (email or "").strip().lower()
    if _email_taken(email):
        raise Conflict("TUTOR_EXISTS", "Esiste già un tutor con questa email")
    account = Account.objects.filter(email__iexact=email).first() if email else None
    if account is not None and Tutor.objects.filter(account=account).exists():
        raise Conflict("TUTOR_EXISTS", "L'account è già collegato a un tutor")
    tutor = Tutor.objects.create(display_name=display_name, email=email)
    record(
        "STAFF",
        "TUTOR_CREATED",
        actor=actor,
        obj=tutor,
        reason=reason,
        purpose="anagrafica tutor",
        details={"email_recorded": bool(email)},
    )
    if invite:
        invite_tutor(actor, tutor, reason=reason, request=request)
    return tutor


@transaction.atomic
def update_tutor(actor, tutor, *, expected_version, changes, reason):
    require_center(actor)
    reason = require_reason(reason)
    tutor = Tutor.objects.select_for_update().get(pk=tutor.pk)
    check_version(tutor, expected_version)
    changed = []
    if "display_name" in changes and changes["display_name"] != tutor.display_name:
        tutor.display_name = changes["display_name"]
        changed.append("display_name")
    if "email" in changes:
        email = (changes["email"] or "").strip().lower()
        if email != tutor.email:
            if tutor.account_id:
                raise Conflict(
                    "TUTOR_HAS_ACCOUNT",
                    "L'email di un tutor con account si cambia dal suo profilo",
                )
            if _email_taken(email, exclude=tutor):
                raise Conflict("TUTOR_EXISTS", "Esiste già un tutor con questa email")
            tutor.email = email
            changed.append("email")
    if changed:
        tutor.save()
    record(
        "STAFF",
        "TUTOR_UPDATED",
        actor=actor,
        obj=tutor,
        reason=reason,
        purpose="anagrafica tutor",
        details={"changed_fields": changed},
    )
    return tutor


def _open_invitations(email, role):
    return Invitation.objects.filter(
        email__iexact=email,
        role=role,
        status__in=[Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT],
    )


@transaction.atomic
def set_tutor_active(actor, tutor, *, active, expected_version, reason, request=None):
    require_center(actor)
    reason = require_reason(reason)
    tutor = Tutor.objects.select_for_update().get(pk=tutor.pk)
    check_version(tutor, expected_version)
    if tutor.active == active:
        return tutor
    tutor.active = active
    tutor.save()
    now = timezone.now()
    revoked_roles = 0
    if not active:
        if tutor.account_id:
            revoked_roles = RoleGrant.objects.filter(
                account_id=tutor.account_id, role="TUTOR", revoked_at__isnull=True
            ).update(revoked_at=now)
        if tutor.email:
            from apps.identity import services

            for inv in _open_invitations(tutor.email, "TUTOR"):
                _identity(services.revoke_invitation, actor, inv.pk, request=request)
    elif tutor.account_id and not _active_grant(tutor.account_id, "TUTOR", now):
        RoleGrant.objects.create(account_id=tutor.account_id, role="TUTOR", valid_from=now)
    record(
        "STAFF",
        "TUTOR_REACTIVATED" if active else "TUTOR_DEACTIVATED",
        actor=actor,
        obj=tutor,
        reason=reason,
        purpose="anagrafica tutor",
        details={"revoked_role_grants": revoked_roles},
    )
    return tutor


def _active_grant(account_id, role, now):
    from django.db.models import Q

    return (
        RoleGrant.objects.filter(
            account_id=account_id, role=role, revoked_at__isnull=True, valid_from__lte=now
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .exists()
    )


@transaction.atomic
def invite_tutor(actor, tutor, *, reason, request=None):
    """Invito di ruolo TUTOR: il token parte subito (nessuna verifica di relazione)."""
    from apps.identity import services

    require_center(actor)
    reason = require_reason(reason)
    if not tutor.active:
        raise Conflict("TUTOR_INACTIVE", "Riattiva il tutor prima di invitarlo")
    if tutor.account_id:
        raise Conflict("TUTOR_HAS_ACCOUNT", "Il tutor ha già un account")
    if not tutor.email:
        raise PrivacyError("EMAIL_REQUIRED", "Serve l'email del tutor per l'invito")
    invitation = _identity(
        services.create_invitation, actor, tutor.email, "TUTOR", request=request
    )
    record(
        "INVITE",
        "TUTOR_INVITE_CREATED",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        reason=reason,
        purpose="accesso tutor",
        details={"tutor": str(tutor.pk)},
    )
    return invitation


def link_account_on_accept(account, invitation):
    """Chiamata da ``identity.services.accept_invitation`` (già in transazione)."""
    if Tutor.objects.filter(account=account).exists():
        return
    tutor = (
        Tutor.objects.select_for_update()
        .filter(email__iexact=invitation.email, account__isnull=True, active=True)
        .first()
    )
    if tutor is None:
        return
    tutor.account = account
    tutor.save()
    record(
        "STAFF",
        "TUTOR_ACCOUNT_LINKED",
        actor=account,
        obj=tutor,
        purpose="accesso tutor",
        details={"invitation": str(invitation.pk)},
    )


# --- Utenti del centro (T3) -------------------------------------------------------


@transaction.atomic
def invite_center_user(actor, *, email, reason, request=None):
    from apps.identity import services

    require_center(actor)
    reason = require_reason(reason)
    invitation = _identity(
        services.create_invitation, actor, email, "CENTER", request=request
    )
    record(
        "STAFF",
        "CENTER_INVITE_CREATED",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        reason=reason,
        purpose="accesso gestore",
    )
    return invitation


@transaction.atomic
def revoke_staff_role(actor, account, *, role, reason):
    require_center(actor)
    reason = require_reason(reason)
    if role not in STAFF_ROLES:
        raise PrivacyError("INVALID_ROLE", "Ruolo non gestibile da qui")
    if role == "CENTER" and account.pk == actor.pk:
        raise Conflict("SELF_REVOKE", "Non puoi revocare il tuo ruolo di gestore")
    now = timezone.now()
    if role == "CENTER":
        others = (
            RoleGrant.objects.filter(role="CENTER", revoked_at__isnull=True)
            .exclude(account=account)
            .values("account")
            .distinct()
            .count()
        )
        if others == 0:
            raise Conflict("LAST_CENTER", "Deve restare almeno un gestore attivo")
    count = RoleGrant.objects.filter(
        account=account, role=role, revoked_at__isnull=True
    ).update(revoked_at=now)
    if count == 0:
        raise Conflict("ROLE_NOT_ACTIVE", "Il ruolo non è attivo")
    record(
        "STAFF",
        "ROLE_REVOKED",
        actor=actor,
        object_type="identity.account",
        object_id=str(account.pk),
        reason=reason,
        purpose="gestione utenti",
        details={"role": role},
    )
    return count
