"""Comandi operativi del calendario (GAP-E02, E03, E04).

Tutti i cambi passano dallo stesso motore: DTO corrente di ogni settimana fisica
interessata (origine e destinazione), lezioni cambiate sbloccate, validatore
indipendente su calendario fisso + proposta, transizioni tutor anche ai confini,
sostituzione atomica delle prenotazioni e vincoli DB forzati prima del successo.
"""

from datetime import timedelta
from django.db import transaction
from django.conf import settings
from apps.scheduling.contracts import utc_epoch
from apps.scheduling.source import DataNotReady
from apps.scheduling.validator import validate_assignments
from apps.scheduling.revision import bump_revision
from .models import (
    LessonOccurrence,
    LessonParticipant,
    RecoveryObligation,
    Attendance,
    AttendanceRevision,
)
from .context import (
    operations_compile,
    synthetic_unit,
    unit_key,
    week_of,
    OCCUPYING,
)
from .services import (
    current_dto,
    new_codes,
    save_bookings,
    assert_complete,
    force_constraints,
    cross_week_transitions,
    summary,
    reopen_recovery,
)
from .commands import (
    Command,
    audit,
    event,
    require_reason,
    check_version,
    now,
    DomainError,
)
from .scope import authorize_any, is_lesson_tutor
from . import notifications
from apps.identity.policies import is_center

FIELDS = ("start_at", "tutor_id", "mode", "location", "space_id", "video_id")
DURATION_CATALOG = (60, 90, 120)


def lesson_queryset():
    return LessonOccurrence.objects.select_related(
        "demand__request",
        "publication__plan__run__snapshot__policy",
        "recovery",
        "tutor",
    )


def lock_lessons(ids):
    """Lock in ordine di id per evitare deadlock tra comandi concorrenti."""
    keys = [str(i) for i in ids]
    rows = {
        str(l.id): l
        for l in lesson_queryset()
        .select_for_update(of=("self",))
        .filter(pk__in=keys)
        .order_by("id")
    }
    if any(k not in rows for k in keys):
        raise DomainError("NOT_FOUND", "Lezione inesistente")
    return [rows[k] for k in keys]


def full_summary(lesson):
    return {
        **summary(lesson),
        "tutor_id": str(lesson.tutor_id),
        "mode": lesson.mode,
        "location": lesson.location,
        "space_id": str(lesson.space_id) if lesson.space_id else None,
        "video_id": str(lesson.video_id) if lesson.video_id else None,
        "week_start": week_of(lesson.start_at).isoformat(),
    }


def require_future_active(lesson, expected_version=None):
    if expected_version is not None:
        check_version(lesson, expected_version)
    if lesson.state != "PUBLISHED":
        raise DomainError("LESSON_NOT_ACTIVE", "Lezione non attiva")
    if lesson.start_at <= now():
        raise DomainError(
            "PAST_LESSON",
            "Lezione iniziata o conclusa: usare la correzione amministrativa",
        )


def target_of(lesson, changes):
    target = {f: getattr(lesson, f) for f in FIELDS}
    for field, value in changes.items():
        if field not in FIELDS:
            raise DomainError("UNSUPPORTED_FIELD", f"Campo non modificabile: {field}")
        target[field] = value
    for field in ("tutor_id", "space_id", "video_id"):
        target[field] = str(target[field]) if target[field] else None
    if target["start_at"] <= now():
        raise DomainError("PAST_LESSON", "Il nuovo inizio deve essere futuro")
    if target["start_at"].second or target["start_at"].microsecond:
        raise DomainError("MINUTE_PRECISION", "Precisione al minuto richiesta")
    return target


def target_assignment(lesson, target, epoch, duration):
    minute = (target["start_at"] - epoch).total_seconds() / 60
    if not minute.is_integer():
        raise DomainError("MINUTE_PRECISION", "Precisione al minuto richiesta")
    return {
        "demand_key": unit_key(lesson),
        "tutor_id": target["tutor_id"],
        "mode": target["mode"],
        "location": target["location"],
        "space_id": target["space_id"],
        "video_id": target["video_id"],
        "start": int(minute),
        "end": int(minute) + duration,
    }


def snapshot_policy(lessons):
    pairs = {
        (
            l.publication.plan.run.snapshot.policy_id,
            l.publication.plan.run.snapshot.data["mode"],
        )
        for l in lessons
    }
    if len(pairs) != 1:
        raise DomainError(
            "POLICY_MISMATCH", "Lezioni pianificate con policy diverse: non combinabili"
        )
    lesson = lessons[0]
    return (
        lesson.publication.plan.run.snapshot.policy,
        lesson.publication.plan.run.snapshot.data["mode"],
    )


