"""Calendario pubblico del mese e rettifiche in bozza (v0.9.11).

Regole:
- ogni mese ha **un solo calendario pubblico** (quello che vedono famiglie e tutor);
- **ogni modifica** del centro a un mese (sposta, cambia durata, cancella, scambia,
  sostituisci il tutor, aggiungi le lezioni di una richiesta verificata) finisce **in bozza**
  come rettifica: famiglie e tutor continuano a vedere il calendario pubblicato;
- il **gestore del centro** pubblica tutte le rettifiche del mese insieme, oppure sceglie
  di **pubblicare subito** quella che sta facendo.

Una rettifica si convalida al momento dell'inserimento rieseguendo, in una transazione
annullata, tutte le rettifiche in bozza del mese più quella nuova con gli stessi servizi
del calendario: se non si potrebbe pubblicare, non entra nemmeno in bozza.
"""

import logging
import uuid
from datetime import datetime

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.education.path_services import Conflict, DomainError

from .autoplan import ROME, month_end, month_start
from .models import AutoPlan, CalendarCorrection

log = logging.getLogger(__name__)

LESSON_OPS = ("reschedule", "cancel", "modify")


class _Rollback(Exception):
    pass


def _month_of(instant):
    return month_start(instant.astimezone(ROME).date())


def _dt(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _lesson(pk):
    from apps.calendar.models import LessonOccurrence

    try:
        return LessonOccurrence.objects.select_related("subject", "tutor").get(pk=pk)
    except (LessonOccurrence.DoesNotExist, ValueError, TypeError) as exc:
        raise DomainError("NOT_FOUND", "Lezione non trovata") from exc


def _when(start, end=None):
    local = start.astimezone(ROME)
    days = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
    text = f"{days[local.weekday()]} {local.day}/{local.month} {local:%H:%M}"
    if end is not None:
        text += f"–{end.astimezone(ROME):%H:%M}"
    return text


def _who(lesson):
    names = [p.student.display_name for p in lesson.participants.select_related("student")]
    return ", ".join(names[:3]) + ("…" if len(names) > 3 else "")


def _summary(op, lesson=None, other=None, command=None, plan=None):
    command = command or {}
    if op == "plan":
        n = plan.lessons.filter(state="PROPOSED").count()
        req = plan.request
        who = req.group_label or (req.student.display_name if req.student_id else "")
        return f"Nuove lezioni: {req.subject.name}{' · ' + who if who else ''} ({n})"
    head = f"{lesson.subject.name} · {_who(lesson)}"
    if op == "cancel":
        return f"Cancella {head}, {_when(lesson.start_at, lesson.end_at)}"
    if op == "reschedule":
        start = _dt(command.get("start_at"))
        end = _dt(command.get("end_at")) or start + (lesson.end_at - lesson.start_at)
        return f"Sposta {head}: {_when(lesson.start_at, lesson.end_at)} → {_when(start, end)}"
    if op == "swap":
        return f"Scambia {head} ({_when(lesson.start_at)}) con {other.subject.name} ({_when(other.start_at)})"
    if op == "modify":
        changes = command.get("changes") or {}
        parts = []
        if changes.get("tutor_id"):
            from apps.education.models import Tutor

            t = Tutor.objects.filter(pk=changes["tutor_id"]).first()
            parts.append(f"sostituto {t.display_name if t else '?'}")
        if changes.get("start_at"):
            parts.append(_when(_dt(changes["start_at"])))
        if changes.get("mode"):
            parts.append("passa online" if changes["mode"] == "ONLINE" else "passa in presenza")
        if changes.get("space_id") and not changes.get("mode"):
            parts.append("cambio aula")
        return f"Modifica {head}, {_when(lesson.start_at)}: {', '.join(parts) or 'dettagli'}"
    return head


# --- esecuzione ------------------------------------------------------------------------


def _defer_constraints():
    """I servizi del calendario contano su vincoli differiti fino al loro controllo finale:
    dopo un'operazione precedente nella stessa transazione (SET CONSTRAINTS ALL IMMEDIATE)
    vanno riportati in differita, altrimenti una lezione appena creata (ancora senza
    partecipanti e prenotazioni) verrebbe rifiutata."""
    from django.db import connection

    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL DEFERRED")


def _execute(row, actor):
    """Esegue la rettifica con i servizi del calendario (versioni lette al momento)."""
    from apps.calendar import operations
    from apps.calendar.models import LessonOccurrence
    from apps.calendar.services import change_lesson

    from .autoplan_publish import publish

    _defer_constraints()
    key = f"correction:{row.id}:{uuid.uuid4()}"
    cmd = dict(row.command or {})
    reason = (cmd.pop("reason", "") or "Rettifica del calendario del mese").strip()[:200]
    if row.op == "plan":
        return publish(row.plan_id, actor)
    version = LessonOccurrence.objects.only("version").get(pk=row.lesson_id).version
    if row.op == "reschedule":
        body = {"expected_version": version, "start_at": _dt(cmd["start_at"]), "reason": reason}
        if cmd.get("end_at"):
            body["end_at"] = _dt(cmd["end_at"])
        return change_lesson(actor, row.lesson_id, "reschedule", body, key)
    if row.op == "cancel":
        return change_lesson(actor, row.lesson_id, "cancel", {"expected_version": version, "reason": reason}, key)
    if row.op == "modify":
        changes = dict(cmd.get("changes") or {})
        if changes.get("start_at"):
            changes["start_at"] = _dt(changes["start_at"])
        try:
            return operations.modify_lesson(
                actor, row.lesson_id, {"expected_version": version, "reason": reason, "changes": changes}, key
            )
        except (KeyError, TypeError) as exc:
            raise DomainError(
                "UNSUPPORTED", "Questa lezione non si può modificare così: spostala o annullala e ripianificala"
            ) from exc
    if row.op == "swap":
        second = LessonOccurrence.objects.only("version").get(pk=row.other_id).version
        return operations.swap_lessons(
            actor,
            {"first_id": row.lesson_id, "first_version": version, "second_id": row.other_id,
             "second_version": second, "reason": reason},
            key,
        )
    raise DomainError("INVALID_OP", "Rettifica sconosciuta")


def _message(error):
    detail = getattr(error, "detail", None)
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, (list, tuple)):
            msg = " ".join(str(m) for m in msg)
        return str(msg or detail.get("code") or error)[:300]
    if isinstance(error, DatabaseError):
        return "Vincoli del calendario non rispettati (sovrapposizione, aula o posti)"
    return str(error)[:300]


