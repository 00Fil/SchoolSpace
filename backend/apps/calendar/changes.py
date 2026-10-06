"""Modifiche di orario e durata proposte dal centro (drag & drop in Agenda).

Flusso:
1. il centro trascina una lezione (o ne tira il bordo): ``propose`` verifica il nuovo orario
   con le stesse regole dello spostamento diretto e crea una ``LessonChange`` PENDING con una
   risposta per il tutor e una per ogni studente; tutor, famiglie e studenti ricevono notifica;
2. ogni interessato accetta o rifiuta (``answer``): quando tutti hanno accettato la modifica
   si applica; un rifiuto la chiude e avvisa il centro;
3. il centro può confermarla subito senza attendere (``confirm_now``) o ritirarla (``withdraw``).
La lezione non cambia finché la modifica non è applicata. Qualsiasi altra modifica della
lezione (spostamento diretto, cancellazione) annulla le modifiche in attesa.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.education.path_services import Conflict, DomainError

from .models import LessonChange, LessonChangeAnswer, LessonOccurrence


def now():
    return timezone.now()


def change_json(change, user=None):
    answers = list(change.answers.select_related("tutor", "student"))
    lesson = change.lesson
    return {
        "id": str(change.id),
        "lesson_id": str(change.lesson_id),
        "state": change.state,
        "start_at": change.start_at.isoformat(),
        "end_at": change.end_at.isoformat(),
        "previous_start_at": change.previous_start_at.isoformat(),
        "previous_end_at": change.previous_end_at.isoformat(),
        "version": change.version,
        "created_at": change.created_at.isoformat() if change.created_at else None,
        "resolution": change.resolution,
        "lesson": {
            "subject": lesson.subject.name,
            "tutor": lesson.tutor.display_name,
            "mode": lesson.mode,
            "students": [p.student.display_name for p in lesson.participants.select_related("student")],
        },
        "answers": [
            {
                "id": str(a.id),
                "party": a.party,
                "who": a.tutor.display_name if a.tutor_id else a.student.display_name,
                "status": a.status,
                "note": a.note,
                "mine": bool(user and can_answer(user, a)),
            }
            for a in answers
        ],
    }


def lock_lesson(lesson_id):
    return (
        LessonOccurrence.objects.select_for_update(of=("self",))
        .select_related("demand", "publication__plan__run__snapshot__policy", "subject", "tutor")
        .get(pk=lesson_id)
    )


def supersede(lesson, keep=None):
    """La lezione è cambiata per altra via: le modifiche in attesa non valgono più."""
    rows = LessonChange.objects.filter(lesson=lesson, state="PENDING")
    if keep is not None:
        rows = rows.exclude(pk=keep)
    rows.update(state="CANCELLED", resolution="Superata da un’altra modifica della lezione", resolved_at=now())


def recipients_for_change(change):
    from apps.communications.calendar_hooks import lesson_recipients

    return lesson_recipients(change.lesson)


def notify_requested(change):
    from apps.communications.services import emit

    lesson = change.lesson
    return emit(
        "lesson.change_requested",
        {
            "change_id": str(change.id),
            "lesson_id": str(lesson.id),
            "subject_name": lesson.subject.name,
            "mode": lesson.mode,
            "start_at": change.start_at.isoformat(),
            "end_at": change.end_at.isoformat(),
            "previous_start_at": change.previous_start_at.isoformat(),
            "previous_end_at": change.previous_end_at.isoformat(),
        },
        recipients_for_change(change),
        idempotency_key=f"calendar:change:{change.id}:requested",
        subject_ref=f"lesson-change:{change.id}",
    )


def notify_center(change, outcome):
    from apps.communications.services import Recipient, emit

    account = change.requested_by
    if not account.is_active:
        return None
    lesson = change.lesson
    return emit(
        "lesson.change_answered",
        {
            "change_id": str(change.id),
            "lesson_id": str(lesson.id),
            "subject_name": lesson.subject.name,
            "start_at": change.start_at.isoformat(),
            "end_at": change.end_at.isoformat(),
            "outcome": outcome,
            "resolution": change.resolution[:150],
        },
        [Recipient(account, {"role": "center"})],
        idempotency_key=f"calendar:change:{change.id}:{outcome.lower()}",
        subject_ref=f"lesson-change:{change.id}",
    )


@transaction.atomic
def propose(actor, lesson_id, command, key):
    """Crea la modifica in attesa, oppure (``confirm_now``) la applica subito."""
    from .services import authorize, change_lesson, check_reschedule

    authorize(actor)
    start, end = command["start_at"], command["end_at"]
    if command.get("confirm_now"):
        return {
            "applied": True,
            "lesson": change_lesson(
                actor,
                lesson_id,
                "reschedule",
                {"expected_version": command["expected_version"], "start_at": start, "end_at": end},
                key,
            ),
        }
    lesson = lock_lesson(lesson_id)
    if lesson.version != command["expected_version"]:
        raise Conflict("VERSION_CONFLICT", "Lezione cambiata: ricaricare")
    if lesson.state != "PUBLISHED" or lesson.start_at <= now():
        raise DomainError("LESSON_NOT_ACTIVE", "Si possono modificare solo lezioni future e attive")
    if start == lesson.start_at and end == lesson.end_at:
        raise DomainError("NO_CHANGE", "Orario e durata sono invariati")
    check_reschedule(lesson, start, end)
    previous = LessonChange.objects.select_for_update().filter(lesson=lesson, state="PENDING").first()
    if previous and previous.start_at == start and previous.end_at == end:
        return {"applied": False, "change": change_json(previous, actor)}
    supersede(lesson)
    change = LessonChange.objects.create(
        lesson=lesson,
        start_at=start,
        end_at=end,
        previous_start_at=lesson.start_at,
        previous_end_at=lesson.end_at,
        lesson_version=lesson.version,
        requested_by=actor,
    )
    LessonChangeAnswer.objects.create(change=change, party="TUTOR", tutor_id=lesson.tutor_id)
    for student_id in lesson.participants.values_list("student_id", flat=True):
        LessonChangeAnswer.objects.create(change=change, party="STUDENT", student_id=student_id)
    notify_requested(change)
    return {"applied": False, "change": change_json(change, actor)}


def lock_change(change_id):
    return LessonChange.objects.select_for_update(of=("self",)).select_related("lesson__subject", "lesson__tutor").get(pk=change_id)


def apply(change, actor, resolution):
    """Applica la modifica (in un savepoint): se nel frattempo non è più valida la chiude come FAILED."""
    from .services import change_lesson

    try:
        with transaction.atomic():
            change_lesson(
                actor,
                change.lesson_id,
                "reschedule",
                {"expected_version": change.lesson_version, "start_at": change.start_at, "end_at": change.end_at},
                f"lesson-change:{change.id}",
                keep_change=change.id,
            )
    except (DomainError, IntegrityError) as error:
        detail = getattr(error, "detail", None)
        message = str(detail.get("message")) if isinstance(detail, dict) and detail.get("message") else "orario non più disponibile"
        change.state = "FAILED"
        change.resolution = f"Non applicata: {message}"[:200]
        change.resolved_at = now()
        change.version += 1
        change.save()
        return False
    change.state = "APPLIED"
    change.resolution = resolution[:200]
    change.resolved_by = actor if actor.pk else None
    change.resolved_at = now()
    change.version += 1
    change.save()
    return True


@transaction.atomic
def confirm_now(actor, change_id):
    from .services import authorize

    authorize(actor)
    change = lock_change(change_id)
    if change.state != "PENDING":
        raise Conflict("CHANGE_NOT_PENDING", "La modifica non è più in attesa")
    ok = apply(change, actor, "Confermata dal centro senza attendere le risposte")
    if not ok:
        raise DomainError("CHANGE_NOT_APPLICABLE", change.resolution)
    return change_json(change, actor)


@transaction.atomic
def withdraw(actor, change_id):
    from .services import authorize

    authorize(actor)
    change = lock_change(change_id)
    if change.state != "PENDING":
        raise Conflict("CHANGE_NOT_PENDING", "La modifica non è più in attesa")
    change.state = "CANCELLED"
    change.resolution = "Ritirata dal centro"
    change.resolved_by = actor
    change.resolved_at = now()
    change.version += 1
    change.save()
    return change_json(change, actor)


def can_answer(user, answer):
    from apps.identity.policies import active_roles, visible_students

    if not user or not user.is_authenticated:
        return False
    if answer.party == "TUTOR":
        return bool(answer.tutor.account_id) and answer.tutor.account_id == user.id and "TUTOR" in active_roles(user)
    if answer.student.account_id and answer.student.account_id == user.id:
        return True
    return visible_students(user).filter(pk=answer.student_id).exists()


@transaction.atomic
def answer(actor, change_id, accept, note=""):
    change = lock_change(change_id)
    mine = [a for a in change.answers.select_for_update(of=("self",)).select_related("tutor", "student") if can_answer(actor, a)]
    if not mine:
        raise DomainError("NOT_FOUND", "Modifica inesistente")
    if change.state != "PENDING":
        raise Conflict("CHANGE_NOT_PENDING", "La modifica non è più in attesa")
    for a in mine:
        if a.status == "PENDING":
            a.status = "ACCEPTED" if accept else "REJECTED"
            a.answered_by = actor
            a.answered_at = now()
            a.note = note[:300]
            a.save()
    who = ", ".join(a.tutor.display_name if a.tutor_id else a.student.display_name for a in mine)
    if not accept:
        change.state = "REJECTED"
        change.resolution = f"Rifiutata ({who}){': ' + note if note else ''}"[:200]
        change.resolved_by = actor
        change.resolved_at = now()
        change.version += 1
        change.save()
        notify_center(change, "REJECTED")
    elif not change.answers.exclude(status="ACCEPTED").exists():
        ok = apply(change, change.requested_by, "Confermata da tutti gli interessati")
        notify_center(change, "APPLIED" if ok else "FAILED")
    return change_json(change, actor)


def visible(user):
    """Center: tutte; altri: quelle in cui devono (o hanno dovuto) rispondere."""
    from datetime import timedelta

    from django.db.models import Q

    from apps.identity.policies import active_roles, is_center, visible_students

    rows = LessonChange.objects.select_related("lesson__subject", "lesson__tutor").order_by("start_at")
    recent = Q(state="PENDING") | Q(resolved_at__gte=now() - timedelta(days=30))
    if is_center(user):
        return rows.filter(recent)
    scope = Q(answers__party="STUDENT", answers__student__in=visible_students(user)) | Q(
        answers__party="STUDENT", answers__student__account=user
    )
    if "TUTOR" in active_roles(user):
        scope |= Q(answers__party="TUTOR", answers__tutor__account=user)
    return rows.filter(recent).filter(scope).distinct()
