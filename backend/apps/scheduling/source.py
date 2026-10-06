"""Experimental DB compiler: one local week (contract 0.4) or, when the policy
opts in, up to six local weeks with the v0.5 features (contract 0.5)."""

from datetime import datetime, time, timedelta, timezone
import hashlib
from django.db.models import Q
from apps.education.models import TeachingRequest, Student, Tutor, Resource
from apps.education.path_services import (
    participant_ids,
    fingerprint,
    validate_blocks,
    DomainError,
)
from apps.availability.models import (
    AvailabilityRule,
    AvailabilityDeclaration,
    AvailabilityException,
    AvailabilityConflict,
)
from domain.intervals import expand_weekly, Interval, compile_effective, local_to_utc
from .models import (
    LessonSeries,
    TutorSkill,
    TutorOperatingPolicy,
    ResourceTiming,
    ServiceWindow,
    Closure,
)
from .contracts import parse_input, InputError, DEFAULT_LIMITS
from .policies import fairness_policy


class DataNotReady(ValueError):
    def __init__(self, code, message, ref=None):
        # ``ref``: id della richiesta che blocca, quando noto (v0.9.4).
        self.code, self.message, self.ref = code, message, ref
        super().__init__(message)


def level_id(level):
    return "level:" + hashlib.sha256(level.strip().encode()).hexdigest()[:32]


# v0.9.4: profili di ricerca. STANDARD usa il budget della policy (<= 30 s);
# THOROUGH è il calcolo "accurato" (es. notturno): budget lungo e più worker,
# stesso modello, stessi vincoli e stesso validatore indipendente.
EFFORTS = ("STANDARD", "THOROUGH")


def thorough_budget():
    from django.conf import settings

    return float(getattr(settings, "PLANNING_THOROUGH_BUDGET_SECONDS", 6 * 3600))


def thorough_workers():
    from django.conf import settings

    return int(getattr(settings, "PLANNING_THOROUGH_WORKERS", 8))


def wants_v05(policy, replanning=None, effort="STANDARD"):
    order = policy.objective_order or ["P0", "P1", "P2"]
    return bool(
        effort == "THOROUGH"
        or policy.horizon_weeks > 1
        or order != ["P0", "P1", "P2"]
        or policy.budget_seconds > 10
        or policy.student_buffer_minutes
        or policy.allow_cross_local_midnight
        or policy.recurring_stability != "NONE"
        or replanning
        or LessonSeries.objects.filter(active=True).exists()
        or TeachingRequest.objects.filter(
            status="APPROVED", tutor_choice="PREFERRED"
        ).exists()
    )


