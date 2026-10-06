"""Registro e procedure dei diritti degli interessati (GAP-H05, artt. 12, 15-22).

Flusso: ricezione → verifica identità (per i minori: responsabilità genitoriale) →
esecuzione tramite FR24 (export, rettifica, anonimizzazione) → chiusura con audit.
Ogni transizione è scritta anche nel ledger esterno, che sopravvive a cancellazioni e restore.
"""

import calendar
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.education.models import Student
from apps.governance.audit import record

from . import ledger
from .errors import Conflict, PrivacyError
from .models import PrivacyRequest
from .registry import require_center, require_reason

R = PrivacyRequest
OPEN = (R.Status.RECEIVED, R.Status.VERIFIED, R.Status.EXTENDED)


def add_months(moment, months):
    month = moment.month - 1 + months
    year = moment.year + month // 12
    month = month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _subject_exists(subject_type, subject_id):
    if subject_type == R.SubjectType.STUDENT:
        return Student.objects.filter(pk=subject_id).exists()
    return get_user_model().objects.filter(pk=subject_id).exists()


def _log(req, event, actor, **extra):
    record(
        "PRIVACY",
        event,
        actor=actor,
        obj=req,
        purpose=f"diritti:{req.kind}",
        details={"status": req.status, **extra},
    )
    ledger.append_on_commit(
        event,
        request=str(req.pk),
        kind=req.kind,
        subject_type=req.subject_type,
        subject_id=str(req.subject_id),
        subject_pseudonym=req.subject_pseudonym,
        status=req.status,
        **extra,
    )


@transaction.atomic
def open_request(actor, *, kind, subject_type, subject_id, channel, requester_role):
    from .subjects import pseudonym

    require_center(actor)
    if kind not in R.Kind.values or subject_type not in R.SubjectType.values:
        raise PrivacyError("INVALID_KIND", "Tipo di richiesta o interessato non valido")
    if not _subject_exists(subject_type, subject_id):
        raise PrivacyError("SUBJECT_NOT_FOUND", "Interessato non trovato")
    now = timezone.now()
    req = R.objects.create(
        kind=kind,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_pseudonym=pseudonym(subject_id),
        channel=str(channel)[:60],
        requester_role=str(requester_role)[:60],
        received_at=now,
        due_at=add_months(now, 1),
        handled_by=actor,
    )
    _log(req, "REQUEST_RECEIVED", actor, due_at=req.due_at.isoformat())
    return req


def _locked(req):
    req = R.objects.select_for_update().get(pk=req.pk)
    if req.status not in OPEN:
        raise Conflict("REQUEST_CLOSED", "Richiesta già chiusa")
    return req


@transaction.atomic
def verify_identity(actor, req, *, method):
    require_center(actor)
    method = require_reason(method)
    req = _locked(req)
    if req.identity_verified_at:
        raise Conflict("ALREADY_VERIFIED", "Identità già verificata")
    req.identity_verified_at = timezone.now()
    req.identity_verification = method
    if req.status == R.Status.RECEIVED:
        req.status = R.Status.VERIFIED
    req.save()
    _log(req, "REQUEST_IDENTITY_VERIFIED", actor)
    return req


@transaction.atomic
def extend(actor, req, *, reason):
    """Proroga di due mesi per richieste complesse (art. 12.3), una sola volta."""
    require_center(actor)
    reason = require_reason(reason)
    req = _locked(req)
    if req.status == R.Status.EXTENDED:
        raise Conflict("ALREADY_EXTENDED", "Richiesta già prorogata")
    req.status = R.Status.EXTENDED
    req.extension_reason = reason
    req.due_at = add_months(req.due_at, 2)
    req.save()
    _log(req, "REQUEST_EXTENDED", actor, due_at=req.due_at.isoformat())
    return req


def _require_verified(req):
    if not req.identity_verified_at:
        raise Conflict("IDENTITY_NOT_VERIFIED", "Verificare prima l'identità")


def _close(req, actor, outcome, motivation=""):
    req.status = R.Status.COMPLETED
    req.outcome = outcome
    req.motivation = motivation[:500]
    req.closed_at = timezone.now()
    req.handled_by = actor
    req.save()
    _log(req, "REQUEST_COMPLETED", actor, outcome=outcome)


@transaction.atomic
def fulfil_export(actor, req, *, audience, fmt="json"):
    """Accesso (art. 15) o portabilità (art. 20): export protetto per l'audience indicata."""
    from .exports import create_export
    from .subjects import collect, render

    require_center(actor)
    req = _locked(req)
    _require_verified(req)
    if req.kind not in (R.Kind.ACCESS, R.Kind.PORTABILITY):
        raise PrivacyError("WRONG_KIND", "Richiesta non di accesso o portabilità")
    if req.kind == R.Kind.PORTABILITY and fmt != "json":
        # Formato strutturato, di uso comune e leggibile da dispositivo automatico.
        raise PrivacyError("PORTABILITY_JSON", "La portabilità usa il formato JSON")
    if fmt not in ("json", "csv"):
        raise PrivacyError("INVALID_FORMAT", "Formato json o csv")
    payload = collect(req.subject_type, req.subject_id)
    content = render(
        payload,
        fmt,
        subject_type=req.subject_type,
        subject_id=req.subject_id,
        purpose=req.kind,
    )
    export, token = create_export(
        actor=actor,
        audience=audience,
        content=content,
        fmt=fmt,
        filename=f"export-{req.kind.lower()}-{req.subject_pseudonym}.{fmt}",
        purpose=f"diritti:{req.kind}",
        privacy_request=req,
    )
    _close(req, actor, "EXPORT_ISSUED")
    return export, token