def _code(error):
    detail = getattr(error, "detail", None)
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])
    return "CORRECTION_INVALID"


def _simulate(actor, pending, new):
    """Prova la bozza del mese + la nuova rettifica senza lasciare effetti."""
    try:
        with transaction.atomic():
            for row in pending:
                try:
                    with transaction.atomic():
                        _execute(row, actor)
                except (DomainError, DatabaseError):
                    pass  # rettifica già non più valida: la segnala la pubblicazione
            try:
                with transaction.atomic():
                    _execute(new, actor)
            except (DomainError, DatabaseError) as error:
                raise Conflict(
                    _code(error),
                    "La rettifica non si può applicare al calendario del mese: " + _message(error),
                ) from error
            raise _Rollback
    except _Rollback:
        return


# --- API di dominio --------------------------------------------------------------------


def pending(month):
    return CalendarCorrection.objects.filter(month=month, state="PENDING").order_by("created_at")


def _replace(lesson_ids):
    """Una sola rettifica in bozza per lezione: la nuova sostituisce la precedente."""
    rows = CalendarCorrection.objects.filter(state__in=("PENDING", "FAILED"), op__in=LESSON_OPS, lesson_id__in=lesson_ids)
    stale = list(rows)
    swaps = CalendarCorrection.objects.filter(state="PENDING", op="swap").filter(
        lesson_id__in=lesson_ids
    ) | CalendarCorrection.objects.filter(state="PENDING", op="swap", other_id__in=lesson_ids)
    if swaps.exists():
        raise Conflict(
            "LESSON_IN_DRAFT_SWAP",
            "La lezione è già in uno scambio in bozza: pubblica o scarta prima quella rettifica",
        )
    return stale


