"""Raccolta dei dati dell'interessato, export, rettifica e anonimizzazione (GAP-H05, FR24)."""

import csv
import hashlib
import hmac
import io
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.governance.audit import _is_secret_key, record

from .models import (
    FamilyProfile,
    GuardianLinkDetail,
    StudentImportKey,
    StudentProfile,
)

EXPORT_SCHEMA = "privacy-export/1"
ANON_DOMAIN = "anonimizzato.invalid"
# Mai negli export: credenziali, hash di token, payload tecnici del solver.
EXCLUDED_FIELDS = {"password", "token_hash", "data", "environment", "input_hash"}


def pseudonym(subject_id):
    key = (settings.SECRET_KEY + ":privacy-pseudonym").encode()
    return hmac.new(key, str(subject_id).encode(), hashlib.sha256).hexdigest()[:12]


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def serialize(obj):
    out = {}
    for field in obj._meta.concrete_fields:
        name = field.attname
        if field.name in EXCLUDED_FIELDS or _is_secret_key(field.name):
            continue
        out[field.name if not field.is_relation else field.name] = _value(
            getattr(obj, name)
        )
    return out


def _related_rows(instance, skip=()):
    """Tutte le righe che puntano direttamente all'istanza (FK o 1:1)."""
    sections = {}
    for rel in instance._meta.related_objects:
        if rel.many_to_many or rel.related_model._meta.label_lower in skip:
            continue
        model = rel.related_model
        rows = model._base_manager.filter(**{rel.field.name: instance.pk})
        data = [serialize(row) for row in rows[:5000]]
        if data:
            sections[model._meta.label_lower] = data
    return sections


def collect_student(student):
    family = student.family
    profile = FamilyProfile.objects.filter(family=family).first()
    links = []
    for link in GuardianLink.objects.filter(student=student).select_related("account"):
        detail = GuardianLinkDetail.objects.filter(link=link).first()
        links.append(
            {
                **serialize(link),
                "guardian_name": link.account.get_full_name(),
                "guardian_email": link.account.email,
                "detail": serialize(detail) if detail else None,
            }
        )
    return {
        "student": serialize(student),
        "family": {
            **serialize(family),
            "profile": serialize(profile) if profile else None,
        },
        "guardian_links": links,
        "related": _related_rows(
            student,
            skip={"education.guardianlink"},
        ),
    }


def identity_invitations(email):
    from apps.identity.models import Invitation, normalize_email

    return Invitation.objects.filter(email__iexact=normalize_email(email))


def identity_audit_for(account):
    from django.db.models import Q

    from apps.identity.models import IdentityAuditEvent

    return IdentityAuditEvent.objects.filter(
        Q(actor=account) | Q(subject=account)
    ).order_by("occurred_at")


def _minimize_identity_audit(account):
    """L'audit identity è append-only (trigger PG): si azzera solo l'IP, in manutenzione
    governata; attore e soggetto restano come riferimenti all'account pseudonimizzato."""
    from django.db import connection, models

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.audit_maintenance = 'on'")
        return models.QuerySet.update(
            identity_audit_for(account).filter(ip__isnull=False), ip=None
        )


def _clear_identity_credentials(account, tag):
    from apps.identity.models import (
        PasswordResetToken,
        RecoveryCode,
        TOTPDevice,
        UserSession,
    )

    now = timezone.now()
    UserSession.objects.filter(account=account, revoked_at__isnull=True).update(
        revoked_at=now, revoked_reason="anonymized"
    )
    UserSession.objects.filter(account=account).update(ip=None, user_agent="")
    TOTPDevice.objects.filter(account=account).delete()
    RecoveryCode.objects.filter(account=account).delete()
    PasswordResetToken.objects.filter(account=account).delete()
    # Inviti chiusi: l'email è un dato personale, resta un indirizzo pseudonimo.
    identity_invitations(account.email).exclude(
        status__in=["PENDING_VERIFICATION", "SENT"]
    ).update(email=f"anon-{tag}@{ANON_DOMAIN}")
    _minimize_identity_audit(account)


