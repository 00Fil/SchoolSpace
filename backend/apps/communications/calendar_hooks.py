"""Emissione degli eventi di calendario (pubblicazione, spostamento, cancellazione).

Chiamato da ``apps.calendar.services`` dentro la stessa transazione che scrive lezione,
prenotazioni, audit e ``CalendarEvent``: se il commit fallisce non resta alcuna
notifica; se riesce, l'obbligo di notifica è persistente anche senza Redis.

Destinatari (perimetro calcolato al momento dell'evento, come i portali):
- tutor assegnato (account attivo);
- account studente del partecipante con ruolo STUDENT attivo;
- tutori legali con delega verificata, ``can_view``, valida e ruolo GUARDIAN attivo.
Ognuno riceve solo i nomi dei *propri* studenti; nessun elenco dei membri del gruppo,
nessun link video (si ottiene da ``/occurrences/{id}/meeting``).
"""

from django.db.models import Q
from django.utils import timezone

from .services import Recipient, emit

EVENT_TYPES = {
    "LESSON_PUBLISHED": "lesson.published",
    "LESSON_RESCHEDULE": "lesson.rescheduled",
    "LESSON_CANCEL": "lesson.cancelled",
}


def _active_role(account_ids, role, now):
    from apps.identity.models import RoleGrant

    return set(
        RoleGrant.objects.filter(
            account_id__in=account_ids,
            role=role,
            valid_from__lte=now,
            revoked_at__isnull=True,
        )
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .values_list("account_id", flat=True)
    )


def lesson_recipients(lesson):
    from apps.education.models import Student

    now = timezone.now()
    recipients = []
    tutor_account = lesson.tutor.account
    if tutor_account is not None and tutor_account.is_active:
        recipients.append(Recipient(tutor_account, {"role": "tutor"}))
    student_ids = list(lesson.participants.values_list("student_id", flat=True))
    students = list(
        Student.objects.filter(
            pk__in=student_ids, account__isnull=False
        ).select_related("account")
    )
    student_role = _active_role([s.account_id for s in students], "STUDENT", now)
    for student in students:
        if student.account.is_active and student.account_id in student_role:
            recipients.append(
                Recipient(
                    student.account,
                    {"role": "student", "student_names": [student.display_name]},
                )
            )
    # s4: stesse regole dei portali (maggiore età, riconferma) + can_receive_notifications.
    from apps.identity.policies import notification_guardian_links

    links = list(
        notification_guardian_links(student_ids, now).select_related(
            "account", "student"
        )
    )
    guardian_role = _active_role([l.account_id for l in links], "GUARDIAN", now)
    for link in links:
        if link.account.is_active and link.account_id in guardian_role:
            recipients.append(
                Recipient(
                    link.account,
                    {"role": "guardian", "student_names": [link.student.display_name]},
                )
            )
    return recipients


def lesson_payload(lesson, kind, before=None):
    payload = {
        "lesson_id": str(lesson.id),
        "version": lesson.version,
        "subject_name": lesson.subject.name,
        "mode": lesson.mode,
        "location": lesson.location,
        "start_at": lesson.start_at.isoformat(),
        "end_at": lesson.end_at.isoformat(),
        "state": lesson.state,
    }
    if kind == "LESSON_RESCHEDULE" and before:
        payload["previous_start_at"] = before["start_at"]
        payload["previous_end_at"] = before["end_at"]
    return payload


def notify_lesson(lesson, kind, before=None):
    """Registra l'evento di comunicazione per un cambiamento di calendario."""
    return emit(
        EVENT_TYPES[kind],
        lesson_payload(lesson, kind, before),
        lesson_recipients(lesson),
        idempotency_key=f"calendar:lesson:{lesson.id}:v{lesson.version}",
        subject_ref=f"lesson:{lesson.id}",
        audience="calendar.lesson",
    )