@transaction.atomic
def fulfil_rectification(actor, req, *, changes, reason):
    from .subjects import rectify

    require_center(actor)
    req = _locked(req)
    _require_verified(req)
    if req.kind != R.Kind.RECTIFICATION:
        raise PrivacyError("WRONG_KIND", "Richiesta non di rettifica")
    if not isinstance(changes, dict) or not changes:
        raise PrivacyError("CHANGES_REQUIRED", "Indicare i campi da rettificare")
    try:
        changed = rectify(
            actor, req.subject_type, req.subject_id, changes, reason=reason
        )
    except ValueError as exc:
        raise PrivacyError("NOT_RECTIFIABLE", str(exc)) from exc
    _close(req, actor, "RECTIFIED", ",".join(changed))
    return changed


@transaction.atomic
def fulfil_erasure(actor, req, *, motivation):
    """Cancellazione governata: anonimizzazione irreversibile dei dati identificativi.

    Le righe storiche (calendario, audit) restano pseudonime perché soggette a retention
    (D09): la motivazione viene registrata come richiesto da reg2 §Diritti.
    """
    from .subjects import anonymize_account, anonymize_student

    require_center(actor)
    motivation = require_reason(motivation)
    req = _locked(req)
    _require_verified(req)
    if req.kind != R.Kind.ERASURE:
        raise PrivacyError("WRONG_KIND", "Richiesta non di cancellazione")
    reason = f"art. 17 richiesta {req.pk}"
    if req.subject_type == R.SubjectType.STUDENT:
        anonymize_student(
            Student.objects.get(pk=req.subject_id), reason=reason, actor=actor
        )
    else:
        account = get_user_model().objects.get(pk=req.subject_id)
        if account.is_superuser:
            raise Conflict("SUPERUSER", "Revocare prima i privilegi amministrativi")
        anonymize_account(account, reason=reason, actor=actor)
    _close(req, actor, "ANONYMIZED", motivation)
    return req


@transaction.atomic
def close_manually(actor, req, *, outcome, motivation):
    """Limitazione/opposizione o esiti gestiti fuori dal software, con motivazione."""
    require_center(actor)
    motivation = require_reason(motivation)
    req = _locked(req)
    _require_verified(req)
    if outcome not in (
        "RESTRICTED",
        "OBJECTION_UPHELD",
        "OBJECTION_REJECTED",
        "NO_DATA",
    ):
        raise PrivacyError("INVALID_OUTCOME", "Esito non valido")
    _close(req, actor, outcome, motivation)
    return req


@transaction.atomic
def reject(actor, req, *, motivation):
    require_center(actor)
    motivation = require_reason(motivation)
    req = _locked(req)
    req.status = R.Status.REJECTED
    req.outcome = "REJECTED"
    req.motivation = motivation
    req.closed_at = timezone.now()
    req.handled_by = actor
    req.save()
    _log(req, "REQUEST_REJECTED", actor)
    return req


def overdue(now=None):
    now = now or timezone.now()
    return R.objects.filter(status__in=OPEN, due_at__lt=now)


def due_soon(days=7, now=None):
    now = now or timezone.now()
    return R.objects.filter(
        status__in=OPEN, due_at__gte=now, due_at__lt=now + timedelta(days=days)
    )


SELF_SERVICE_KINDS = ("ACCESS", "PORTABILITY", "RECTIFICATION", "ERASURE", "RESTRICTION", "OBJECTION")


@transaction.atomic
def open_self_request(actor, *, kind, subject_type, subject_id, requester_role):
    """P5 · «I miei dati»: l'interessato (o il genitore) apre la richiesta dal portale.

    L'autorizzazione sul soggetto la verifica la vista; qui si registra come le richieste
    raccolte dal centro (canale PORTALE, scadenza un mese, ledger).
    """
    from .subjects import pseudonym

    if kind not in SELF_SERVICE_KINDS or subject_type not in R.SubjectType.values:
        raise PrivacyError("INVALID_KIND", "Tipo di richiesta o interessato non valido")
    if R.objects.filter(
        kind=kind, subject_type=subject_type, subject_id=subject_id, status__in=OPEN
    ).exists():
        raise Conflict("REQUEST_ALREADY_OPEN", "C'è già una richiesta uguale in corso")
    now = timezone.now()
    req = R.objects.create(
        kind=kind,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_pseudonym=pseudonym(subject_id),
        channel="PORTALE",
        requester_role=str(requester_role)[:60],
        received_at=now,
        due_at=add_months(now, 1),
        handled_by=actor,
    )
    _log(req, "REQUEST_RECEIVED", actor, due_at=req.due_at.isoformat())
    return req
