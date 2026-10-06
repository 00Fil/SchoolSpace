"""Notifiche (outbox s3-comunicazioni) per i comandi calendario di s2.

Tutte le funzioni vanno chiamate dentro la transazione del comando: se il commit
fallisce non resta alcuna notifica. Payload minimi: nessun elenco di partecipanti o
membri del gruppo, nessun link video (vedi ``apps.communications.payloads``).
"""

from django.db.models import Q
from django.utils import timezone

from apps.communications.calendar_hooks import (
    lesson_payload,
    lesson_recipients,
    notify_lesson,
)
from apps.communications.services import Recipient, emit

# Operazioni s2 che cambiano orario/risorse di una lezione pubblicata.
RESCHEDULE_OPERATIONS = {"MOVE", "MODIFY", "SWAP", "RESCHEDULE", "SERIES_SPLIT"}
CANCEL_OPERATIONS = {"CANCEL", "SERIES_EXDATE", "SERIES_CANCEL"}


def lesson_changed(lesson, operation, before=None):
    """Spostamento/modifica/scambio → lesson.rescheduled; cancellazioni → cancelled."""
    if operation in CANCEL_OPERATIONS or lesson.state == "CANCELLED":
        return notify_lesson(lesson, "LESSON_CANCEL")
    return notify_lesson(lesson, "LESSON_RESCHEDULE", before=before)


def _lesson_event(event_type, lesson, key, extra=None):
    payload = lesson_payload(lesson, "")
    payload.update(extra or {})
    return emit(
        event_type,
        payload,
        lesson_recipients(lesson),
        idempotency_key=key,
        subject_ref=f"lesson:{lesson.id}",
    )


def makeup_scheduled(lesson, obligation):
    return _lesson_event(
        "lesson.makeup_scheduled",
        lesson,
        f"calendar:lesson:{lesson.id}:v{lesson.version}",
        {"recovery_id": str(obligation.id)},
    )


def lesson_completed(lesson):
    return _lesson_event(
        "lesson.completed",
        lesson,
        f"calendar:lesson:{lesson.id}:v{lesson.version}",
    )


def attendance_corrected(lesson, sequence):
    return _lesson_event(
        "attendance.corrected",
        lesson,
        f"calendar:attendance:{lesson.id}:r{sequence}",
    )


def recovery_changed(obligation, event_type):
    """recovery.created / recovery.waived ai destinatari della lezione d'origine."""
    lesson = obligation.origin_lesson
    return emit(
        event_type,
        {
            "recovery_id": str(obligation.id),
            "lesson_id": str(lesson.id),
            "subject_name": lesson.subject.name,
            "minutes": obligation.minutes_remaining,
            "state": obligation.state,
            "version": obligation.version,
        },
        lesson_recipients(lesson),
        idempotency_key=f"calendar:recovery:{obligation.id}:v{obligation.version}",
        subject_ref=f"recovery:{obligation.id}",
    )


def center_recipients():
    from apps.identity.models import RoleGrant

    now = timezone.now()
    grants = (
        RoleGrant.objects.filter(
            role="CENTER", valid_from__lte=now, revoked_at__isnull=True
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("account")
    )
    return [
        Recipient(g.account, {"role": "center"}) for g in grants if g.account.is_active
    ]


def conflict_opened(case):
    """Pratica aperta: solo operatori del centro (le famiglie non vedono pratiche)."""
    return emit(
        "conflict.opened",
        {
            "conflict_id": str(case.id),
            "lesson_id": str(case.lesson_id) if case.lesson_id else None,
            "kind": case.kind,
            "week_start": case.week_start.isoformat() if case.week_start else None,
        },
        center_recipients(),
        idempotency_key=f"calendar:conflict:{case.id}:v1",
        subject_ref=f"conflict:{case.id}",
    )


def change_request_event(row, event_type):
    """change_request.submitted al centro; change_request.decided al richiedente."""
    if event_type == "change_request.submitted":
        recipients = center_recipients()
    else:
        recipients = [Recipient(row.requested_by, {"role": "requester"})]
    return emit(
        event_type,
        {
            "change_request_id": str(row.id),
            "lesson_id": str(row.lesson_id),
            "kind": row.kind,
            "state": row.state,
            "version": row.version,
        },
        recipients,
        idempotency_key=f"calendar:change:{row.id}:v{row.version}",
        subject_ref=f"change:{row.id}",
    )