def validate_changes(changes):
    """changes: [(lesson, target, duration_minutes)]. Lezioni nuove non salvate ammesse.

    Restituisce per ogni lezione i profili (tutor, risorse) della settimana di arrivo."""
    lessons = [lesson for lesson, _, _ in changes]
    from apps.scheduling.autoplan import is_monthly_lesson

    saved = [l for l in lessons if not l._state.adding]
    if saved and all(is_monthly_lesson(l) for l in saved):
        return validate_monthly(changes)
    policy, mode = snapshot_policy(lessons)
    unlocked = [l.id for l in lessons if not l._state.adding]
    weeks = {}
    for lesson, target, duration in changes:
        if not lesson._state.adding:
            weeks.setdefault(week_of(lesson.start_at), [])
        weeks.setdefault(week_of(target["start_at"]), []).append(
            (lesson, target, duration)
        )
    profiles = {}
    for week in sorted(weeks):
        landing = weeks[week]
        with operations_compile():
            data = current_dto(policy, week, mode, unlocked)
        keys = {u["demand_key"] for u in data["units"]}
        for lesson, _, _ in landing:
            if unit_key(lesson) not in keys:
                try:
                    data["units"].append(synthetic_unit(lesson, data))
                except DataNotReady as error:
                    raise DomainError(error.code, error.message) from error
        current = [
            u["locked_assignment"] for u in data["units"] if u["locked_assignment"]
        ]
        epoch = utc_epoch(data)
        moving = [
            target_assignment(lesson, target, epoch, duration)
            for lesson, target, duration in landing
        ]
        result = validate_assignments(data, [*current, *moving], require_coverage=False)
        if result["status"] != "PASSED":
            raise DomainError(
                "CALENDAR_VALIDATION_FAILED",
                "Assegnazioni incompatibili con disponibilità, domanda o vincoli correnti",
                violations=new_codes(data, current, result)
                or sorted({v["code"] for v in result["violations"]}),
                week_start=week.isoformat(),
            )
        tutors = {t["id"]: t for t in data["tutors"]}
        resources = {r["id"]: r for r in data["resources"]}
        for lesson, target, _ in landing:
            profiles[id(lesson)] = (tutors, resources)
    return profiles


def validate_monthly(changes):
    """Lezioni del pianificatore mensile (v0.9.11): stessi vincoli del motore mensile —
    apertura e chiusure, impegni di tutor e studenti, lezioni e aule occupate, tutor abilitato
    per la materia. Se serve un'aula (in presenza) sceglie una libera con posti sufficienti."""
    from apps.scheduling.autoplan import ROME
    from apps.scheduling.models import TutorSkill
    from apps.scheduling.slots import Finder, _hits

    ignore = [l.pk for l, _, _ in changes if not l._state.adding]
    tutors, resources, profiles = {}, {}, {}
    for lesson, target, duration in changes:
        start = target["start_at"]
        day = start.astimezone(ROME).date()
        students = [] if lesson._state.adding else [p.student_id for p in lesson.participants.all()]
        finder = Finder(students, [target["tutor_id"]], target["mode"], duration, day, day, ignore=ignore)
        res = finder.check(target["tutor_id"], start)
        codes = set(res["codes"])
        if str(target["tutor_id"]) != str(lesson.tutor_id) and not TutorSkill.objects.filter(
            tutor_id=target["tutor_id"], subject_id=lesson.subject_id, approved=True,
            valid_from__lte=day, valid_until__gte=day,
        ).exists():
            codes.add("TUTOR_SKILLS_MISSING")
        if target["mode"] == "IN_PERSON":
            mine = next((r for r in finder.rooms if str(r.id) == str(target["space_id"] or "")), None)
            end = start + timedelta(minutes=duration)
            if mine is not None and not _hits(finder.busy_r.get(str(mine.id), []), start, end) and (
                mine.student_capacity or 0
            ) >= len(students):
                codes.discard("NO_ROOM")
            elif res["space_id"]:
                target["space_id"] = str(res["space_id"])
            target["video_id"] = None
        else:
            target["space_id"] = None
        if codes:
            raise DomainError(
                "CALENDAR_VALIDATION_FAILED",
                "Modifica incompatibile con apertura, impegni, abilitazioni o lezioni già fissate",
                violations=sorted(codes),
            )
        tutors[str(target["tutor_id"])] = {"pause_minutes": 0}
        for rid in (target["space_id"], target["video_id"]):
            if rid:
                resources[str(rid)] = {"buffer_minutes": 0}
    for lesson, _, _ in changes:
        profiles[id(lesson)] = (tutors, resources)
    return profiles


