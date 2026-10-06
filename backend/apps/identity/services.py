"""Casi d'uso di identità: inviti, reset password, policy di accesso (GAP-B02/B03/B07).

Le funzioni non controllano chi chiama: i permessi sono verificati dalle API (centro + MFA).
Gli errori per token non validi sono volutamente indistinguibili (``INVALID_TOKEN``).
"""

from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from . import audit, conf, sessions
from .delivery import deliver
from .models import (
    Account,
    Invitation,
    PasswordResetToken,
    RoleGrant,
    StudentAccessPolicy,
    normalize_email,
)
from .tokens import hash_token, new_token


class ServiceError(Exception):
    def __init__(self, code, status=400, message=None, extra=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.message = message
        self.extra = extra or {}


INVALID_TOKEN = "INVALID_TOKEN"
OPEN = [Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT]


def _password_errors(password, user):
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ServiceError(
            "WEAK_PASSWORD",
            message="Password non valida",
            extra={"errors": exc.messages},
        )


# --- Inviti ---------------------------------------------------------------------------


def _issue_token(invitation):
    if invitation.send_count >= conf.get("INVITATION_MAX_SENDS"):
        raise ServiceError("INVITATION_SEND_LIMIT", status=409)
    token, digest = new_token()
    invitation.token_hash = digest
    invitation.expires_at = timezone.now() + timedelta(
        seconds=conf.get("INVITATION_TTL_SECONDS")
    )
    invitation.status = Invitation.Status.SENT
    invitation.send_count += 1
    invitation.version += 1
    invitation.save()
    deliver("invitation", invitation.email, token, ref=invitation)


@transaction.atomic
def create_invitation(
    actor, email, role, student=None, can_manage_availability=False, request=None,
    age_confirmed=False, family=None,
):
    email = normalize_email(email)
    if role not in RoleGrant.Role.values:
        raise ServiceError("INVALID_ROLE")
    if role != "GUARDIAN":
        family = None
    elif family is not None:
        student = None  # invito di famiglia: la delega copre tutti i figli
    if role in ("GUARDIAN", "STUDENT") and student is None and family is None:
        raise ServiceError("STUDENT_REQUIRED")
    if role not in ("GUARDIAN", "STUDENT"):
        student = None
    if role == "STUDENT" and student.account_id is not None:
        raise ServiceError("STUDENT_ALREADY_HAS_ACCOUNT", status=409)
    if role == "STUDENT" and not age_confirmed:
        # D07: account proprio solo da STUDENT_ACCOUNT_MIN_AGE anni, attestato dal centro.
        raise ServiceError("STUDENT_AGE_CONFIRMATION_REQUIRED")
    invitation = Invitation(
        email=email,
        role=role,
        student=student,
        family=family,
        can_manage_availability=bool(can_manage_availability) and role == "GUARDIAN",
        created_by=actor,
    )
    try:
        with transaction.atomic():
            invitation.save()
    except IntegrityError:
        raise ServiceError("INVITATION_EXISTS", status=409)
    if role != "GUARDIAN":
        # Il tutore riceve l'invito solo dopo la verifica della relazione.
        _issue_token(invitation)
    audit.record(
        "invitation.created",
        actor=actor,
        object_id=invitation.id,
        request=request,
        role=role,
        student=str(student.id) if student else None,
        family=str(family.pk) if family else None,
        status=invitation.status,
        age_confirmed=bool(age_confirmed) if role == "STUDENT" else None,
    )
    return invitation


def _locked(invitation_id):
    try:
        return Invitation.objects.select_for_update().get(pk=invitation_id)
    except Invitation.DoesNotExist:
        raise ServiceError("NOT_FOUND", status=404)


@transaction.atomic
def verify_guardian_relation(actor, invitation_id, evidence, request=None):
    invitation = _locked(invitation_id)
    if invitation.role != "GUARDIAN":
        raise ServiceError("NOT_A_GUARDIAN_INVITATION", status=409)
    if invitation.status != Invitation.Status.PENDING_VERIFICATION:
        raise ServiceError("INVALID_STATE", status=409)
    evidence = (evidence or "").strip()
    if not evidence or len(evidence) > 200:
        raise ServiceError("EVIDENCE_REQUIRED")
    invitation.relation_verified_by = actor
    invitation.relation_verified_at = timezone.now()
    invitation.relation_evidence = evidence
    _issue_token(invitation)
    audit.record(
        "invitation.relation_verified",
        actor=actor,
        object_id=invitation.id,
        request=request,
        student=str(invitation.student_id),
    )
    return invitation


@transaction.atomic
def resend_invitation(actor, invitation_id, request=None):
    invitation = _locked(invitation_id)
    if invitation.status != Invitation.Status.SENT:
        raise ServiceError("INVALID_STATE", status=409)
    _issue_token(invitation)  # il token precedente smette di valere
    audit.record(
        "invitation.resent", actor=actor, object_id=invitation.id, request=request
    )
    return invitation


@transaction.atomic
def revoke_invitation(actor, invitation_id, request=None):
    invitation = _locked(invitation_id)
    if invitation.status not in OPEN:
        raise ServiceError("INVALID_STATE", status=409)
    invitation.status = Invitation.Status.REVOKED
    invitation.revoked_at = timezone.now()
    invitation.token_hash = None
    invitation.qr_token_hash = None
    invitation.qr_expires_at = None
    invitation.version += 1
    invitation.save()
    audit.record(
        "invitation.revoked", actor=actor, object_id=invitation.id, request=request
    )
    return invitation


@transaction.atomic
def issue_qr_token(actor, invitation_id, request=None):
    """Token breve per l'accesso via QR mostrato dal centro (v0.9.5).

    Non tocca il token dell'email né la versione dell'invito: la consegna in corso resta
    valida. Il token in chiaro torna solo al chiamante e non viene salvato né auditato.
    """
    invitation = _locked(invitation_id)
    now = timezone.now()
    if invitation.status != Invitation.Status.SENT or not invitation.expires_at or invitation.expires_at <= now:
        raise ServiceError("INVALID_STATE", status=409, message="L'invito non è attivo")
    token, digest = new_token()
    expires = min(
        invitation.expires_at,
        now + timedelta(seconds=conf.get("INVITATION_QR_TTL_SECONDS")),
    )
    Invitation.objects.filter(pk=invitation.pk).update(
        qr_token_hash=digest, qr_expires_at=expires
    )
    audit.record(
        "invitation.qr_issued", actor=actor, object_id=invitation.id, request=request
    )
    return token, expires


def _active_grant_exists(account, role, now):
    return (
        account.role_grants.filter(
            role=role, revoked_at__isnull=True, valid_from__lte=now
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .exists()
    )


@transaction.atomic
def accept_invitation(token, password=None, current_user=None, request=None):
    from apps.education.models import GuardianLink, Student

    now = timezone.now()
    digest = hash_token(token or "")
    invitation = (
        Invitation.objects.select_for_update()
        .filter(token_hash=digest, status=Invitation.Status.SENT)
        .first()
    )
    if invitation is None:
        # QR mostrato dal centro: vale solo per pochi minuti.
        invitation = (
            Invitation.objects.select_for_update()
            .filter(
                qr_token_hash=digest,
                status=Invitation.Status.SENT,
                qr_expires_at__gt=now,
            )
            .first()
        )
    if invitation is None or invitation.expires_at <= now:
        raise ServiceError(INVALID_TOKEN, message="Link non valido o scaduto")
    account = Account.objects.filter(email__iexact=invitation.email).first()
    if account is not None:
        # Chi ha già un account deve accedere con quello: il token non sostituisce la password.
        if (
            current_user is None
            or not current_user.is_authenticated
            or current_user.pk != account.pk
        ):
            raise ServiceError(
                "LOGIN_REQUIRED",
                status=409,
                message="Accedi con il tuo account e riapri il link di invito",
            )
        if not account.is_active:
            raise ServiceError(INVALID_TOKEN, message="Link non valido o scaduto")
    else:
        account = Account(
            username=invitation.email[:150], email=invitation.email, email_verified=True
        )
        if not isinstance(password, str) or not password:
            raise ServiceError("PASSWORD_REQUIRED")
        _password_errors(password, account)
        account.set_password(password)
        account.save()
    if not account.email_verified:
        account.email_verified = True
        account.save(update_fields=["email_verified"])
    if invitation.role == "STUDENT":
        student = Student.objects.select_for_update().get(pk=invitation.student_id)
        if student.account_id not in (None, account.pk):
            raise ServiceError(INVALID_TOKEN, message="Link non valido o scaduto")
        if student.account_id is None:
            student.account = account
            student.save()
    if not _active_grant_exists(account, invitation.role, now):
        RoleGrant.objects.create(account=account, role=invitation.role, valid_from=now)
    if invitation.role == "TUTOR":
        # P1/T2: collega la scheda tutor creata dal centro (stessa email, senza account).
        from apps.education.tutors import link_account_on_accept

        link_account_on_accept(account, invitation)
    if invitation.role == "GUARDIAN" and invitation.student_id:
        link = (
            GuardianLink.objects.filter(
                account=account,
                student_id=invitation.student_id,
                revoked_at__isnull=True,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
            .first()
        )
        if link is None:
            GuardianLink.objects.create(
                account=account,
                student_id=invitation.student_id,
                can_view=True,
                can_manage_availability=invitation.can_manage_availability,
                verified=True,
                valid_from=now,
            )
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_at = now
    invitation.accepted_account = account
    invitation.token_hash = None
    invitation.qr_token_hash = None
    invitation.qr_expires_at = None
    invitation.version += 1
    invitation.save()
    audit.record(
        "invitation.accepted",
        actor=account,
        subject=account,
        object_id=invitation.id,
        request=request,
        role=invitation.role,
    )
    return account


# --- Password -------------------------------------------------------------------------


def request_password_reset(email, request=None):
    """Sempre lo stesso esito per il chiamante; l'invio avviene solo per account idonei."""
    email = normalize_email(email)
    account = Account.objects.filter(email__iexact=email, is_active=True).first()
    if account is None or not (account.email_verified or account.has_usable_password()):
        return None
    with transaction.atomic():
        PasswordResetToken.objects.filter(account=account, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        token, digest = new_token()
        record = PasswordResetToken.objects.create(
            account=account,
            token_hash=digest,
            expires_at=timezone.now()
            + timedelta(seconds=conf.get("PASSWORD_RESET_TTL_SECONDS")),
        )
        audit.record("password_reset.requested", subject=account, request=request)
        deliver("password_reset", account.email, token, ref=record)
    return account


@transaction.atomic
def confirm_password_reset(token, password, request=None):
    now = timezone.now()
    record = (
        PasswordResetToken.objects.select_for_update(of=("self",))
        .select_related("account")
        .filter(token_hash=hash_token(token or ""), used_at__isnull=True)
        .first()
    )
    if record is None or record.expires_at <= now or not record.account.is_active:
        raise ServiceError(INVALID_TOKEN, message="Link non valido o scaduto")
    account = record.account
    if not isinstance(password, str) or not password:
        raise ServiceError("PASSWORD_REQUIRED")
    _password_errors(password, account)
    account.set_password(password)
    account.save()
    PasswordResetToken.objects.filter(account=account, used_at__isnull=True).update(
        used_at=now
    )
    revoked = sessions.revoke_all(account, "password_reset")
    audit.record(
        "password_reset.completed",
        actor=account,
        subject=account,
        request=request,
        sessions_revoked=revoked,
    )
    return account


@transaction.atomic
def change_password(
    account, current_password, new_password, keep_session_id, request=None
):
    if not account.check_password(current_password or ""):
        raise ServiceError("INVALID_CREDENTIALS", status=400)
    _password_errors(new_password, account)
    account.set_password(new_password)
    account.save()
    revoked = sessions.revoke_all(account, "password_change", except_id=keep_session_id)
    audit.record(
        "password.changed",
        actor=account,
        subject=account,
        request=request,
        sessions_revoked=revoked,
    )
    return account


# --- Studente maggiorenne (D07) -------------------------------------------------------


@transaction.atomic
def set_student_access_policy(
    actor,
    student,
    adult_confirmed,
    guardian_access,
    expected_version=None,
    request=None,
):
    if guardian_access not in StudentAccessPolicy.GuardianAccess.values:
        raise ServiceError("INVALID_GUARDIAN_ACCESS")
    policy = (
        StudentAccessPolicy.objects.select_for_update().filter(student=student).first()
    )
    if policy is None:
        if expected_version not in (None, 0):
            raise ServiceError("VERSION_CONFLICT", status=409)
        policy = StudentAccessPolicy(student=student, confirmed_by=actor)
    elif expected_version is not None and expected_version != policy.version:
        raise ServiceError("VERSION_CONFLICT", status=409)
    else:
        policy.version += 1
    policy.adult_confirmed = bool(adult_confirmed)
    policy.guardian_access = guardian_access
    policy.confirmed_by = actor
    if not policy.adult_confirmed:
        policy.student_consent_at = None
    policy.save()
    audit.record(
        "student_policy.updated",
        actor=actor,
        object_id=student.id,
        request=request,
        adult_confirmed=policy.adult_confirmed,
        guardian_access=guardian_access,
    )
    return policy


@transaction.atomic
def set_student_guardian_consent(account, granted, request=None):
    from apps.education.models import Student

    student = Student.objects.filter(account=account).first()
    policy = (
        StudentAccessPolicy.objects.select_for_update()
        .filter(student=student, adult_confirmed=True)
        .first()
        if student
        else None
    )
    if policy is None:
        raise ServiceError("NOT_APPLICABLE", status=409)
    policy.student_consent_at = timezone.now() if granted else None
    policy.version += 1
    policy.save()
    audit.record(
        "student_policy.consent",
        actor=account,
        subject=account,
        object_id=student.id,
        request=request,
        granted=bool(granted),
    )
    return policy