def collect_account(account):
    from apps.governance.models import AuditEvent

    base = serialize(account)
    for field in ("is_superuser", "is_staff"):
        base.pop(field, None)
    return {
        "account": base,
        "role_grants": [serialize(g) for g in account.role_grants.all()],
        "guardian_links": [
            {
                **serialize(link),
                "student_name": link.student.display_name,
                "detail": serialize(d)
                if (d := GuardianLinkDetail.objects.filter(link=link).first())
                else None,
            }
            for link in account.guardian_links.select_related("student")
        ],
        "student_record": [
            serialize(s) for s in Student.objects.filter(account=account)
        ],
        "tutor_profile": [
            serialize(t)
            for t in type(account)
            ._meta.get_field("tutor_profile")
            .related_model.objects.filter(account=account)
        ],
        "invitations": [
            {
                "created_at": _value(i.created_at),
                "role": i.role,
                "student": _value(i.student_id),
                "status": i.status,
            }
            for i in identity_invitations(account.email)
        ],
        "sessions": [
            {
                "created_at": _value(x.created_at),
                "last_seen_at": _value(x.last_seen_at),
                "ip": x.ip,
                "user_agent": x.user_agent,
                "revoked_at": _value(x.revoked_at),
            }
            for x in account.sessions.all()[:500]
        ],
        "security_audit": [
            {
                "occurred_at": _value(e.occurred_at),
                "operation": e.operation,
                "ip": e.ip,
                "as_actor": e.actor_id == account.pk,
            }
            for e in identity_audit_for(account)[:5000]
        ],
        "audit_as_actor": [
            {
                "occurred_at": _value(e.occurred_at),
                "category": e.category,
                "operation": e.operation,
                "object_type": e.object_type,
            }
            for e in AuditEvent.objects.filter(actor=account)[:5000]
        ],
    }


def collect(subject_type, subject_id):
    if subject_type == "STUDENT":
        return collect_student(Student.objects.get(pk=subject_id))
    return collect_account(get_user_model().objects.get(pk=subject_id))


def render(payload, fmt, *, subject_type, subject_id, purpose):
    envelope = {
        "schema": EXPORT_SCHEMA,
        "generated_at": timezone.now().isoformat(),
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "purpose": purpose,
        "data": payload,
    }
    if fmt == "json":
        return json.dumps(envelope, ensure_ascii=False, indent=2, default=str).encode()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "record", "field", "value"])

    def walk(section, record_id, value):
        if isinstance(value, dict):
            rid = value.get("id", record_id)
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    walk(f"{section}.{key}", rid, item)
                else:
                    writer.writerow([section, rid, key, "" if item is None else item])
        elif isinstance(value, list):
            for item in value:
                walk(section, record_id, item)
        else:
            writer.writerow([section, record_id, "", value])

    for key in ("schema", "generated_at", "subject_type", "subject_id", "purpose"):
        writer.writerow(["meta", "", key, envelope[key]])
    walk("data", str(subject_id), payload)
    return buffer.getvalue().encode("utf-8-sig")


# --- Rettifica ---------------------------------------------------------------

STUDENT_FIELDS = {"display_name", "level", "birth_date"}
FAMILY_FIELDS = {"contact_name", "contact_email", "contact_phone"}
ACCOUNT_FIELDS = {"first_name", "last_name", "email"}


@transaction.atomic
def rectify(actor, subject_type, subject_id, changes, *, reason):
    from .registry import require_reason, update_student

    reason = require_reason(reason)
    if subject_type == "STUDENT":
        allowed = STUDENT_FIELDS | FAMILY_FIELDS
        if set(changes) - allowed:
            raise ValueError(", ".join(sorted(set(changes) - allowed)))
        student = Student.objects.get(pk=subject_id)
        student_changes = {k: v for k, v in changes.items() if k in STUDENT_FIELDS}
        if "birth_date" in student_changes and isinstance(
            student_changes["birth_date"], str
        ):
            student_changes["birth_date"] = date.fromisoformat(
                student_changes["birth_date"]
            )
        if student_changes:
            update_student(
                actor,
                student,
                expected_version=None,
                changes=student_changes,
                reason=reason,
            )
        family_changes = {k: v for k, v in changes.items() if k in FAMILY_FIELDS}
        if family_changes:
            profile, _ = FamilyProfile.objects.get_or_create(family=student.family)
            for key, value in family_changes.items():
                setattr(profile, key, value)
            profile.save()
        changed = sorted(changes)
    else:
        if set(changes) - ACCOUNT_FIELDS:
            raise ValueError(", ".join(sorted(set(changes) - ACCOUNT_FIELDS)))
        account = get_user_model().objects.select_for_update().get(pk=subject_id)
        for key, value in changes.items():
            setattr(account, key, value)
        account.save()
        changed = sorted(changes)
    record(
        "PRIVACY",
        "RECTIFIED",
        actor=actor,
        object_type=subject_type.lower(),
        object_id=str(subject_id),
        reason=reason,
        details={"changed_fields": changed},
    )
    return changed


