"""Servizi auditati per famiglie, studenti, deleghe e inviti (GAP-B06, FR01/FR02/FR23).

Regole:
* solo il centro scrive (controllo nell'API e qui con :func:`require_center`);
* ogni modifica ha motivo, versione attesa ove applicabile ed evento di audit;
* una delega attiva per coppia account/studente (paper §4.2: UQ relazione attiva);
* la revoca è immediata nel live; gli inviti sono monouso e conservano solo l'hash.
"""

import hashlib

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.governance.audit import record
from apps.identity.models import RoleGrant
from apps.identity.policies import is_center

from .errors import Conflict, NotAllowed, PrivacyError
from .models import (
    FamilyGuardian,
    FamilyProfile,
    GuardianLinkDetail,
    InvitationTerms,
    StudentProfile,
)
from apps.reasons import reason_or_default

PERMISSION_FIELDS = (
    "can_view",
    "can_manage_availability",
    "can_receive_notifications",
    "can_request_changes",
)


def require_center(actor):
    if not is_center(actor):
        raise NotAllowed("CENTER_ONLY", "Operazione riservata al centro")


def require_reason(reason):
    """Il motivo non si chiede più: se manca si registra il testo standard."""
    return reason_or_default(reason)


def check_version(obj, expected):
    if expected is not None and obj.version != expected:
        raise Conflict("VERSION_CONFLICT", "Versione non aggiornata")


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _active_link_q(now):
    return Q(revoked_at__isnull=True) & (
        Q(valid_until__isnull=True) | Q(valid_until__gt=now)
    )


# --- Famiglie -------------------------------------------------------------


@transaction.atomic
def create_family(actor, *, reference, contact=None, reason="", command=""):
    require_center(actor)
    if Family.objects.filter(reference=reference).exists():
        raise Conflict("FAMILY_EXISTS", "Riferimento famiglia già presente")
    family = Family.objects.create(reference=reference)
    profile = FamilyProfile.objects.create(family=family, **(contact or {}))
    record(
        "FAMILY",
        "FAMILY_CREATED",
        actor=actor,
        obj=family,
        reason=reason,
        command=command,
        purpose="anagrafica",
        details={"fields": sorted((contact or {}).keys())},
    )
    return family, profile


@transaction.atomic
def update_family(actor, family, *, expected_version, changes, reason):
    require_center(actor)
    reason = require_reason(reason)
    family = Family.objects.select_for_update().get(pk=family.pk)
    check_version(family, expected_version)
    profile, _ = FamilyProfile.objects.get_or_create(family=family)
    changed = []
    if "reference" in changes and changes["reference"] != family.reference:
        if Family.objects.filter(reference=changes["reference"]).exists():
            raise Conflict("FAMILY_EXISTS", "Riferimento famiglia già presente")
        family.reference = changes["reference"]
        changed.append("reference")
    for field in ("contact_name", "contact_email", "contact_phone"):
        if field in changes and getattr(profile, field) != changes[field]:
            setattr(profile, field, changes[field])
            changed.append(field)
    family.save()
    if any(f.startswith("contact_") for f in changed):
        profile.save()
    record(
        "FAMILY",
        "FAMILY_UPDATED",
        actor=actor,
        obj=family,
        reason=reason,
        purpose="anagrafica",
        details={"changed_fields": changed},
    )
    return family


# --- Studenti -------------------------------------------------------------


@transaction.atomic
def create_student(
    actor, *, family, display_name, level="", birth_date=None, reason="", command=""
):
    require_center(actor)
    student = Student.objects.create(
        family=family, display_name=display_name, level=level
    )
    StudentProfile.objects.create(student=student, birth_date=birth_date)
    record(
        "FAMILY",
        "STUDENT_CREATED",
        actor=actor,
        obj=student,
        reason=reason,
        command=command,
        purpose="anagrafica",
        details={"family": str(family.pk), "birth_date_recorded": bool(birth_date)},
    )
    # I genitori della famiglia che hanno già accettato l'invito vedono subito il figlio.
    for guardian in FamilyGuardian.objects.filter(
        family=family, revoked_at__isnull=True, account__isnull=False
    ).select_related("account", "invitation"):
        _family_link(guardian, student, actor=actor)
    return student