def compile_source(
    policy, week_start, mode, unlocked_ids=(), replanning=None, effort="STANDARD"
):
    """``replanning``: optional {"authorizations": {lesson_id: authorization_id},
    "propose_scope_expansion": bool} for an authorised local replan (GAP-D05)."""
    if week_start.weekday() != 0:
        raise DataNotReady(
            "MONDAY_REQUIRED", "L’orizzonte deve iniziare di lunedì locale"
        )
    if not policy.approved_for_exploration:
        raise DataNotReady(
            "POLICY_NOT_APPROVED",
            "La policy deve essere esplicitamente approvata per l’esplorazione, non per produzione",
        )
    if policy.unsupported_constraints:
        raise DataNotReady(
            "UNSUPPORTED_CONSTRAINT",
            "Policy con vincoli non implementati: nessun rilassamento",
        )
    if effort not in EFFORTS:
        raise DataNotReady("EFFORT_UNKNOWN", "Profilo di calcolo sconosciuto")
    v05 = wants_v05(policy, replanning, effort)
    weeks = policy.horizon_weeks if v05 else 1
    week_starts = [week_start + timedelta(days=7 * w) for w in range(weeks)]
    week_end = week_start + timedelta(days=7 * weeks)
    epoch = local_to_utc(datetime.combine(week_start, time.min))
    end_utc = local_to_utc(datetime.combine(week_end, time.min))
    span = int((end_utc - epoch).total_seconds() / 60)

    def number(moment):
        if moment.second or moment.microsecond:
            raise DataNotReady(
                "MINUTE_PRECISION",
                "Precisione al minuto richiesta, senza arrotondamenti impliciti",
            )
        return int((moment.astimezone(timezone.utc) - epoch).total_seconds() / 60)

    def clip(first, last):
        first = max(first, epoch)
        last = min(last, end_utc)
        return {"start": number(first), "end": number(last)} if first < last else None

    def recurring(row):
        try:
            return expand_weekly(
                row.weekday,
                row.start_time,
                row.end_time,
                row.period_start,
                row.period_end,
                week_start,
                week_end,
                getattr(row, "timezone", "Europe/Rome"),
            )
        except (ValueError, KeyError) as error:
            raise DataNotReady(
                "INVALID_LOCAL_TIME",
                "Ora locale inesistente, ambigua o regola non valida",
            ) from error

    general = list(
        ServiceWindow.objects.order_by("id").filter(
            resource__isnull=True, period_start__lt=week_end, period_end__gte=week_start
        )
    )
    service = []
    for row in general:
        for interval in recurring(row):
            service.append(
                {
                    "mode": row.mode,
                    "location": row.location,
                    **clip(interval.start, interval.end),
                }
            )
    if not service:
        raise DataNotReady(
            "SERVICE_WINDOWS_MISSING", "Definire aperture di servizio nell’orizzonte"
        )
    requests = list(
        TeachingRequest.objects.order_by("id")
        .filter(
            period_start__lt=week_end, period_end__gte=week_start, status="APPROVED"
        )
        .select_related("student", "group", "curriculum_block__path", "subject")
        .prefetch_related("participants", "preferred_tutors")
    )
    if not requests:
        raise DataNotReady("DEMAND_MISSING", "Nessuna richiesta didattica nel periodo")
    max_units = DEFAULT_LIMITS["0.5" if v05 else "0.4"]["max_units"]
    if sum(req.sessions_per_week for req in requests) * weeks > max_units:
        raise DataNotReady(
            "DEMAND_LIMIT",
            f"Il bridge ammette massimo {max_units} unità: nessuna domanda viene troncata",
        )
    seen_paths = set()
    for request in requests:
        if (
            request.curriculum_block_id
            and request.curriculum_block.path_id not in seen_paths
        ):
            try:
                validate_blocks(request.curriculum_block.path, require_complete=True)
            except DomainError as error:
                raise DataNotReady(
                    "CURRICULUM_NOT_READY",
                    "Il programma dichiarato non è completo o presenta conflitti",
                ) from error
            seen_paths.add(request.curriculum_block.path_id)
    unit_specs = []
    student_ids = set()
    levels = set()
    request_levels = {}
    for req in requests:
        if not req.mode:
            raise DataNotReady(
                "REQUEST_MODE_MISSING",
                "La modalità delle richieste legacy deve essere esplicita",
                str(req.id),
            )
        if req.curriculum_block_id:
            block = req.curriculum_block
            ids = participant_ids(block)
            stored = set(req.participants.values_list("student_id", flat=True))
            if stored != set(ids) or req.source_fingerprint != fingerprint(block, ids):
                raise DataNotReady(
                    "CURRICULUM_CHANGED",
                    "Curriculum o partecipanti derivati alterati: revisione esplicita necessaria",
                )
            attrs = {
                "duration_minutes": block.duration_minutes,
                "sessions_per_week": block.sessions_per_week,
                "mode": block.mode,
                "priority": block.priority,
                "mandatory": block.mandatory,
                "period_start": block.period_start,
                "period_end": block.period_end,
                "subject_id": block.subject_id,
                "student_id": block.student_id,
                "group_id": block.group_id,
            }
            if any(getattr(req, k) != v for k, v in attrs.items()):
                raise DataNotReady(
                    "DERIVED_REQUEST_CHANGED",
                    "Richiesta derivata incoerente con il curriculum",
                )
            level = block.path.level
        else:
            if req.group_id:
                raise DataNotReady(
                    "LEGACY_GROUP_UNSUPPORTED",
                    "Gruppi senza curriculum canonico non supportati dal bridge",
                )
            ids = [req.student_id]
            level = req.student.level
        if not level.strip():
            raise DataNotReady(
                "LEVEL_MISSING",
                "Dichiarare il livello didattico, senza dedurlo dal nome o dall’età",
                str(req.id),
            )
        levels.add(level)
        request_levels[req.id] = level
        for wk in week_starts:
            wk_end = wk + timedelta(days=7)
            if req.period_start >= wk_end or req.period_end < wk:
                continue  # request not active in this week of a longer horizon
            # Lezioni singole e ricorrenti hanno finestre volutamente parziali
            # (un giorno, la prima e l'ultima settimana): la policy delle
            # settimane parziali vale solo per la domanda settimanale storica.
            if req.kind == "WEEKLY" and policy.partial_week_rule == "BLOCK" and (
                req.period_start > wk or req.period_end < wk_end - timedelta(days=1)
            ):
                raise DataNotReady(
                    "PARTIAL_WEEK",
                    "Settimana parziale: la policy corrente ne blocca l’espansione",
                    str(req.id),
                )
            first = max(wk, req.period_start)
            after = min(wk_end, req.period_end + timedelta(days=1))
            earliest = number(local_to_utc(datetime.combine(first, time.min)))
            latest = number(local_to_utc(datetime.combine(after, time.min)))
            sessions = req.sessions_per_week
            if req.kind == "SINGLE":
                sessions = 1
                if req.fixed_time is not None:
                    # Lezione piazzata dal centro: finestra pari alla durata.
                    begin = local_to_utc(datetime.combine(req.period_start, req.fixed_time))
                    earliest = number(begin)
                    latest = number(begin + timedelta(minutes=req.duration_minutes))
            for serial in range(1, sessions + 1):
                key = f"req:{req.id}/week:{wk}/{serial}"
                unit_specs.append(
                    (
                        req,
                        serial,
                        {
                            "demand_key": key,
                            "type": "GROUP" if req.group_id else "INDIVIDUAL",
                            "subject": str(req.subject_id),
                            "level": level_id(level),
                            "participants": [str(i) for i in ids],
                            "duration_minutes": req.duration_minutes,
                            "priority": req.priority,
                            "mandatory": req.mandatory,
                            "allowed_modes": [req.mode],
                            "allowed_tutors": [],
                            "online_capacity": req.group.online_capacity
                            if req.group_id
                            else None,
                            "earliest_start": earliest,
                            "latest_end": latest,
                            "locked_assignment": None,
                        },
                        wk,
                    )
                )
        student_ids.update(ids)
    active_students = list(Student.objects.filter(id__in=student_ids, active=True))
    if len(active_students) != len(student_ids):
        raise DataNotReady("STUDENT_INACTIVE", "Uno studente richiesto non è attivo")
    skills = list(
        TutorSkill.objects.order_by("id")
        .filter(
            approved=True,
            level__in=levels,
            valid_from__lt=week_end,
            valid_until__gte=week_start,
            tutor__active=True,
        )
        # P1/T2: un tutor senza account (invito non ancora accettato) resta pianificabile;
        # un account disattivato no.
        .filter(Q(tutor__account__isnull=True) | Q(tutor__account__is_active=True))
        .select_related("tutor")
    )
    required_pairs = {
        (str(req.subject_id), request_levels[req.id], req.mode) for req in requests
    }
    skills = [
        skill
        for skill in skills
        if (str(skill.subject_id), skill.level, skill.mode) in required_pairs
    ]
    tutor_ids = {skill.tutor_id for skill in skills}
    if not tutor_ids:
        raise DataNotReady(
            "TUTOR_SKILLS_MISSING", "Nessuna competenza approvata pertinente"
        )
    if len(tutor_ids) > 10:
        raise DataNotReady(
            "TUTOR_LIMIT", "Il bridge sperimentale ammette massimo 10 tutor pertinenti"
        )
    work = {
        row.tutor_id: row
        for row in TutorOperatingPolicy.objects.filter(tutor_id__in=tutor_ids)
    }
    if set(work) != tutor_ids:
        raise DataNotReady(
            "TUTOR_LIMITS_MISSING",
            "Dichiarare limiti, pause e transizioni per ogni tutor pertinente",
        )

    def availability(subject, kind):
        lookup = {kind: subject}
        declaration = AvailabilityDeclaration.objects.filter(**lookup).first()
        if not declaration or declaration.state == "UNKNOWN":
            raise DataNotReady(
                "MISSING_AVAILABILITY",
                "Disponibilità incompleta: dichiarazione esplicita necessaria",
            )
        if AvailabilityConflict.objects.filter(**lookup, open=True).exists():
            raise DataNotReady(
                "AVAILABILITY_CONFLICT",
                "Conflitto tra dichiarazioni ancora da risolvere",
            )
        rules = list(
            AvailabilityRule.objects.filter(
                **lookup, period_start__lt=week_end, period_end__gte=week_start
            ).exclude(status="REVOKED")
        )
        if any(row.status == "DRAFT" for row in rules):
            raise DataNotReady(
                "AVAILABILITY_PENDING",
                "Disponibilità nel periodo ancora da approvare o revocare",
            )
        exceptions = list(
            AvailabilityException.objects.filter(
                **lookup, start_at__lt=end_utc, end_at__gt=epoch
            )
        )
        if declaration.state == "DECLARED_NONE":
            if rules or any(e.kind == "ADD_AVAILABLE" for e in exceptions):
                raise DataNotReady(
                    "CONTRADICTORY_AVAILABILITY",
                    "Nessuna disponibilità dichiarata ma finestre attive presenti",
                )
            return declaration.state, []
        windows = []
        for mode_name in ("IN_PERSON", "ONLINE"):
            for location in ("ON_SITE", "REMOTE"):
                if (
                    kind == "student"
                    and not v05
                    and mode_name == "ONLINE"
                    and any(
                        r.mode == mode_name and r.location == "ON_SITE"
                        for r in [*rules, *exceptions]
                    )
                ):
                    raise DataNotReady(
                        "STUDENT_ONLINE_ONSITE_UNSUPPORTED",
                        "Studenti online in sede richiedono regole di occupazione ancora non implementate",
                    )
                recurring_intervals = [
                    i
                    for row in rules
                    if row.mode == mode_name and row.location == location
                    for i in recurring(row)
                ]
                added = []
                removed = []
                for exception in exceptions:
                    if exception.mode == mode_name and exception.location == location:
                        c = clip(exception.start_at, exception.end_at)
                        if c:
                            (
                                added if exception.kind == "ADD_AVAILABLE" else removed
                            ).append(
                                Interval(
                                    epoch + timedelta(minutes=c["start"]),
                                    epoch + timedelta(minutes=c["end"]),
                                )
                            )
                effective = compile_effective(
                    recurring_intervals, added, removed, "APPROVED"
                )
                for interval in effective:
                    clipped = clip(interval.start, interval.end)
                    if clipped:
                        windows.append(
                            {
                                "mode": mode_name,
                                **(
                                    {"location": location}
                                    if kind == "tutor"
                                    or (v05 and mode_name == "ONLINE")
                                    else {}
                                ),
                                **clipped,
                            }
                        )
        return declaration.state, windows

    students = []
    for student in active_students:
        state, windows = availability(student, "student")
        students.append(
            {
                "id": str(student.id),
                "availability_state": state,
                "availability": windows,
            }
        )
    tutors = []
    for tutor in Tutor.objects.filter(id__in=tutor_ids).order_by("id"):
        state, windows = availability(tutor, "tutor")
        profile = work[tutor.id]
        compiled_skills = []
        for skill in skills:
            if skill.tutor_id != tutor.id:
                continue
            c = clip(
                local_to_utc(datetime.combine(skill.valid_from, time.min)),
                local_to_utc(
                    datetime.combine(skill.valid_until + timedelta(days=1), time.min)
                ),
            )
            if c:
                compiled_skills.append(
                    {
                        "subject": str(skill.subject_id),
                        "level": level_id(skill.level),
                        "mode": skill.mode,
                        **c,
                    }
                )
        tutors.append(
            {
                "id": str(tutor.id),
                "availability_state": state,
                "availability": windows,
                "skills": compiled_skills,
                "daily_limit_minutes": profile.daily_limit_minutes,
                "weekly_limit_minutes": profile.weekly_limit_minutes,
                "pause_minutes": profile.pause_minutes,
                "transition_minutes": {
                    "ON_SITE": {"ON_SITE": 0, "REMOTE": profile.site_to_remote_minutes},
                    "REMOTE": {"ON_SITE": profile.remote_to_site_minutes, "REMOTE": 0},
                },
            }
        )
    for req, serial, unit, _ in unit_specs:
        matching = {
            str(s.tutor_id)
            for s in skills
            if s.subject_id == req.subject_id
            and s.level == request_levels[req.id]
            and s.mode == req.mode
        }
        if not matching:
            raise DataNotReady(
                "REQUEST_SKILLS_MISSING",
                "Una richiesta non ha competenze pertinenti approvate",
                str(req.id),
            )
        chosen = {str(t.id) for t in req.preferred_tutors.all()}
        if req.tutor_choice == "REQUIRED":
            # Vincolo duro: solo il tutor richiesto (se competente), mai rilassato.
            if not chosen & matching:
                raise DataNotReady(
                    "REQUIRED_TUTOR_UNAVAILABLE",
                    "Il tutor richiesto obbligatoriamente non ha la competenza approvata per la materia",
                    str(req.id),
                )
            matching = chosen & matching
        elif req.tutor_choice == "PREFERRED" and chosen & matching:
            # Preferenza morbida: termine P dell'obiettivo (dopo copertura ed equità).
            unit["preferred_tutors"] = sorted(chosen & matching)
        unit["allowed_tutors"] = sorted(matching)
    resources = []
    active_resources = list(Resource.objects.filter(active=True).order_by("id"))
    for resource in active_resources:
        timing = ResourceTiming.objects.filter(resource=resource).first()
        if not timing:
            raise DataNotReady(
                "RESOURCE_POLICY_MISSING",
                "Dichiarare buffer e modalità delle aperture per ogni risorsa attiva",
            )
        rows = list(
            ServiceWindow.objects.order_by("id").filter(
                resource=resource, period_start__lt=week_end, period_end__gte=week_start
            )
        )
        availability_windows = [
            clip(i.start, i.end) for row in rows for i in recurring(row)
        ]
        if not rows and timing.inherit_service_windows:
            applicable = [
                w
                for w in service
                if (resource.kind == "SPACE" and w["location"] == "ON_SITE")
                or (resource.kind == "VIDEO_CHANNEL" and w["mode"] == "ONLINE")
            ]
            availability_windows = [
                {"start": w["start"], "end": w["end"]} for w in applicable
            ]
        if not rows and not timing.inherit_service_windows:
            raise DataNotReady(
                "RESOURCE_WINDOWS_MISSING",
                "Aperture specifiche della risorsa mancanti, senza ereditarietà autorizzata",
            )
        resources.append(
            {
                "id": str(resource.id),
                "kind": resource.kind,
                "student_capacity": resource.student_capacity,
                "buffer_minutes": timing.buffer_minutes,
                "availability": availability_windows,
            }
        )
    closures = []
    resource_ids = {resource.id for resource in active_resources}
    for closure in Closure.objects.order_by("id").filter(
        start_at__lt=end_utc, end_at__gt=epoch
    ):
        if closure.resource_id and closure.resource_id not in resource_ids:
            continue
        closures.append(
            {
                "mode": closure.mode,
                "resource_id": str(closure.resource_id)
                if closure.resource_id
                else None,
                **clip(closure.start_at, closure.end_at),
            }
        )
    dto = {
        "schema_version": "0.5" if v05 else "0.4",
        "policy_version": f"policy:{policy.id}/v{policy.version}",
        "epoch": epoch.isoformat(),
        "timezone": "Europe/Rome",
        "horizon_days": 7 * weeks,
        "horizon_minutes": span,
        "grid_minutes": 15,
        "duration_catalog": [60, 90, 120],
        "mode": mode,
        "budget_seconds": thorough_budget()
        if effort == "THOROUGH"
        else policy.budget_seconds,
        "online_onsite_requires_space": policy.online_onsite_requires_space,
        "video_channels_required": policy.video_channels_required,
        "allow_cross_local_midnight": policy.allow_cross_local_midnight,
        "student_buffer_minutes": policy.student_buffer_minutes,
        "objective_order": list(policy.objective_order or ["P0", "P1", "P2"]),
        "unsupported_constraints": policy.unsupported_constraints,
        "students": sorted(students, key=lambda row: row["id"]),
        "tutors": tutors,
        "resources": resources,
        "service_windows": service,
        "closures": closures,
        "units": [spec[2] for spec in unit_specs],
    }
    if v05:
        if "F" in dto["objective_order"]:
            try:
                dto["fairness_policy"] = fairness_policy(
                    policy.fairness_policy_id, policy.fairness_policy_version
                )
            except ValueError as error:
                raise DataNotReady("FAIRNESS_POLICY_UNKNOWN", str(error)) from error
        dto["series"] = compile_series(policy, unit_specs, weeks)
        if (
            any(spec[2].get("preferred_tutors") for spec in unit_specs)
            and "P" not in dto["objective_order"]
        ):
            # Il tutor preferito è un termine P: se la policy non lo ordina,
            # lo si aggiunge per ultimo (non peggiora mai copertura ed equità).
            dto["objective_order"].append("P")
        if effort == "THOROUGH":
            dto["search_workers"] = thorough_workers()
    from apps.calendar.context import attach_calendar, active_week, assignment

    unlocked = set(map(str, unlocked_ids))
    if replanning:
        unlocked |= {str(k) for k in replanning["authorizations"]}
    try:
        parse_input(dto)
    except InputError as error:
        raise DataNotReady(error.code, error.message) from error
    for wk in week_starts:
        dto = attach_calendar(dto, wk, policy, unlocked)
    if replanning:
        units = {u["demand_key"]: u for u in dto["units"]}
        granted = []
        for wk in week_starts:
            for lesson in active_week(wk):
                auth = replanning["authorizations"].get(str(lesson.id))
                unit = units.get(lesson.demand.demand_key)
                if auth and unit:
                    unit["previous_assignment"] = assignment(lesson, epoch)
                    granted.append(
                        {"demand_key": unit["demand_key"], "authorization_id": auth}
                    )
        if len(granted) != len(replanning["authorizations"]):
            raise DataNotReady(
                "UNLOCK_NOT_IN_HORIZON",
                "Ogni lezione da sbloccare deve essere pubblicata nell’orizzonte",
            )
        dto["replanning"] = {
            "scope": "LOCAL",
            "unlocked": granted,
            "expansion_candidates": sorted(
                u["demand_key"] for u in dto["units"] if u["locked_assignment"]
            ),
            "propose_scope_expansion": bool(replanning["propose_scope_expansion"]),
        }
    try:
        dto = parse_input(dto)
    except InputError as error:
        raise DataNotReady(error.code, error.message) from error
    return dto, unit_specs