@transaction.atomic
def propose(actor, op, data, publish_now=False):
    """Registra una rettifica del calendario del mese (o la pubblica subito)."""
    from apps.calendar.services import authorize

    authorize(actor)
    if op not in dict(CalendarCorrection.OPS) or op == "plan":
        raise DomainError("INVALID_OP", "Operazione non ammessa")
    lesson = _lesson(data.get("lesson_id"))
    other = _lesson(data.get("other_id")) if op == "swap" else None
    if lesson.state != "PUBLISHED" or lesson.start_at <= timezone.now():
        raise DomainError("LESSON_NOT_ACTIVE", "Si possono rettificare solo lezioni future in programma")
    command = _plain({k: v for k, v in data.items() if k not in ("lesson_id", "other_id", "expected_version")})
    if op == "reschedule" and not command.get("start_at"):
        raise DomainError("INVALID_PAYLOAD", "start_at richiesto")
    month = _month_of(lesson.start_at)
    stale = _replace([lesson.id] + ([other.id] if other else []))
    row = CalendarCorrection(
        month=month, op=op, lesson=lesson, other=other, command=command, actor=actor,
        summary=_summary(op, lesson, other, command)[:300],
    )
    row.id = uuid.uuid4()
    for s in stale:
        s.state = "DISCARDED"
        s.save(update_fields=["state", "updated_at"])
    if publish_now:
        try:
            with transaction.atomic():
                _execute(row, actor)
        except (DomainError, DatabaseError) as error:
            raise Conflict(_code(error), "Non si può pubblicare la rettifica: " + _message(error)) from error
        row.state, row.applied_at = "APPLIED", timezone.now()
        row.save()
        return row
    _simulate(actor, list(pending(month).exclude(pk__in=[s.pk for s in stale])), row)
    row.save()
    return row


@transaction.atomic
def propose_plan(actor, plan, publish_now=False):
    """Lezioni di una richiesta verificata: in bozza nel calendario del mese o subito."""
    from .autoplan_publish import publish

    if publish_now:
        result = publish(plan.id, actor)
        return None, result
    row = CalendarCorrection(
        month=plan.month, op="plan", plan=plan, actor=actor,
        summary=_summary("plan", plan=plan)[:300],
    )
    row.id = uuid.uuid4()
    CalendarCorrection.objects.filter(plan=plan, state="PENDING").update(state="DISCARDED")
    _simulate(actor, list(pending(plan.month)), row)
    row.save()
    return row, {"published": 0, "awaiting": 0, "confirmations_sent": 0, "draft": True}


def publish_month(actor, month):
    """Pubblica le rettifiche in bozza del mese (in ordine) e l'eventuale bozza mensile."""
    from apps.calendar.services import authorize

    from .autoplan_publish import publish

    authorize(actor)
    applied, failed = 0, []
    for row in list(pending(month)):
        try:
            with transaction.atomic():
                _execute(row, actor)
            row.state, row.applied_at, row.error = "APPLIED", timezone.now(), ""
            applied += 1
        except (DomainError, DatabaseError) as error:
            log.info("correction.failed", extra={"correction_id": str(row.id), "detail": str(getattr(error, "detail", error))[:500]})
            row.state, row.error = "FAILED", _message(error)
            failed.append({"id": str(row.id), "summary": row.summary, "error": row.error})
        row.save(update_fields=["state", "applied_at", "error", "updated_at"])
    draft = AutoPlan.objects.filter(month=month, state="DRAFT", request__isnull=True).first()
    plan_result = None
    if draft is not None:
        try:
            plan_result = publish(draft.id, actor)
        except DomainError as error:
            failed.append({"id": str(draft.id), "summary": "Bozza del calendario mensile", "error": _message(error)})
    return {"applied": applied, "failed": failed, "plan": plan_result}