def place(lesson, target, duration, profiles):
    tutors, resources = profiles[id(lesson)]
    lesson.start_at = target["start_at"]
    lesson.end_at = lesson.start_at + timedelta(minutes=duration)
    lesson.tutor_id = target["tutor_id"]
    lesson.mode = target["mode"]
    lesson.location = target["location"]
    lesson.space_id = target["space_id"]
    lesson.video_id = target["video_id"]
    lesson.tutor_occupied_until = lesson.end_at + timedelta(
        minutes=tutors[target["tutor_id"]]["pause_minutes"]
    )
    lesson.space_occupied_until = (
        lesson.end_at
        + timedelta(minutes=resources[target["space_id"]]["buffer_minutes"])
        if target["space_id"]
        else None
    )
    lesson.video_occupied_until = (
        lesson.end_at
        + timedelta(minutes=resources[target["video_id"]]["buffer_minutes"])
        if target["video_id"]
        else None
    )


def change_lessons(actor, changes, operation, reason, extra_after=None):
    """Valida e applica atomicamente [(lesson, changes_dict)]. Ritorna i summary."""
    plan = []
    for lesson, fields in changes:
        duration = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
        plan.append((lesson, target_of(lesson, fields), duration))
    profiles = validate_changes(plan)
    tutors = {lesson.tutor_id for lesson, _, _ in plan}
    befores = {lesson.id: full_summary(lesson) for lesson, _, _ in plan}
    for lesson, _, _ in plan:
        lesson.bookings.all().delete()
    from apps.scheduling.autoplan import is_monthly_lesson
    from apps.scheduling.autoplan_publish import ensure_anchor

    for lesson, target, duration in plan:
        place(lesson, target, duration, profiles)
        if not lesson._state.adding and is_monthly_lesson(lesson):
            ensure_anchor(lesson, actor)
        lesson.version += 1
        lesson.save()
        tutors.add(lesson.tutor_id)
    for lesson, _, _ in plan:
        save_bookings(lesson)
    cross_week_transitions(tutors)
    for lesson, _, _ in plan:
        assert_complete(lesson)
    force_constraints()
    out = []
    for lesson, _, _ in plan:
        after = full_summary(lesson)
        audit(
            actor,
            operation,
            reason,
            lesson=lesson,
            before=befores[lesson.id],
            after={**after, **(extra_after or {})},
        )
        event(
            "LESSON_" + operation,
            f"lesson:{lesson.id}:v{lesson.version}",
            {"lesson_id": str(lesson.id), "version": lesson.version},
        )
        notifications.lesson_changed(lesson, operation, befores[lesson.id])
        out.append(after)
    return out


def cancel_lesson(actor, lesson, reason, operation="CANCEL"):
    """Cancellazione senza ricevuta: per comandi composti (pratiche, serie)."""
    require_future_active(lesson)
    before = full_summary(lesson)
    lesson.bookings.all().delete()
    lesson.state = "CANCELLED"
    lesson.version += 1
    lesson.save()
    reopen_recovery(lesson, actor, reason)
    assert_complete(lesson)
    force_constraints()
    audit(actor, operation, reason, lesson=lesson, before=before, after=summary(lesson))
    event(
        "LESSON_CANCEL",
        f"lesson:{lesson.id}:v{lesson.version}",
        {"lesson_id": str(lesson.id), "version": lesson.version},
    )
    notifications.lesson_changed(lesson, "CANCEL")
    return summary(lesson)


def response(cmd, payload):
    bump_revision()
    return cmd.done(
        {
            **payload,
            "revision": cmd.revision.revision + 1,
            "experimental": True,
            "notifications_sent": False,
        }
    )


# --- GAP-E02: spostamento tra settimane, modifica, scambio ------------------------


@transaction.atomic
def move_lesson(actor, lesson_id, command, key):
    cmd = Command(actor, "calendar-move", key, {"lesson_id": str(lesson_id), **command})
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    require_future_active(lesson, command["expected_version"])
    reason = require_reason(command)
    (after,) = change_lessons(
        cmd.actor, [(lesson, {"start_at": command["start_at"]})], "MOVE", reason
    )
    return response(cmd, after)