def compile_series(policy, unit_specs, weeks):
    """Series per (request, serial) across weeks; LessonSeries gives the slot."""
    declared = {
        (row.request_id, row.serial): row
        for row in LessonSeries.objects.filter(
            active=True, request_id__in={spec[0].id for spec in unit_specs}
        )
    }
    grouped = {}
    for req, serial, unit, _ in unit_specs:
        grouped.setdefault((req.id, serial), []).append(unit["demand_key"])
    result = []
    for (request_id, serial), keys in sorted(grouped.items(), key=lambda i: str(i[0])):
        row = declared.get((request_id, serial))
        if row:
            minute = row.local_start_time.hour * 60 + row.local_start_time.minute
            result.append(
                {
                    "series_key": f"series:{request_id}/{serial}",
                    "units": keys,
                    "stability": row.stability,
                    "preferred_slot": {
                        "weekday": row.weekday,
                        "local_start_minute": minute,
                        "source": "LESSON_SERIES"
                        if row.source == "DECLARED"
                        else "PREVIOUS_PLAN",
                    },
                }
            )
        elif policy.recurring_stability == "PREFERRED" and weeks > 1:
            result.append(
                {
                    "series_key": f"series:{request_id}/{serial}",
                    "units": keys,
                    "stability": "PREFERRED",
                    "preferred_slot": None,
                }
            )
    return result
