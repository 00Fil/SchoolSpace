"""Import iniziale da template CSV versionato (GAP-H06, T17).

* Template versionati in ``TEMPLATES``; l'intestazione deve coincidere esattamente.
* Validazione completa prima di scrivere: con errori non si scrive nulla.
* ``dry_run``: tutto viene eseguito in una transazione annullata; nessun invito (T17).
* Idempotenza per chiavi naturali: ``family_reference``, ``student_key``, email del tutore,
  coppia tutore/studente. Un secondo import identico non crea duplicati.
* Tutori senza account: si crea un invito di identity in attesa di verifica (nessun token).
  Il token parte solo con ``create_invites=True`` e ``verify_links=True`` in esecuzione reale
  (la verifica documentale è avvenuta prima dell'import). Nome e cognome del tutore nel CSV
  non vengono usati: l'account nasce all'accettazione dell'invito (minimizzazione).
"""

import csv
import hashlib
import io
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.governance.audit import record

from .errors import PrivacyError
from .models import (
    FamilyProfile,
    GuardianLinkDetail,
    ImportBatch,
    StudentImportKey,
    StudentProfile,
)
from .registry import (
    create_guardian_link,
    existing_account,
    invite_guardian,
    require_center,
    verify_invitation_relation,
)

TEMPLATES = {
    "1": [
        "family_reference",
        "family_contact_name",
        "family_contact_email",
        "family_contact_phone",
        "student_key",
        "student_display_name",
        "student_level",
        "student_birth_date",
        "guardian_email",
        "guardian_first_name",
        "guardian_last_name",
        "guardian_relationship",
        "guardian_can_manage_availability",
        "guardian_can_receive_notifications",
    ]
}
MAX_ROWS = 5000
BOOL = {
    "true": True,
    "1": True,
    "si": True,
    "sì": True,
    "false": False,
    "0": False,
    "no": False,
    "": None,
}


class _Rollback(Exception):
    pass


def _bool(value, row, field, errors):
    key = (value or "").strip().lower()
    if key not in BOOL:
        errors.append({"row": row, "field": field, "code": "INVALID_BOOLEAN"})
        return None
    return BOOL[key]


def parse(content, template_version):
    if template_version not in TEMPLATES:
        raise PrivacyError("UNKNOWN_TEMPLATE", "Versione del template non supportata")
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PrivacyError("ENCODING", "Il file deve essere UTF-8") from exc
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames != TEMPLATES[template_version]:
        raise PrivacyError(
            "HEADER_MISMATCH",
            "Intestazione diversa dal template v" + template_version,
        )
    rows, errors = [], []
    for index, raw in enumerate(reader, start=2):
        if index - 1 > MAX_ROWS:
            raise PrivacyError("TOO_MANY_ROWS", f"Massimo {MAX_ROWS} righe")
        row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
        if None in raw:
            errors.append({"row": index, "code": "EXTRA_COLUMNS"})
            continue
        for field in ("family_reference", "student_key", "student_display_name"):
            if not row[field]:
                errors.append({"row": index, "field": field, "code": "REQUIRED"})
        for field, limit in (
            ("family_reference", 80),
            ("student_key", 80),
            ("student_display_name", 120),
            ("student_level", 60),
        ):
            if len(row[field]) > limit:
                errors.append({"row": index, "field": field, "code": "TOO_LONG"})
        for field in ("family_contact_email", "guardian_email"):
            if row[field]:
                try:
                    validate_email(row[field])
                except ValidationError:
                    errors.append(
                        {"row": index, "field": field, "code": "INVALID_EMAIL"}
                    )
        birth = None
        if row["student_birth_date"]:
            try:
                birth = date.fromisoformat(row["student_birth_date"])
                if birth >= timezone.localdate():
                    raise ValueError
            except ValueError:
                errors.append(
                    {
                        "row": index,
                        "field": "student_birth_date",
                        "code": "INVALID_DATE",
                    }
                )
        relationship = row["guardian_relationship"] or "PARENT"
        if relationship not in GuardianLinkDetail.Relationship.values:
            errors.append(
                {
                    "row": index,
                    "field": "guardian_relationship",
                    "code": "INVALID_CHOICE",
                }
            )
        manage = _bool(
            row["guardian_can_manage_availability"],
            index,
            "guardian_can_manage_availability",
            errors,
        )
        notify = _bool(
            row["guardian_can_receive_notifications"],
            index,
            "guardian_can_receive_notifications",
            errors,
        )
        rows.append(
            {
                **row,
                "line": index,
                "birth": birth,
                "relationship": relationship,
                "manage": bool(manage),
                "notify": True if notify is None else notify,
            }
        )
    # Coerenza tra righe: la stessa chiave studente non può cambiare famiglia o nome.
    seen = {}
    for row in rows:
        key = row["student_key"]
        sig = (row["family_reference"], row["student_display_name"])
        if key in seen and seen[key] != sig:
            errors.append(
                {
                    "row": row["line"],
                    "field": "student_key",
                    "code": "INCONSISTENT_DUPLICATE",
                }
            )
        seen.setdefault(key, sig)
    return rows, errors


PRE_IMPORT_EVIDENCE = "verifica documentale pre-import"