@transaction.atomic
def update_student(actor, student, *, expected_version, changes, reason):
    require_center(actor)
    reason = require_reason(reason)
    student = Student.objects.select_for_update().get(pk=student.pk)
    check_version(student, expected_version)
    profile, _ = StudentProfile.objects.get_or_create(student=student)
    changed = []
    for field in ("display_name", "level", "family", "active"):
        if field in changes and getattr(student, field) != changes[field]:
            setattr(student, field, changes[field])
            changed.append(field)
    if "birth_date" in changes and profile.birth_date != changes["birth_date"]:
        profile.birth_date = changes["birth_date"]
        profile.save()
        changed.append("birth_date")
    if changed:
        student.save()
    record(
        "FAMILY",
        "STUDENT_UPDATED",
        actor=actor,
        obj=student,
        reason=reason,
        purpose="anagrafica",
        details={"changed_fields": changed},
    )
    if "active" in changed and not student.active:
        # Disattivazione: le deleghe restano visibili allo storico ma l'account dello
        # studente non autentica più (FR24: disattivazione governata).
        if student.account_id:
            account = student.account
            account.is_active = False
            account.save()
    return student


# --- Account dei tutori legali -----------------------------------------------


def existing_account(email):
    """Account già registrato per l'email (match normalizzato), oppure None.

    Gli account dei tutori nascono solo accettando un invito di identity (B02):
    il registro non crea account inattivi "segnaposto".
    """
    from apps.identity.models import normalize_email

    return get_user_model().objects.filter(email__iexact=normalize_email(email)).first()


