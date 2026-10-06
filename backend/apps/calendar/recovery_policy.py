"""Regole dei recuperi decise dal committente il 3/10/2026 (D06).

- Assenza della famiglia: recupero se avvisata almeno ``RECOVERY_NOTICE_HOURS`` ore prima;
  il centro può concederlo comunque, in modo esplicito e tracciato (``grant_late_notice``).
- Scadenza: entro la fine dell'anno scolastico della lezione d'origine.
- Lezioni di gruppo e chiusure impreviste: decide il centro caso per caso (nessuna regola automatica).
- Assenza del tutor: si propone un sostituto abilitato, altrimenti si crea il recupero.
"""

from zoneinfo import ZoneInfo

from django.conf import settings

from .commands import DomainError, now

ROME = ZoneInfo("Europe/Rome")
FAMILY_CAUSES = {"FAMILY_REQUEST", "STUDENT_ABSENCE"}


def notice_limit():
    return int(getattr(settings, "RECOVERY_NOTICE_HOURS", 24))


def reported_at(lesson):
    """Momento dell'avviso: la prima richiesta di assenza/cancellazione, altrimenti adesso."""
    from .models import ChangeRequest

    first = (
        ChangeRequest.objects.filter(lesson=lesson, kind__in=("ABSENCE", "CANCEL"))
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return first or now()


def notice_hours(lesson):
    return (lesson.start_at - reported_at(lesson)).total_seconds() / 3600


def check_entitlement(lesson, command):
    """Solleva LATE_NOTICE se il preavviso è breve e il centro non ha concesso il recupero."""
    if command.get("cause") not in FAMILY_CAUSES:
        return {"late_notice": False, "granted_by_center": False}
    hours = notice_hours(lesson)
    late = hours < notice_limit()
    if late and not command.get("grant_late_notice"):
        raise DomainError(
            "LATE_NOTICE",
            f"Assenza avvisata con meno di {notice_limit()} ore di anticipo: "
            "il recupero spetta solo se il centro lo concede",
        )
    return {
        "late_notice": late,
        "granted_by_center": late,
        "notice_hours": round(max(hours, 0), 1),
    }


def due_by(moment):
    """Fine dell'anno scolastico che contiene la lezione d'origine (None se non configurato)."""
    from apps.scheduling.models import SchoolYear

    day = moment.astimezone(ROME).date()
    year = (
        SchoolYear.objects.filter(start_date__lte=day, end_date__gte=day)
        .order_by("-start_date")
        .first()
    )
    return year.end_date if year else None


def recovery_periods(moment):
    """Periodi per i recuperi dell'anno della lezione, dal giorno della lezione in poi."""
    from apps.scheduling.models import StudyPeriod

    day = moment.astimezone(ROME).date()
    rows = StudyPeriod.objects.filter(
        kind="RECOVERY",
        school_year__start_date__lte=day,
        school_year__end_date__gte=day,
        end_date__gte=day,
    ).order_by("start_date")
    return [
        {"start_date": p.start_date.isoformat(), "end_date": p.end_date.isoformat(), "label": p.label}
        for p in rows
    ]


def check_due(obligation, start_at):
    limit = due_by(obligation.origin_lesson.start_at)
    if limit and start_at.astimezone(ROME).date() > limit:
        raise DomainError(
            "RECOVERY_PAST_DUE",
            f"Il recupero va fatto entro la fine dell'anno scolastico ({limit.isoformat()})",
        )
