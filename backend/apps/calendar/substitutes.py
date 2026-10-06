"""P4 · DC-TUTOR-ASSENTE: sostituto abilitato, altrimenti recupero.

Per ogni tutor attivo prova la lezione con quel tutor usando lo stesso controllo dei
comandi (disponibilità, abilitazioni, carico, pause, risorse) dentro un savepoint
annullato: nessuna scrittura resta.
"""

from django.db import transaction

from apps.education.models import Tutor
from apps.education.path_services import DomainError

from .operations import require_future_active, target_of, validate_changes

MAX_TUTORS = 60


def codes_of(error):
    detail = error.detail if isinstance(error.detail, dict) else {}
    found = detail.get("violations") or [detail.get("code") or "NOT_ADMISSIBLE"]
    return sorted({str(c) for c in found})


def substitutes(lesson):
    require_future_active(lesson)
    duration = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
    rows = []
    tutors = (
        Tutor.objects.filter(active=True)
        .exclude(pk=lesson.tutor_id)
        .order_by("display_name")[:MAX_TUTORS]
    )
    with transaction.atomic():
        for tutor in tutors:
            sid = transaction.savepoint()
            try:
                target = target_of(lesson, {"tutor_id": str(tutor.id)})
                validate_changes([(lesson, target, duration)])
                rows.append({"tutor_id": str(tutor.id), "name": tutor.display_name, "ok": True, "codes": []})
            except DomainError as error:
                rows.append({"tutor_id": str(tutor.id), "name": tutor.display_name, "ok": False, "codes": codes_of(error)})
            finally:
                transaction.savepoint_rollback(sid)
    rows.sort(key=lambda r: (not r["ok"], r["name"]))
    return {
        "lesson_id": str(lesson.id),
        "version": lesson.version,
        "substitutes": rows,
        "fallback": "RECOVERY" if not any(r["ok"] for r in rows) else None,
    }