# --- Anonimizzazione -----------------------------------------------------------


def anonymize_account(account, *, reason, actor=None):
    from apps.identity.models import RoleGrant

    from .registry import revoke_guardian_link

    now = timezone.now()
    tag = pseudonym(account.pk)
    with transaction.atomic():
        RoleGrant.objects.filter(account=account, revoked_at__isnull=True).update(
            revoked_at=now
        )
        for link in GuardianLink.objects.filter(
            account=account, revoked_at__isnull=True
        ):
            revoke_guardian_link(actor, link, reason=reason, system=True)
        from .registry import revoke_open_invitations

        revoke_open_invitations(actor, email=account.email)
        _clear_identity_credentials(account, tag)
        account.username = f"anon-{tag}"
        account.email = f"anon-{tag}@{ANON_DOMAIN}"
        account.first_name = ""
        account.last_name = ""
        account.is_active = False
        account.is_staff = False
        account.email_verified = False
        account.mfa_required = False
        account.set_unusable_password()
        account.save()
        tutor_model = type(account)._meta.get_field("tutor_profile").related_model
        tutor_model.objects.filter(account=account).update(
            display_name=f"Tutor anonimizzato {tag}"
        )
        record(
            "PRIVACY",
            "ACCOUNT_ANONYMIZED",
            actor=actor,
            object_type="identity.account",
            object_id=str(account.pk),
            reason=reason,
            details={"pseudonym": tag},
        )
    return tag


def anonymize_student(student, *, reason, actor=None):
    """Anonimizzazione governata: le righe necessarie a calendario e storico restano,
    ma senza dati identificativi (minimizzazione prevalente, reg2 §Diritti)."""
    from .registry import revoke_guardian_link

    now = timezone.now()
    tag = pseudonym(student.pk)
    with transaction.atomic():
        student = Student.objects.select_for_update().get(pk=student.pk)
        for link in GuardianLink.objects.filter(
            student=student, revoked_at__isnull=True
        ):
            revoke_guardian_link(actor, link, reason=reason, system=True)
        student.display_name = f"Studente anonimizzato {tag}"
        student.level = ""
        student.active = False
        student.save()
        StudentProfile.objects.update_or_create(
            student=student, defaults={"birth_date": None, "anonymized_at": now}
        )
        StudentImportKey.objects.filter(student=student).delete()
        from apps.identity.models import Invitation

        from .registry import revoke_open_invitations

        revoke_open_invitations(actor, student_id=student.pk)
        for inv in Invitation.objects.filter(student=student):
            Invitation.objects.filter(pk=inv.pk).update(
                email=f"anon-{pseudonym(inv.pk)}@{ANON_DOMAIN}"
            )
        if student.account_id:
            anonymize_account(student.account, reason=reason, actor=actor)
        family = student.family
        if (
            not Student.objects.filter(family=family)
            .exclude(display_name__startswith="Studente anonimizzato ")
            .exists()
        ):
            ftag = pseudonym(family.pk)
            Family.objects.filter(pk=family.pk).update(reference=f"ANON-{ftag}")
            FamilyProfile.objects.update_or_create(
                family=family,
                defaults={
                    "contact_name": "",
                    "contact_email": "",
                    "contact_phone": "",
                    "anonymized_at": now,
                },
            )
        record(
            "PRIVACY",
            "STUDENT_ANONYMIZED",
            actor=actor,
            object_type="education.student",
            object_id=str(student.pk),
            reason=reason,
            details={"pseudonym": tag},
        )
    return tag


def is_anonymized(subject_type, subject_id):
    if subject_type == "STUDENT":
        return StudentProfile.objects.filter(
            student_id=subject_id, anonymized_at__isnull=False
        ).exists()
    return (
        get_user_model()
        .objects.filter(pk=subject_id, email__endswith="@" + ANON_DOMAIN)
        .exists()
    )