@transaction.atomic
def modify_lesson(actor, lesson_id, command, key):
    cmd = Command(
        actor, "calendar-modify", key, {"lesson_id": str(lesson_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    require_future_active(lesson, command["expected_version"])
    reason = require_reason(command)
    changes = {k: v for k, v in command.get("changes", {}).items()}
    if not changes:
        raise DomainError("NO_CHANGES", "Indicare almeno un campo da modificare")
    current = {f: getattr(lesson, f) for f in FIELDS}
    proposed = {**current, **changes}
    for field in ("tutor_id", "space_id", "video_id"):
        current[field] = str(current[field]) if current[field] else None
        proposed[field] = str(proposed[field]) if proposed[field] else None
    if proposed == current:
        raise DomainError("NO_CHANGES", "Nessuna differenza rispetto alla lezione")
    (after,) = change_lessons(cmd.actor, [(lesson, changes)], "MODIFY", reason)
    return response(cmd, after)


@transaction.atomic
def swap_lessons(actor, command, key):
    first_id, second_id = command["first_id"], command["second_id"]
    cmd = Command(
        actor,
        "calendar-swap",
        key,
        {**command, "first_id": str(first_id), "second_id": str(second_id)},
    )
    if cmd.replay:
        return cmd.replay
    if str(first_id) == str(second_id):
        raise DomainError("SWAP_SAME_LESSON", "Indicare due lezioni distinte")
    first, second = lock_lessons([first_id, second_id])
    require_future_active(first, command["first_version"])
    require_future_active(second, command["second_version"])
    reason = require_reason(command)
    from apps.scheduling.autoplan import is_monthly_lesson

    if is_monthly_lesson(first) or is_monthly_lesson(second):
        rows = swap_monthly(cmd.actor, first, second, reason)
    else:
        rows = change_lessons(
            cmd.actor,
            [
                (first, {"start_at": second.start_at}),
                (second, {"start_at": first.start_at}),
            ],
            "SWAP",
            reason,
        )
    from .changes import supersede

    supersede(first)
    supersede(second)
    return response(cmd, {"lessons": rows})


def swap_monthly(actor, first, second, reason):
    """Scambio di lezioni del pianificatore mensile: ognuna prende il posto dell'altra e
    mantiene la propria durata. Vincoli del pianificatore mensile, ignorando le due lezioni
    scambiate (i loro vecchi orari si liberano)."""
    from apps.scheduling.autoplan import move_codes
    from .services import apply_times

    # La lezione che va al posto di quella che inizia prima ne prende l'inizio; l'altra
    # finisce dove finiva la seconda. Con durate diverse le lezioni attaccate restano
    # attaccate (15–16 + 16–17:30 → 15–16:30 + 16:30–17:30) e gli spazi intorno non cambiano.
    early, late = sorted((first, second), key=lambda l: (l.start_at, str(l.id)))
    early_len, late_len = early.end_at - early.start_at, late.end_at - late.start_at
    moves = [
        (late, early.start_at, late_len),
        (early, late.end_at - early_len, early_len),
    ]
    violations = set()
    for lesson, target, duration in moves:
        other = late if lesson is early else early
        violations.update(move_codes(lesson, target, duration=duration, ignore=[other.pk]))
    (a, a_start, a_len), (b, b_start, b_len) = moves
    if a_start < b_start + b_len and b_start < a_start + a_len:
        shared = (
            a.tutor_id == b.tutor_id
            or (a.space_id and a.space_id == b.space_id)
            or {p.student_id for p in a.participants.all()}
            & {p.student_id for p in b.participants.all()}
        )
        if shared:
            violations.add("RESOURCE_OVERLAP")
    if violations:
        raise DomainError(
            "CALENDAR_VALIDATION_FAILED",
            "Scambio incompatibile con apertura, impegni o lezioni già fissate",
            violations=sorted(violations),
        )
    befores = {lesson.id: full_summary(lesson) for lesson, _, _ in moves}
    for lesson, _, _ in moves:
        lesson.bookings.all().delete()
    for lesson, target, duration in moves:
        apply_times(lesson, target, duration)
        lesson.version += 1
        lesson.save()
    for lesson, _, _ in moves:
        save_bookings(lesson)
    cross_week_transitions({first.tutor_id, second.tutor_id})
    moves = [m for m in moves if m[0] is first] + [m for m in moves if m[0] is second]
    for lesson, _, _ in moves:
        assert_complete(lesson)
    force_constraints()
    out = []
    for lesson, _, _ in moves:
        after = full_summary(lesson)
        audit(actor, "SWAP", reason, lesson=lesson, before=befores[lesson.id], after=after)
        event(
            "LESSON_SWAP",
            f"lesson:{lesson.id}:v{lesson.version}",
            {"lesson_id": str(lesson.id), "version": lesson.version},
        )
        notifications.lesson_changed(lesson, "SWAP", befores[lesson.id])
        out.append(after)
    return out


# --- GAP-E03: RecoveryObligation e makeup -----------------------------------------


def obligation_summary(obligation):
    from . import recovery_policy

    origin = obligation.origin_lesson
    due = recovery_policy.due_by(origin.start_at) if origin else None
    makeup = (
        obligation.makeup_lessons.filter(state__in=OCCUPYING)
        .values_list("id", flat=True)
        .first()
    )
    return {
        "id": str(obligation.id),
        "canonical_key": obligation.canonical_key,
        "origin_lesson_id": str(obligation.origin_lesson_id),
        "demand_key": obligation.demand.demand_key,
        "participants": obligation.participants,
        "minutes_remaining": obligation.minutes_remaining,
        "cause": obligation.cause,
        "state": obligation.state,
        "version": obligation.version,
        "makeup_lesson_id": str(makeup) if makeup else None,
        "origin_start_at": origin.start_at.isoformat() if origin else None,
        "subject_id": str(origin.subject_id) if origin and origin.subject_id else None,
        "due_by": due.isoformat() if due else None,
        "recovery_periods": recovery_policy.recovery_periods(origin.start_at) if origin else [],
        "created_at": obligation.created_at.isoformat() if getattr(obligation, "created_at", None) else None,
    }


def ensure_obligation(actor, lesson, command, reason):
    """Identità canonica: un solo obbligo per lezione d'origine (T40)."""
    existing = (
        RecoveryObligation.objects.select_for_update()
        .filter(origin_lesson=lesson)
        .first()
    )
    if existing:
        return existing, False
    if lesson.recovery_id:
        raise DomainError(
            "RECOVERY_OF_RECOVERY",
            "Cancellare un recupero riapre il suo obbligo: nessun nuovo obbligo",
        )
    members = {str(p.student_id) for p in lesson.participants.all()}
    chosen = sorted({str(s) for s in command["participant_ids"]})
    if not chosen or not set(chosen) <= members:
        raise DomainError(
            "RECOVERY_PARTICIPANTS_INVALID",
            "Solo partecipanti approvati della lezione d'origine",
        )
    if lesson.state == "CANCELLED":
        if LessonOccurrence.objects.filter(
            demand=lesson.demand, state__in=OCCUPYING, recovery__isnull=True
        ).exists():
            raise DomainError(
                "DEMAND_ALREADY_REPLANNED",
                "L'unità è già coperta da un'altra lezione: nessun recupero duplicato",
            )
    elif lesson.state == "COMPLETED":
        absent = set(
            Attendance.objects.filter(
                lesson=lesson, status__in=("ABSENT", "JUSTIFIED")
            ).values_list("participant__student_id", flat=True)
        )
        if not set(chosen) <= {str(s) for s in absent}:
            raise DomainError(
                "RECOVERY_PARTICIPANTS_INVALID",
                "Per una lezione conclusa il recupero riguarda solo gli assenti registrati",
            )
    else:
        raise DomainError(
            "RECOVERY_ORIGIN_INVALID",
            "Recupero solo per lezioni cancellate o concluse con assenze",
        )
    duration = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
    minutes = command.get("minutes") or duration
    if minutes not in DURATION_CATALOG or minutes > duration:
        raise DomainError(
            "RECOVERY_MINUTES_INVALID",
            "Minuti del recupero nel catalogo durate e non superiori all'originale",
        )
    from . import recovery_policy

    policy = recovery_policy.check_entitlement(lesson, command)
    obligation = RecoveryObligation.objects.create(
        canonical_key=f"recovery:lesson:{lesson.id}",
        origin_lesson=lesson,
        demand=lesson.demand,
        participants=chosen,
        minutes_remaining=minutes,
        cause=command["cause"],
        reason=reason,
        created_by=actor,
    )
    audit(
        actor,
        "RECOVERY_CREATED",
        reason,
        lesson=lesson,
        obj=obligation,
        after={**obligation_summary(obligation), **policy},
    )
    event(
        "RECOVERY_CREATED",
        f"recovery:{obligation.id}:v1",
        {"recovery_id": str(obligation.id)},
    )
    notifications.recovery_changed(obligation, "recovery.created")
    return obligation, True


@transaction.atomic
def create_recovery(actor, lesson_id, command, key):
    cmd = Command(
        actor, "calendar-recovery", key, {"lesson_id": str(lesson_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    check_version(lesson, command["expected_version"])
    reason = require_reason(command)
    obligation, created = ensure_obligation(cmd.actor, lesson, command, reason)
    payload = {**obligation_summary(obligation), "created": created}
    if not created:
        return cmd.done({**payload, "experimental": True})
    return response(cmd, payload)


def lock_obligation(obligation_id, expected_version):
    obligation = (
        RecoveryObligation.objects.select_for_update(of=("self",))
        .select_related("origin_lesson__publication__plan__run__snapshot__policy")
        .select_related("demand__request")
        .filter(pk=obligation_id)
        .first()
    )
    if not obligation:
        raise DomainError("NOT_FOUND", "Obbligo di recupero inesistente")
    check_version(obligation, expected_version)
    return obligation


@transaction.atomic
def schedule_makeup(actor, obligation_id, command, key):
    cmd = Command(
        actor, "calendar-makeup", key, {"obligation_id": str(obligation_id), **command}
    )
    if cmd.replay:
        return cmd.replay
    obligation = lock_obligation(obligation_id, command["expected_version"])
    reason = require_reason(command)
    if obligation.state != "OPEN":
        raise DomainError(
            "RECOVERY_NOT_OPEN",
            f"Obbligo in stato {obligation.state}: non recuperabile",
        )
    from . import recovery_policy

    recovery_policy.check_due(obligation, command["start_at"])
    origin = obligation.origin_lesson
    lesson = LessonOccurrence(
        demand=obligation.demand,
        publication=origin.publication,
        subject_id=origin.subject_id,
        recovery=obligation,
        tutor_id=command["tutor_id"],
        mode=command["mode"],
        location=command["location"],
        space_id=command.get("space_id"),
        video_id=command.get("video_id"),
        start_at=command["start_at"],
        end_at=command["start_at"] + timedelta(minutes=obligation.minutes_remaining),
        tutor_occupied_until=command["start_at"],
        state="PUBLISHED",
    )
    from apps.scheduling.autoplan import ROME, is_monthly_lesson

    if is_monthly_lesson(origin):
        # Lezione del pianificatore mensile: stessi vincoli del motore mensile (aperture,
        # chiusure, impegni di tutor e di tutti gli studenti, lezioni e aule occupate).
        from apps.scheduling.slots import Finder, explain

        start = command["start_at"]
        if start <= now():
            raise DomainError("PAST_LESSON", "Il recupero deve essere nel futuro")
        day = start.astimezone(ROME).date()
        finder = Finder(
            obligation.participants, [command["tutor_id"]], command["mode"],
            obligation.minutes_remaining, day, day,
        )
        res = finder.check(command["tutor_id"], start)
        if res["codes"]:
            raise DomainError(
                "CALENDAR_VALIDATION_FAILED",
                "Orario non disponibile: " + "; ".join(explain(res["codes"])),
                violations=res["codes"],
            )
        if command["mode"] == "ONLINE":
            lesson.space_id = None
        elif not lesson.space_id:
            lesson.space_id = res["space_id"]
        lesson.tutor_occupied_until = lesson.end_at
        lesson.space_occupied_until = lesson.end_at if lesson.space_id else None
        lesson.video_occupied_until = lesson.end_at if lesson.video_id else None
    else:
        target = target_of(lesson, {})
        profiles = validate_changes([(lesson, target, obligation.minutes_remaining)])
        place(lesson, target, obligation.minutes_remaining, profiles)
    lesson.save()
    for student in obligation.participants:
        LessonParticipant.objects.create(lesson=lesson, student_id=student)
    save_bookings(lesson)
    cross_week_transitions([lesson.tutor_id])
    assert_complete(lesson)
    force_constraints()
    before = {"state": obligation.state, "version": obligation.version}
    obligation.state = "SCHEDULED"
    obligation.version += 1
    obligation.save()
    audit(
        cmd.actor,
        "MAKEUP",
        reason,
        lesson=lesson,
        obj=obligation,
        before=before,
        after={**full_summary(lesson), "recovery_state": obligation.state},
    )
    event(
        "LESSON_MAKEUP",
        f"lesson:{lesson.id}:v1",
        {"lesson_id": str(lesson.id), "recovery_id": str(obligation.id)},
    )
    notifications.makeup_scheduled(lesson, obligation)
    return response(
        cmd,
        {"lesson": full_summary(lesson), "recovery": obligation_summary(obligation)},
    )


@transaction.atomic
def waive_recovery(actor, obligation_id, command, key):
    cmd = Command(
        actor,
        "calendar-recovery-waive",
        key,
        {"obligation_id": str(obligation_id), **command},
    )
    if cmd.replay:
        return cmd.replay
    obligation = lock_obligation(obligation_id, command["expected_version"])
    reason = require_reason(command)
    if obligation.state != "OPEN":
        raise DomainError("RECOVERY_NOT_OPEN", "Solo un obbligo aperto è rinunciabile")
    before = obligation_summary(obligation)
    obligation.state = "WAIVED"
    obligation.version += 1
    obligation.save()
    audit(
        cmd.actor,
        "RECOVERY_WAIVED",
        reason,
        obj=obligation,
        before=before,
        after=obligation_summary(obligation),
    )
    notifications.recovery_changed(obligation, "recovery.waived")
    return response(cmd, obligation_summary(obligation))


# --- GAP-E04: presenze, COMPLETED, correzione amministrativa ----------------------


def authorize_attendance(actor):
    authorize_any(actor)


def can_record(actor, lesson):
    if is_center(actor):
        return True
    return getattr(
        settings, "CALENDAR_TUTOR_RECORDS_ATTENDANCE", False
    ) and is_lesson_tutor(actor, lesson)


def attendance_summary(lesson):
    rows = {
        str(a.participant.student_id): a
        for a in Attendance.objects.filter(lesson=lesson).select_related("participant")
    }
    entries = []
    counts = {"PRESENT": 0, "ABSENT": 0, "JUSTIFIED": 0, "NOT_RECORDED": 0}
    for p in lesson.participants.all().order_by("student_id"):
        a = rows.get(str(p.student_id))
        status = a.status if a else "NOT_RECORDED"
        counts[status] += 1
        entries.append(
            {
                "student_id": str(p.student_id),
                "status": status,
                "minutes": a.minutes if a else None,
                "version": a.version if a else 0,
                "recorded": bool(a),
            }
        )
    return {
        "lesson_id": str(lesson.id),
        "lesson_state": lesson.state,
        "lesson_version": lesson.version,
        "entries": entries,
        "counts": counts,
    }


def write_attendance(actor, lesson, entries, command_name, reason):
    participants = {str(p.student_id): p for p in lesson.participants.all()}
    seen = set()
    duration = int((lesson.end_at - lesson.start_at).total_seconds() // 60)
    for entry in entries:
        student = str(entry["student_id"])
        if student not in participants or student in seen:
            raise DomainError(
                "ATTENDANCE_PARTICIPANT_INVALID",
                "Ogni voce deve riferirsi una sola volta a un partecipante della lezione",
            )
        seen.add(student)
        minutes = entry.get("minutes")
        if minutes is not None and (
            entry["status"] != "PRESENT" or not 0 < minutes <= duration
        ):
            raise DomainError(
                "ATTENDANCE_MINUTES_INVALID",
                "Minuti effettivi solo per presenti ed entro la durata della lezione",
            )
    for entry in entries:
        participant = participants[str(entry["student_id"])]
        row = (
            Attendance.objects.select_for_update()
            .filter(participant=participant)
            .first()
        )
        if row is None:
            row = Attendance.objects.create(
                participant=participant,
                lesson=lesson,
                status=entry["status"],
                minutes=entry.get("minutes"),
                recorded_by=actor,
            )
        else:
            if (row.status, row.minutes) == (entry["status"], entry.get("minutes")):
                continue
            row.status = entry["status"]
            row.minutes = entry.get("minutes")
            row.recorded_by = actor
            row.version += 1
            row.save()
        AttendanceRevision.objects.create(
            attendance=row,
            sequence=row.revisions.count() + 1,
            status=row.status,
            minutes=row.minutes,
            command=command_name,
            reason=reason,
            actor=actor,
        )


@transaction.atomic
def record_attendance(actor, lesson_id, command, key):
    cmd = Command(
        actor,
        "calendar-attendance",
        key,
        {"lesson_id": str(lesson_id), **command},
        authorizer=authorize_attendance,
    )
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    if not can_record(cmd.actor, lesson):
        raise DomainError("FORBIDDEN", "Solo il centro o il tutor della lezione")
    check_version(lesson, command["expected_version"])
    if lesson.state != "PUBLISHED":
        raise DomainError(
            "ATTENDANCE_LOCKED",
            "Lezione non attiva o conclusa: usare la correzione amministrativa",
        )
    if lesson.start_at > now():
        raise DomainError("LESSON_NOT_STARTED", "Presenze solo da inizio lezione")
    before = attendance_summary(lesson)
    write_attendance(
        cmd.actor, lesson, command["entries"], "RECORD", command.get("reason", "")
    )
    after = attendance_summary(lesson)
    audit(
        cmd.actor,
        "ATTENDANCE",
        command.get("reason") or "Registrazione presenze",
        lesson=lesson,
        before=before["counts"],
        after=after["counts"],
    )
    return cmd.done({**after, "experimental": True})


@transaction.atomic
def complete_lesson(actor, lesson_id, command, key):
    cmd = Command(
        actor,
        "calendar-complete",
        key,
        {"lesson_id": str(lesson_id), **command},
        authorizer=authorize_attendance,
    )
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    if not can_record(cmd.actor, lesson):
        raise DomainError("FORBIDDEN", "Solo il centro o il tutor della lezione")
    check_version(lesson, command["expected_version"])
    if lesson.state != "PUBLISHED":
        raise DomainError("LESSON_NOT_ACTIVE", "Lezione non attiva")
    if lesson.end_at > now():
        raise DomainError("LESSON_NOT_ENDED", "Conclusione solo dopo la fine")
    recorded = Attendance.objects.filter(lesson=lesson).count()
    if recorded != lesson.participants.count():
        raise DomainError(
            "ATTENDANCE_INCOMPLETE",
            "Registrare la presenza (anche NOT_RECORDED) di ogni partecipante",
        )
    before = full_summary(lesson)
    lesson.state = "COMPLETED"
    lesson.completed_at = now()
    lesson.version += 1
    lesson.save()
    assert_complete(lesson)
    force_constraints()
    if lesson.recovery_id:
        obligation = RecoveryObligation.objects.select_for_update().get(
            pk=lesson.recovery_id
        )
        obligation.state = "FULFILLED"
        obligation.version += 1
        obligation.save()
        audit(
            cmd.actor,
            "RECOVERY_FULFILLED",
            "Recupero concluso",
            lesson=lesson,
            obj=obligation,
            after=obligation_summary(obligation),
        )
    reason = (command.get("reason") or "").strip() or "Lezione conclusa"
    audit(
        cmd.actor,
        "COMPLETE",
        reason,
        lesson=lesson,
        before=before,
        after={**summary(lesson), **attendance_summary(lesson)["counts"]},
    )
    event(
        "LESSON_COMPLETED",
        f"lesson:{lesson.id}:v{lesson.version}",
        {"lesson_id": str(lesson.id), "version": lesson.version},
    )
    notifications.lesson_completed(lesson)
    return response(cmd, {**summary(lesson), "attendance": attendance_summary(lesson)})


@transaction.atomic
def admin_correction(actor, lesson_id, command, key):
    """Correzione amministrativa auditata di una lezione conclusa (FR21, T30).

    Cambia solo le presenze; storia append-only in AttendanceRevision e CalendarAudit."""
    cmd = Command(
        actor,
        "calendar-admin-correction",
        key,
        {"lesson_id": str(lesson_id), **command},
    )
    if cmd.replay:
        return cmd.replay
    (lesson,) = lock_lessons([lesson_id])
    check_version(lesson, command["expected_version"])
    reason = require_reason(command)
    if command.get("confirm_correction") is not True:
        raise DomainError("CORRECTION_CONFIRMATION", "Conferma esplicita richiesta")
    if lesson.state != "COMPLETED":
        raise DomainError(
            "LESSON_NOT_COMPLETED",
            "Correzione amministrativa solo per lezioni concluse",
        )
    before = attendance_summary(lesson)
    write_attendance(cmd.actor, lesson, command["entries"], "ADMIN_CORRECTION", reason)
    after = attendance_summary(lesson)
    if before["entries"] == after["entries"]:
        raise DomainError("NO_CHANGES", "La correzione non modifica alcuna presenza")
    lesson.version += 1
    lesson.save(update_fields=["version", "updated_at"])
    audit(
        cmd.actor,
        "ADMIN_CORRECTION",
        reason,
        lesson=lesson,
        before={"entries": before["entries"]},
        after={"entries": after["entries"]},
    )
    event(
        "LESSON_CORRECTED",
        f"lesson:{lesson.id}:v{lesson.version}",
        {"lesson_id": str(lesson.id), "version": lesson.version},
    )
    notifications.attendance_corrected(lesson, lesson.version)
    return response(cmd, after)