def publish_one(actor, correction_id):
    """Pubblica subito una sola rettifica in bozza (le altre del mese restano in bozza)."""
    from apps.calendar.services import authorize

    from .autoplan_publish import publish

    authorize(actor)
    row = CalendarCorrection.objects.select_related("plan").get(pk=correction_id)
    if row.state not in ("PENDING", "FAILED"):
        raise Conflict("CORRECTION_NOT_DRAFT", "La rettifica è già stata pubblicata o scartata")
    try:
        with transaction.atomic():
            if row.op == "plan":
                publish(row.plan_id, actor)
            else:
                _execute(row, actor)
    except (DomainError, DatabaseError) as error:
        row.state, row.error = "FAILED", _message(error)
        row.save(update_fields=["state", "error", "updated_at"])
        raise Conflict(_code(error), "Non si può pubblicare la rettifica: " + row.error) from error
    row.state, row.applied_at, row.error = "APPLIED", timezone.now(), ""
    row.save(update_fields=["state", "applied_at", "error", "updated_at"])
    return row


@transaction.atomic
def discard(correction_id):
    row = CalendarCorrection.objects.select_for_update().get(pk=correction_id)
    if row.state not in ("PENDING", "FAILED"):
        raise Conflict("CORRECTION_NOT_DRAFT", "La rettifica è già stata pubblicata o scartata")
    row.state = "DISCARDED"
    row.save(update_fields=["state", "updated_at"])
    if row.op == "plan" and row.plan and row.plan.state == "DRAFT" and row.plan.request_id:
        # le lezioni della richiesta tornano da verificare (la bozza resta disponibile)
        type(row.plan.request).objects.filter(pk=row.plan.request_id).update(
            planning_state="REVIEW", completed_at=None
        )
    return row


def discard_for_plans(plan_ids):
    CalendarCorrection.objects.filter(plan_id__in=plan_ids, state__in=("PENDING", "FAILED")).update(
        state="DISCARDED"
    )


def pending_targets(lo, hi):
    """(tutor, studenti, inizio, fine) dei nuovi orari delle rettifiche in bozza."""
    out = []
    rows = CalendarCorrection.objects.filter(state="PENDING", op__in=("reschedule", "modify")).select_related("lesson")
    for r in rows:
        cmd = r.command or {}
        start = _dt(cmd.get("start_at") or (cmd.get("changes") or {}).get("start_at"))
        if start is None or r.lesson is None:
            continue
        end = _dt(cmd.get("end_at")) or start + (r.lesson.end_at - r.lesson.start_at)
        if start < hi and end > lo:
            tutor = (cmd.get("changes") or {}).get("tutor_id") or r.lesson.tutor_id
            sids = list(r.lesson.participants.values_list("student_id", flat=True))
            out.append((uuid.UUID(str(tutor)), sids, start, end))
    return out


# --- stato del mese --------------------------------------------------------------------


def _lesson_brief(l):
    return {
        "id": str(l.id),
        "start_at": l.start_at.isoformat(),
        "end_at": l.end_at.isoformat(),
        "tutor": str(l.tutor_id),
        "tutor_name": l.tutor.display_name,
        "subject_name": l.subject.name,
        "mode": l.mode,
        "participants": [
            {"student_id": str(p.student_id), "name": p.student.display_name}
            for p in l.participants.select_related("student")
        ],
    }