def ensure_guardian_role(account):
    now = timezone.now()
    active = account.role_grants.filter(
        role=RoleGrant.Role.GUARDIAN, revoked_at__isnull=True, valid_from__lte=now
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    if not active.exists():
        RoleGrant.objects.create(
            account=account, role=RoleGrant.Role.GUARDIAN, valid_from=now
        )


# --- Deleghe GuardianLink ---------------------------------------------------


@transaction.atomic
def create_guardian_link(
    actor,
    *,
    student,
    account,
    relationship=GuardianLinkDetail.Relationship.PARENT,
    permissions=None,
    valid_from=None,
    valid_until=None,
    reason="",
    command="",
):
    """Crea una delega *non verificata*: il portale non la usa finché il centro non verifica."""
    require_center(actor)
    now = timezone.now()
    perms = {"can_view": True, "can_manage_availability": False}
    perms |= {
        "can_receive_notifications": True,
        "can_request_changes": False,
    }
    perms |= {k: bool(v) for k, v in (permissions or {}).items() if k in perms}
    if student.account_id and student.account_id == account.pk:
        raise PrivacyError("SELF_DELEGATION", "Lo studente non si autoconcede deleghe")
    # Lock su studente per serializzare le creazioni concorrenti sulla stessa coppia.
    Student.objects.select_for_update().get(pk=student.pk)
    if (
        GuardianLink.objects.filter(student=student, account=account)
        .filter(_active_link_q(now))
        .exists()
    ):
        raise Conflict("LINK_EXISTS", "Esiste già una delega attiva per la coppia")
    link = GuardianLink.objects.create(
        student=student,
        account=account,
        can_view=perms["can_view"],
        can_manage_availability=perms["can_manage_availability"],
        verified=False,
        valid_from=valid_from or now,
        valid_until=valid_until,
    )
    GuardianLinkDetail.objects.create(
        link=link,
        relationship=relationship,
        can_receive_notifications=perms["can_receive_notifications"],
        can_request_changes=perms["can_request_changes"],
    )
    ensure_guardian_role(account)
    record(
        "GUARDIANSHIP",
        "LINK_CREATED",
        actor=actor,
        obj=link,
        reason=reason,
        command=command,
        purpose="delega",
        details={
            "student": str(student.pk),
            "account": str(account.pk),
            "relationship": relationship,
            "permissions": perms,
        },
    )
    return link


def _locked_link(link):
    link = GuardianLink.objects.select_for_update().get(pk=link.pk)
    detail, _ = GuardianLinkDetail.objects.get_or_create(link=link)
    return link, detail


@transaction.atomic
def verify_guardian_link(actor, link, *, expected_version, method, reason):
    require_center(actor)
    reason = require_reason(reason)
    if not isinstance(method, str) or not method.strip() or len(method) > 120:
        raise PrivacyError("METHOD_REQUIRED", "Indicare come è stata verificata")
    link, detail = _locked_link(link)
    check_version(link, expected_version)
    if link.revoked_at:
        raise Conflict("LINK_REVOKED", "Delega revocata: crearne una nuova")
    if link.verified:
        raise Conflict("ALREADY_VERIFIED", "Delega già verificata")
    link.verified = True
    link.save()
    detail.verified_by = actor
    detail.verified_at = timezone.now()
    detail.verification_method = method.strip()
    detail.save()
    record(
        "GUARDIANSHIP",
        "LINK_VERIFIED",
        actor=actor,
        obj=link,
        reason=reason,
        purpose="delega",
        details={"method": method.strip()},
    )
    return link


@transaction.atomic
def update_link_permissions(actor, link, *, expected_version, permissions, reason):
    require_center(actor)
    reason = require_reason(reason)
    link, detail = _locked_link(link)
    check_version(link, expected_version)
    if link.revoked_at:
        raise Conflict("LINK_REVOKED", "Delega revocata")
    before = permission_snapshot(link, detail)
    for key, value in permissions.items():
        if key not in PERMISSION_FIELDS:
            raise PrivacyError("UNKNOWN_PERMISSION", key)
        target = link if key in ("can_view", "can_manage_availability") else detail
        setattr(target, key, bool(value))
    link.save()
    detail.save()
    record(
        "GUARDIANSHIP",
        "LINK_PERMISSIONS_CHANGED",
        actor=actor,
        obj=link,
        reason=reason,
        purpose="delega",
        details={"before": before, "after": permission_snapshot(link, detail)},
    )
    return link


@transaction.atomic
def revoke_guardian_link(actor, link, *, reason, expected_version=None, system=False):
    """Revoca immediata (paper §10.5). ``system`` per job governati (es. riconciliazione)."""
    if not system:
        require_center(actor)
    reason = require_reason(reason)
    link, detail = _locked_link(link)
    check_version(link, expected_version)
    if link.revoked_at:
        raise Conflict("LINK_REVOKED", "Delega già revocata")
    now = timezone.now()
    link.revoked_at = now
    link.save()
    detail.revoked_by = actor if getattr(actor, "is_authenticated", False) else None
    detail.revocation_reason = reason
    detail.save()
    revoke_open_invitations(
        actor, email=link.account.email, student_id=link.student_id, system=True
    )
    record(
        "GUARDIANSHIP",
        "LINK_REVOKED",
        actor=actor,
        obj=link,
        reason=reason,
        purpose="delega",
        command="system" if system else "",
    )
    from .ledger import append_on_commit

    append_on_commit("LINK_REVOKED", link=str(link.pk), student=str(link.student_id))
    return link


def permission_snapshot(link, detail):
    return {
        "can_view": link.can_view,
        "can_manage_availability": link.can_manage_availability,
        "can_receive_notifications": detail.can_receive_notifications,
        "can_request_changes": detail.can_request_changes,
    }


# --- Inviti (sistema unico: apps.identity, s1) -----------------------------------


def _identity_call(func, *args, **kwargs):
    from apps.identity.services import ServiceError

    try:
        return func(*args, **kwargs)
    except ServiceError as exc:
        raise PrivacyError(
            exc.code, exc.message or exc.code, status=exc.status
        ) from exc


@transaction.atomic
def invite_guardian(
    actor,
    *,
    student,
    email,
    relationship=GuardianLinkDetail.Relationship.PARENT,
    permissions=None,
    reason="",
    import_batch=None,
    request=None,
):
    """Crea un invito tutore con identity (stato PENDING_VERIFICATION, nessun token).

    Il token viene emesso e consegnato solo da :func:`verify_invitation_relation`.
    """
    from apps.identity import services

    require_center(actor)
    perms = {"can_manage_availability": False, "can_receive_notifications": True}
    perms |= {"can_request_changes": False}
    perms |= {k: bool(v) for k, v in (permissions or {}).items() if k in perms}
    invitation = _identity_call(
        services.create_invitation,
        actor,
        email,
        "GUARDIAN",
        student=student,
        can_manage_availability=perms["can_manage_availability"],
        request=request,
    )
    InvitationTerms.objects.create(
        invitation=invitation,
        relationship=relationship,
        can_receive_notifications=perms["can_receive_notifications"],
        can_request_changes=perms["can_request_changes"],
        import_batch=import_batch,
    )
    record(
        "INVITE",
        "INVITE_CREATED",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        reason=reason,
        purpose="accesso portale",
        details={
            "student": str(student.pk),
            "relationship": relationship,
            "permissions": perms,
        },
    )
    return invitation


@transaction.atomic
def verify_invitation_relation(actor, invitation, *, evidence, request=None):
    """Verifica della relazione: identity emette il token e lo consegna dopo il commit."""
    from apps.identity import services

    require_center(actor)
    invitation = _identity_call(
        services.verify_guardian_relation,
        actor,
        invitation.pk,
        evidence,
        request=request,
    )
    record(
        "INVITE",
        "INVITE_RELATION_VERIFIED",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        purpose="accesso portale",
        details={"student": str(invitation.student_id)},
    )
    return invitation


@transaction.atomic
def resend_invitation(actor, invitation, *, request=None):
    from apps.identity import services

    require_center(actor)
    invitation = _identity_call(
        services.resend_invitation, actor, invitation.pk, request=request
    )
    record(
        "INVITE",
        "INVITE_RESENT",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
    )
    return invitation


@transaction.atomic
def revoke_invitation(actor, invitation, *, reason, request=None, system=False):
    from apps.identity import services

    if not system:
        require_center(actor)
    reason = require_reason(reason)
    invitation = _identity_call(
        services.revoke_invitation,
        actor if getattr(actor, "is_authenticated", False) else None,
        invitation.pk,
        request=request,
    )
    record(
        "INVITE",
        "INVITE_REVOKED",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        reason=reason,
        command="system" if system else "",
    )
    return invitation


def revoke_open_invitations(actor, *, email=None, student_id=None, system=True):
    """Revoca gli inviti aperti (per email e/o studente): usata da revoca e anonimizzazione."""
    from apps.identity.models import Invitation, normalize_email

    query = Invitation.objects.filter(
        status__in=[
            Invitation.Status.PENDING_VERIFICATION,
            Invitation.Status.SENT,
        ]
    )
    if email:
        query = query.filter(email__iexact=normalize_email(email))
    if student_id:
        query = query.filter(student_id=student_id)
    done = 0
    for invitation in query:
        revoke_invitation(actor, invitation, reason="revoca collegata", system=system)
        done += 1
    return done


def apply_invitation_terms(invitation):
    """Alla accettazione: la delega creata/riusata da identity riceve i campi del paper."""
    if invitation.family_id and invitation.accepted_account_id:
        return apply_family_acceptance(invitation)
    terms = InvitationTerms.objects.filter(invitation=invitation).first()
    if invitation.accepted_account_id is None or invitation.student_id is None:
        return None
    link = (
        GuardianLink.objects.filter(
            account_id=invitation.accepted_account_id,
            student_id=invitation.student_id,
            revoked_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if link is None:
        return None
    detail, _ = GuardianLinkDetail.objects.get_or_create(link=link)
    if terms:
        detail.relationship = terms.relationship
        detail.can_receive_notifications = terms.can_receive_notifications
        detail.can_request_changes = terms.can_request_changes
    if detail.verified_at is None and invitation.relation_verified_at:
        detail.verified_by_id = invitation.relation_verified_by_id
        detail.verified_at = invitation.relation_verified_at
        detail.verification_method = invitation.relation_evidence[:120]
    detail.save()
    record(
        "GUARDIANSHIP",
        "LINK_CREATED_FROM_INVITATION",
        actor=invitation.accepted_account,
        obj=link,
        purpose="delega",
        details={"invitation": str(invitation.pk)},
    )
    return detail


# --- Genitori e tutori di famiglia (v0.9.5) ---------------------------------------
#
# Il centro iscrive prima il genitore/tutore (nome, email, relazione verificata), poi i
# figli. L'invito è di famiglia: accettandolo l'account riceve una delega verificata su
# ogni figlio attivo; i figli aggiunti in seguito ricevono la delega in automatico.

GUARDIAN_PERMS = (
    "can_manage_availability",
    "can_receive_notifications",
    "can_request_changes",
)


def _guardian_perms(permissions):
    perms = {
        "can_manage_availability": True,
        "can_receive_notifications": True,
        "can_request_changes": True,
    }
    for key, value in (permissions or {}).items():
        if key not in GUARDIAN_PERMS:
            raise PrivacyError("UNKNOWN_PERMISSION", key)
        perms[key] = bool(value)
    return perms


def _family_link(guardian, student, *, actor=None):
    """Delega verificata guardian→figlio; riusa quella attiva se esiste già."""
    now = timezone.now()
    account = guardian.account
    if student.account_id and student.account_id == account.pk:
        return None
    existing = (
        GuardianLink.objects.filter(student=student, account=account)
        .filter(_active_link_q(now))
        .first()
    )
    if existing is not None:
        return existing
    invitation = guardian.invitation
    link = GuardianLink.objects.create(
        student=student,
        account=account,
        can_view=True,
        can_manage_availability=guardian.can_manage_availability,
        verified=True,
        valid_from=now,
    )
    GuardianLinkDetail.objects.create(
        link=link,
        relationship=guardian.relationship,
        can_receive_notifications=guardian.can_receive_notifications,
        can_request_changes=guardian.can_request_changes,
        verified_by_id=invitation.relation_verified_by_id if invitation else None,
        verified_at=(invitation.relation_verified_at if invitation else None) or now,
        verification_method=(
            invitation.relation_evidence[:120] if invitation else "famiglia"
        ),
    )
    ensure_guardian_role(account)
    record(
        "GUARDIANSHIP",
        "LINK_CREATED_FROM_FAMILY",
        actor=actor if getattr(actor, "is_authenticated", False) else account,
        obj=link,
        purpose="delega",
        details={"family_guardian": str(guardian.pk), "student": str(student.pk)},
    )
    return link


def apply_family_acceptance(invitation):
    guardian = (
        FamilyGuardian.objects.select_for_update()
        .filter(invitation=invitation, revoked_at__isnull=True)
        .first()
    )
    if guardian is None:
        return None
    account = invitation.accepted_account
    if guardian.account_id != account.pk:
        guardian.account = account
        guardian.version += 1
        guardian.save()
    if not (account.first_name or account.last_name) and guardian.display_name:
        first, _, last = guardian.display_name.partition(" ")
        type(account).objects.filter(pk=account.pk).update(
            first_name=first[:150], last_name=last[:150]
        )
    for student in Student.objects.filter(family_id=guardian.family_id, active=True):
        _family_link(guardian, student)
    return guardian


def _invite_family_guardian(actor, guardian, *, evidence="", request=None):
    from apps.identity import services

    invitation = _identity_call(
        services.create_invitation,
        actor,
        guardian.email,
        "GUARDIAN",
        family=guardian.family,
        can_manage_availability=guardian.can_manage_availability,
        request=request,
    )
    InvitationTerms.objects.create(
        invitation=invitation,
        relationship=guardian.relationship,
        can_receive_notifications=guardian.can_receive_notifications,
        can_request_changes=guardian.can_request_changes,
    )
    guardian.invitation = invitation
    guardian.save()
    if evidence:
        invitation = verify_invitation_relation(
            actor, invitation, evidence=evidence, request=request
        )
    return invitation


@transaction.atomic
def add_family_guardian(
    actor,
    family,
    *,
    display_name,
    email,
    phone="",
    relationship=GuardianLinkDetail.Relationship.PARENT,
    permissions=None,
    evidence="",
    reason="",
    request=None,
):
    """Aggiunge un genitore/tutore alla famiglia e crea l'invito di famiglia.

    Con ``evidence`` (come il centro ha verificato la relazione) l'invito parte subito;
    senza resta «da verificare» e nessun token viene emesso.
    """
    from apps.identity.models import normalize_email

    require_center(actor)
    reason = require_reason(reason)
    email = normalize_email(email)
    if relationship not in GuardianLinkDetail.Relationship.values:
        raise PrivacyError("INVALID_RELATIONSHIP", "Relazione non valida")
    name = (display_name or "").strip()
    if not name or len(name) > 120:
        raise PrivacyError("NAME_REQUIRED", "Nome del genitore obbligatorio")
    if FamilyGuardian.objects.filter(
        family=family, email__iexact=email, revoked_at__isnull=True
    ).exists():
        raise Conflict("GUARDIAN_EXISTS", "Questa email è già tra i genitori della famiglia")
    perms = _guardian_perms(permissions)
    guardian = FamilyGuardian.objects.create(
        family=family,
        display_name=name,
        email=email,
        phone=(phone or "").strip()[:30],
        relationship=relationship,
        **perms,
    )
    record(
        "FAMILY",
        "FAMILY_GUARDIAN_ADDED",
        actor=actor,
        object_type="privacy.familyguardian",
        object_id=str(guardian.pk),
        reason=reason,
        purpose="anagrafica",
        details={
            "family": str(family.pk),
            "relationship": relationship,
            "permissions": perms,
            "verified_now": bool(evidence),
        },
    )
    _invite_family_guardian(actor, guardian, evidence=(evidence or "").strip(), request=request)
    guardian.refresh_from_db()
    return guardian


@transaction.atomic
def onboard_family(
    actor, *, reference, guardian, children=(), reason="", request=None
):
    """Iscrizione guidata: famiglia + primo genitore (con invito) + figli, tutto o niente."""
    reason = require_reason(reason)
    family, _ = create_family(
        actor,
        reference=reference,
        contact={
            "contact_name": guardian.get("display_name", "")[:120],
            "contact_email": guardian.get("email", ""),
            "contact_phone": (guardian.get("phone") or "")[:30],
        },
        reason=reason,
    )
    first = add_family_guardian(actor, family, reason=reason, request=request, **guardian)
    for child in children:
        create_student(actor, family=family, reason=reason, **child)
    return family, first


@transaction.atomic
def update_family_guardian(actor, guardian, *, expected_version, changes, reason):
    require_center(actor)
    reason = require_reason(reason)
    guardian = FamilyGuardian.objects.select_for_update().get(pk=guardian.pk)
    check_version(guardian, expected_version)
    if guardian.revoked_at:
        raise Conflict("GUARDIAN_REVOKED", "Genitore già rimosso")
    changed = []
    for key in ("display_name", "phone", "relationship"):
        if key in changes and getattr(guardian, key) != changes[key]:
            setattr(guardian, key, changes[key])
            changed.append(key)
    perms = changes.get("permissions") or {}
    for key, value in _guardian_perms(perms).items():
        if key in perms and getattr(guardian, key) != value:
            setattr(guardian, key, value)
            changed.append(key)
    if "relationship" in changed and guardian.relationship not in GuardianLinkDetail.Relationship.values:
        raise PrivacyError("INVALID_RELATIONSHIP", "Relazione non valida")
    guardian.version += 1
    guardian.save()
    if guardian.account_id and changed:
        # Le deleghe già attive seguono i nuovi permessi.
        now = timezone.now()
        for link in GuardianLink.objects.filter(
            account_id=guardian.account_id, student__family_id=guardian.family_id
        ).filter(_active_link_q(now)):
            link, detail = _locked_link(link)
            link.can_manage_availability = guardian.can_manage_availability
            detail.can_receive_notifications = guardian.can_receive_notifications
            detail.can_request_changes = guardian.can_request_changes
            detail.relationship = guardian.relationship
            link.save()
            detail.save()
    if guardian.invitation_id and changed:
        InvitationTerms.objects.filter(invitation_id=guardian.invitation_id).update(
            relationship=guardian.relationship,
            can_receive_notifications=guardian.can_receive_notifications,
            can_request_changes=guardian.can_request_changes,
        )
    record(
        "FAMILY",
        "FAMILY_GUARDIAN_UPDATED",
        actor=actor,
        object_type="privacy.familyguardian",
        object_id=str(guardian.pk),
        reason=reason,
        purpose="anagrafica",
        details={"changed_fields": changed},
    )
    return guardian


@transaction.atomic
def reinvite_family_guardian(actor, guardian, *, evidence="", reason="", request=None):
    """Nuovo invito di famiglia quando il precedente è stato revocato o è scaduto."""
    from apps.identity.models import Invitation

    require_center(actor)
    reason = require_reason(reason)
    guardian = FamilyGuardian.objects.select_for_update().get(pk=guardian.pk)
    if guardian.revoked_at or guardian.account_id:
        raise Conflict("INVALID_STATE", "Il genitore ha già un accesso o è stato rimosso")
    old = guardian.invitation
    if old and old.status in (Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT):
        if old.status == Invitation.Status.SENT and old.expires_at and old.expires_at > timezone.now():
            raise Conflict("INVITATION_ACTIVE", "L'invito è ancora valido: usa «Invia di nuovo»")
        revoke_invitation(actor, old, reason="sostituito da un nuovo invito", request=request)
    _invite_family_guardian(actor, guardian, evidence=(evidence or "").strip(), request=request)
    guardian.refresh_from_db()
    return guardian


@transaction.atomic
def remove_family_guardian(actor, guardian, *, reason, request=None):
    """Rimuove il genitore dalla famiglia: invito aperto e deleghe sui figli revocati subito."""
    from apps.identity.models import Invitation

    require_center(actor)
    reason = require_reason(reason)
    guardian = FamilyGuardian.objects.select_for_update().get(pk=guardian.pk)
    if guardian.revoked_at:
        raise Conflict("GUARDIAN_REVOKED", "Genitore già rimosso")
    inv = guardian.invitation
    if inv and inv.status in (Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT):
        revoke_invitation(actor, inv, reason=reason, request=request)
    if guardian.account_id:
        now = timezone.now()
        for link in GuardianLink.objects.filter(
            account_id=guardian.account_id, student__family_id=guardian.family_id
        ).filter(_active_link_q(now)):
            revoke_guardian_link(actor, link, reason=reason)
    guardian.revoked_at = timezone.now()
    guardian.revocation_reason = reason
    guardian.version += 1
    guardian.save()
    record(
        "FAMILY",
        "FAMILY_GUARDIAN_REMOVED",
        actor=actor,
        object_type="privacy.familyguardian",
        object_id=str(guardian.pk),
        reason=reason,
        purpose="anagrafica",
        details={"family": str(guardian.family_id)},
    )
    return guardian


def invitation_qr_link(actor, invitation, *, request=None):
    """Link d'accesso breve da mostrare come QR al genitore presente in sede."""
    from apps.identity import services
    from apps.identity.delivery import build_link

    require_center(actor)
    token, expires = _identity_call(
        services.issue_qr_token, actor, invitation.pk, request=request
    )
    record(
        "INVITE",
        "INVITE_QR_SHOWN",
        actor=actor,
        object_type="identity.invitation",
        object_id=str(invitation.pk),
        purpose="accesso portale",
    )
    return build_link("invitation", token), expires