def _import_invitation(actor, row, student, batch, summary, verify_links, send):
    from apps.identity.models import Invitation, normalize_email

    invitation = Invitation.objects.filter(
        email__iexact=normalize_email(row["guardian_email"]),
        role="GUARDIAN",
        student=student,
        status__in=["PENDING_VERIFICATION", "SENT"],
    ).first()
    if invitation is None:
        invitation = invite_guardian(
            actor,
            student=student,
            email=row["guardian_email"],
            relationship=row["relationship"],
            permissions={
                "can_manage_availability": row["manage"],
                "can_receive_notifications": row["notify"],
            },
            reason=f"import {batch.id}",
            import_batch=None if batch._state.adding else batch,
        )
        summary["invitations_created"] += 1
    else:
        summary["invitations_existing"] += 1
    # Il token parte solo con verifica pre-import dichiarata E richiesta esplicita di invio.
    if send and verify_links and invitation.status == "PENDING_VERIFICATION":
        verify_invitation_relation(actor, invitation, evidence=PRE_IMPORT_EVIDENCE)
        summary["invites_sent"] += 1


def _apply(actor, rows, *, verify_links, create_invites, batch):
    summary = {
        "families_created": 0,
        "families_existing": 0,
        "students_created": 0,
        "students_existing": 0,
        "links_created": 0,
        "links_existing": 0,
        "invitations_created": 0,
        "invitations_existing": 0,
        "invites_sent": 0,
        "conflicts": [],
    }
    now = timezone.now()
    for row in rows:
        family = Family.objects.filter(reference=row["family_reference"]).first()
        if family is None:
            family = Family.objects.create(reference=row["family_reference"])
            FamilyProfile.objects.create(
                family=family,
                contact_name=row["family_contact_name"],
                contact_email=row["family_contact_email"].lower(),
                contact_phone=row["family_contact_phone"],
            )
            summary["families_created"] += 1
        else:
            summary["families_existing"] += 1
        key = (
            StudentImportKey.objects.filter(source_key=row["student_key"])
            .select_related("student")
            .first()
        )
        if key is None:
            student = Student.objects.create(
                family=family,
                display_name=row["student_display_name"],
                level=row["student_level"],
            )
            StudentProfile.objects.create(student=student, birth_date=row["birth"])
            StudentImportKey.objects.create(
                source_key=row["student_key"], student=student
            )
            summary["students_created"] += 1
        else:
            student = key.student
            summary["students_existing"] += 1
            if student.family_id != family.pk:
                summary["conflicts"].append(
                    {"row": row["line"], "code": "STUDENT_FAMILY_CHANGED"}
                )
                continue
        if not row["guardian_email"]:
            continue
        account = existing_account(row["guardian_email"])
        if account is None:
            # Nessun account: il tutore entra solo tramite invito di identity (B02).
            _import_invitation(
                actor, row, student, batch, summary, verify_links, create_invites
            )
            continue
        link = (
            GuardianLink.objects.filter(
                student=student, account=account, revoked_at__isnull=True
            )
            .order_by("-created_at")
            .first()
        )
        if link is None:
            link = create_guardian_link(
                actor,
                student=student,
                account=account,
                relationship=row["relationship"],
                permissions={
                    "can_manage_availability": row["manage"],
                    "can_receive_notifications": row["notify"],
                },
                valid_from=now,
                reason=f"import {batch.id}",
                command="privacy_import",
            )
            if verify_links:
                link.verified = True
                link.save()
                GuardianLinkDetail.objects.filter(link=link).update(
                    verified_by=actor,
                    verified_at=now,
                    verification_method=PRE_IMPORT_EVIDENCE,
                )
            summary["links_created"] += 1
        else:
            summary["links_existing"] += 1
    return summary


def run_import(
    actor,
    content,
    *,
    template_version="1",
    dry_run=True,
    verify_links=False,
    create_invites=False,
):
    require_center(actor)
    raw = content if isinstance(content, bytes) else content.encode()
    digest = hashlib.sha256(raw).hexdigest()
    rows, errors = parse(raw, template_version)
    batch = ImportBatch(
        actor=actor,
        template_version=template_version,
        file_sha256=digest,
        dry_run=dry_run,
        rows=len(rows),
    )
    if errors:
        batch.status = "INVALID"
        batch.errors = errors[:500]
        batch.summary = {}
    else:
        try:
            with transaction.atomic():
                summary = None
                if not dry_run:
                    batch.status = "RUNNING"
                    batch.save()
                summary = _apply(
                    actor,
                    rows,
                    verify_links=verify_links,
                    # T17: nessun invito durante il dry-run, qualunque sia l'opzione.
                    create_invites=create_invites and not dry_run,
                    batch=batch,
                )
                if summary["conflicts"]:
                    batch.status = "CONFLICT"
                    raise _Rollback()
                if dry_run:
                    raise _Rollback()
                batch.status = "APPLIED"
                batch.summary = summary
                batch.save()
        except _Rollback:
            batch.status = "CONFLICT" if summary["conflicts"] else "DRY_RUN"
            batch.summary = summary
            batch.errors = summary["conflicts"][:500]
    with transaction.atomic():
        if not ImportBatch.objects.filter(pk=batch.pk).exists():
            batch._state.adding = True
            batch.save(force_insert=True)
        record(
            "IMPORT",
            "IMPORT_" + batch.status,
            actor=actor,
            obj=batch,
            command="privacy_import",
            details={
                "template_version": template_version,
                "file_sha256": digest,
                "rows": len(rows),
                "dry_run": dry_run,
                "summary": {k: v for k, v in batch.summary.items() if k != "conflicts"},
                "errors": len(batch.errors),
            },
        )
    return batch