def _draft_lessons(plan):
    from apps.education.models import Student

    rows = list(plan.lessons.filter(state="PROPOSED").select_related("tutor", "subject"))
    names = dict(
        Student.objects.filter(pk__in={s for l in rows for s in l.participants}).values_list("id", "display_name")
    )
    return [
        {
            "id": str(l.id),
            "start_at": l.start_at.isoformat(),
            "end_at": l.end_at.isoformat(),
            "tutor": str(l.tutor_id),
            "tutor_name": l.tutor.display_name,
            "subject_name": l.subject.name,
            "mode": l.mode,
            "participants": [{"student_id": s, "name": names.get(uuid.UUID(s), "")} for s in l.participants],
        }
        for l in rows
    ]


def correction_json(row):
    out = {
        "id": str(row.id),
        "op": row.op,
        "state": row.state,
        "summary": row.summary,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "actor": getattr(row.actor, "username", ""),
        "lesson": _lesson_brief(row.lesson) if row.lesson_id else None,
        "other": _lesson_brief(row.other) if row.other_id else None,
        "target": None,
        "lessons": [],
        "request_id": str(row.plan.request_id) if row.plan_id and row.plan.request_id else None,
    }
    cmd = row.command or {}
    if row.op == "reschedule" and row.lesson_id:
        start = _dt(cmd.get("start_at"))
        end = _dt(cmd.get("end_at")) or start + (row.lesson.end_at - row.lesson.start_at)
        out["target"] = {"start_at": start.isoformat(), "end_at": end.isoformat()}
    if row.op == "modify" and row.lesson_id and (cmd.get("changes") or {}).get("start_at"):
        start = _dt(cmd["changes"]["start_at"])
        out["target"] = {"start_at": start.isoformat(), "end_at": (start + (row.lesson.end_at - row.lesson.start_at)).isoformat()}
    if row.op == "plan" and row.plan_id:
        out["lessons"] = _draft_lessons(row.plan)
    return out


def month_json(month):
    from apps.calendar.models import LessonOccurrence

    from .autoplan import at
    from .autoplan_publish import public_plan

    first, last = month, month_end(month)
    lo, hi = at(first, 0), at(last, 1440)
    public = LessonOccurrence.objects.filter(state__in=("PUBLISHED", "COMPLETED"), start_at__gte=lo, start_at__lt=hi)
    plan = public_plan(first)
    rows = list(
        CalendarCorrection.objects.filter(month=first, state__in=("PENDING", "FAILED"))
        .select_related("lesson__subject", "lesson__tutor", "other__subject", "other__tutor", "plan", "actor")
        .order_by("created_at")
    )
    draft = AutoPlan.objects.filter(month=first, state="DRAFT", request__isnull=True).first()
    # richieste ancora in verifica: le loro lezioni occupano già gli orari (non sono pubbliche)
    review = list(
        AutoPlan.objects.filter(month=first, state="DRAFT", request__isnull=False, request__planning_state="REVIEW")
        .select_related("request__subject", "request__student")
    )
    last_applied = (
        CalendarCorrection.objects.filter(month=first, state="APPLIED").order_by("-applied_at").values_list("applied_at", flat=True).first()
    )
    stamps = [t for t in (plan.published_at if plan else None, last_applied) if t]
    n_public = public.count()
    is_public = bool(plan) or n_public > 0
    n_pending = sum(1 for r in rows if r.state == "PENDING")
    state = "DRAFT" if (n_pending or draft or any(r.state == "FAILED" for r in rows)) else ("PUBLISHED" if is_public else "EMPTY")
    return {
        "month": first.isoformat()[:7],
        "state": state,
        "public": is_public,
        "published_at": max(stamps).isoformat() if stamps else None,
        "public_lessons": n_public,
        "pending": n_pending,
        "failed": sum(1 for r in rows if r.state == "FAILED"),
        "corrections": [correction_json(r) for r in rows],
        "in_review": [
            {"request_id": str(p.request_id), "lessons": _draft_lessons(p)} for p in review
        ],
        "draft_plan": (
            {"id": str(draft.id), "lessons": _draft_lessons(draft), "created_at": draft.created_at.isoformat()}
            if draft
            else None
        ),
    }
