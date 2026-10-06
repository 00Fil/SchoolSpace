"""Pianificatore mensile semplificato (v0.9.7).

Input, in ordine di rigidità:
1. orari di apertura del centro (``OpeningHours``) e chiusure (``Closure``: ferie,
   pause dell'anno scolastico, chiusure straordinarie) — **sempre rispettati**;
2. impegni di studenti (inseriti dai genitori) e tutor (``Commitment``) — rispettati,
   ma una lezione può sforare un impegno **fino a TOLERANCE minuti** (default 30):
   in quel caso la proposta resta valida e si chiede conferma all'interessato;
3. lezioni già pubblicate o in attesa di conferma, che occupano tutor, studenti e aule.

Domanda: richieste didattiche APPROVATE con periodo nel mese (singole, ricorrenti,
settimanali). Il motore (CP-SAT) sceglie giorno, ora e tutor (uno per richiesta nel
mese: quello scelto dal centro o uno con competenza approvata) e ottimizza, in ordine:
copertura (priorità) ≫ minuti di sforamento ≫ regolarità settimanale ≫ buchi nelle
giornate di tutor e studenti.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from math import ceil
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

ROME = ZoneInfo("Europe/Rome")
STEP = 30  # passo dei possibili orari di inizio (più gli allineamenti agli impegni)
PRIORITY_WEIGHT = {"P0": 3, "P1": 2, "P2": 1}
W_MISS = 100_000
W_OVER = 100  # per minuto di sforamento
W_PATTERN = 400  # lezione fuori dallo schema settimanale della richiesta
W_GAP_TUTOR = 10  # per minuto di buco nella giornata del tutor
W_GAP_STUDENT = 4
W_PREFERRED = 300

REASONS = {
    "NO_TUTOR": "Nessun tutor con la competenza approvata per materia e modalità.",
    "TUTOR_MISSING": "Serie senza tutor: sceglilo nella richiesta.",
    "NO_ROOMS": "Nessuna aula attiva per le lezioni in presenza.",
    "CLOSED": "Il centro è chiuso nei giorni richiesti (orari di apertura o chiusure).",
    "FIXED_TIME": "L’orario fisso è fuori dagli orari del centro o in conflitto.",
    "STUDENT_BUSY": "Gli impegni dello studente coprono tutte le fasce utili (sforamento oltre la tolleranza).",
    "TUTOR_BUSY": "Gli impegni del tutor coprono tutte le fasce utili (sforamento oltre la tolleranza).",
    "BUSY": "Tutor o studente hanno già lezioni in tutte le fasce utili.",
    "FULL": "Le fasce compatibili sono già prese da altre lezioni o non ci sono aule libere.",
    "PAST": "Il periodo richiesto è già passato.",
    "REMOVED": "Lezione tolta durante la verifica: aggiungila in un altro orario o conferma senza.",
}


def tolerance():
    return int(getattr(settings, "AUTOPLAN_TOLERANCE_MINUTES", 30))


def month_start(value):
    return date(value.year, value.month, 1)


def month_end(first):
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def minutes(t):
    return t.hour * 60 + t.minute + (1 if (t.hour, t.minute) == (23, 59) else 0)


def at(day, minute):
    """Datetime aware Europe/Rome per giorno e minuto locale."""
    return datetime.combine(day, time(0), tzinfo=ROME) + timedelta(minutes=minute)


def local_span(start_at, end_at, day):
    """Intervallo in minuti locali del giorno ``day`` coperto da [start_at, end_at)."""
    a = max(start_at.astimezone(ROME), at(day, 0))
    b = min(end_at.astimezone(ROME), at(day, 1440))
    if b <= a:
        return None
    base = at(day, 0)
    return int((a - base).total_seconds() // 60), int(ceil((b - base).total_seconds() / 60))


def days_between(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def overlap(a, b, spans):
    """Minuti di [a, b) coperti dall'unione di ``spans``."""
    cuts = sorted((max(a, s), min(b, e)) for s, e, *_ in spans if s < b and e > a)
    total, cur_s, cur_e = 0, None, None
    for s, e in cuts:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


# --- lettura dei dati -------------------------------------------------------------


def opening_hours():
    from .models import OpeningHours

    out = defaultdict(list)
    for row in OpeningHours.objects.all():
        out[row.weekday].append((minutes(row.start_time), minutes(row.end_time)))
    for wd in out:
        out[wd].sort()
    return out


def closures(first, last):
    """{giorno: {"ALL"|"IN_PERSON"|"ONLINE": [(a, b, motivo)]}} solo chiusure generali."""
    from .models import Closure

    lo, hi = at(first, 0), at(last, 1440)
    out = defaultdict(lambda: defaultdict(list))
    for c in Closure.objects.filter(start_at__lt=hi, end_at__gt=lo, resource__isnull=True):
        for day in days_between(
            max(first, c.start_at.astimezone(ROME).date()),
            min(last, c.end_at.astimezone(ROME).date()),
        ):
            span = local_span(c.start_at, c.end_at, day)
            if span:
                out[day][c.mode].append((*span, c.reason))
    return out


def commitments(first, last, students=(), tutors=()):
    """{("S"|"T", id): {giorno: [(a, b, etichetta)]}}."""
    from .models import Commitment

    out = defaultdict(lambda: defaultdict(list))
    rows = Commitment.objects.filter(
        Q(student_id__in=list(students)) | Q(tutor_id__in=list(tutors))
    )
    for c in rows:
        key = ("S", c.student_id) if c.student_id else ("T", c.tutor_id)
        a, b = minutes(c.start_time), minutes(c.end_time)
        if c.kind == "ONE_OFF":
            if first <= c.date <= last:
                out[key][c.date].append((a, b, c.label))
            continue
        lo = max(first, c.valid_from or first)
        hi = min(last, c.valid_until or last)
        for day in days_between(lo, hi) if lo <= hi else []:
            if day.weekday() == c.weekday:
                out[key][day].append((a, b, c.label))
    return out


def occupied(first, last, exclude_plan=None):
    """Lezioni che occupano tutor, studenti e aule: pubblicate + in attesa di conferma."""
    from apps.calendar.models import LessonOccurrence

    lo, hi = at(first - timedelta(days=7), 0), at(last + timedelta(days=7), 1440)
    tutor, student, room = defaultdict(list), defaultdict(list), defaultdict(list)
    per_request = defaultdict(list)  # request_id -> [data locale]
    lessons = (
        LessonOccurrence.objects.filter(
            state__in=("PUBLISHED", "COMPLETED"), start_at__lt=hi, end_at__gt=lo
        )
        .select_related("demand")
        .prefetch_related("participants")
    )
    for l in lessons:
        tutor[l.tutor_id].append((l.start_at, l.tutor_occupied_until))
        for p in l.participants.all():
            student[p.student_id].append((l.start_at, l.end_at))
        if l.space_id:
            room[l.space_id].append((l.start_at, l.space_occupied_until or l.end_at))
        per_request[l.demand.request_id].append(l.start_at.astimezone(ROME).date())
    waiting = reserved_lessons().filter(start_at__lt=hi, end_at__gt=lo)
    if exclude_plan is not None:
        plans = exclude_plan if isinstance(exclude_plan, (list, tuple)) else [exclude_plan]
        waiting = waiting.exclude(plan__in=plans)
    for l in waiting:
        tutor[l.tutor_id].append((l.start_at, l.end_at))
        for sid in l.participants:
            student[sid].append((l.start_at, l.end_at))
        if l.space_id:
            room[l.space_id].append((l.start_at, l.end_at))
        per_request[l.request_id].append(l.start_at.astimezone(ROME).date())
    # v0.9.11: i nuovi orari delle rettifiche in bozza sono già prenotati
    from .corrections import pending_targets

    for t_id, sids, a, b in pending_targets(lo, hi):
        tutor[t_id].append((a, b))
        for sid in sids:
            student[sid].append((a, b))
    return tutor, student, room, per_request


def reserved_lessons():
    """Lezioni del motore che occupano già lo slot: in attesa di conferma, oppure proposte
    in una bozza di richiesta che il centro sta verificando (v0.9.9)."""
    from .models import AutoPlanLesson

    return AutoPlanLesson.objects.filter(
        Q(state="AWAITING")
        | Q(state="PROPOSED", plan__state="DRAFT", plan__request__isnull=False)
    )


def ever_planned(request_ids):
    from apps.calendar.models import LessonOccurrence
    from .models import AutoPlanLesson

    done = set(
        LessonOccurrence.objects.filter(
            demand__request_id__in=request_ids,
            state__in=("PUBLISHED", "COMPLETED"),
        ).values_list("demand__request_id", flat=True)
    )
    done |= set(
        AutoPlanLesson.objects.filter(
            request_id__in=request_ids, state__in=("AWAITING", "PUBLISHED")
        ).values_list("request_id", flat=True)
    )
    return done


def participants_of(req, first, last):
    # v0.9.9: lezione di gruppo del centro (elenco esplicito dei partecipanti)
    if not req.curriculum_block_id and req.group_label:
        ids = sorted({p.student_id for p in req.participants.all()}, key=str)
        if ids:
            return ids
    if req.student_id:
        return [req.student_id]
    if not req.group_id:
        return []
    return sorted(
        m.student_id
        for m in req.group.memberships.all()
        if m.period_start <= last and m.period_end >= first
    )


def competent_tutors(req, first, last):
    from apps.education.models import Tutor
    from .models import TutorSkill

    skills = TutorSkill.objects.filter(
        subject_id=req.subject_id,
        approved=True,
        valid_from__lte=last,
        valid_until__gte=first,
        tutor__active=True,
    )
    if req.mode:
        skills = skills.filter(mode=req.mode)
    ids = set(skills.values_list("tutor_id", flat=True))
    return list(Tutor.objects.filter(pk__in=ids, active=True).order_by("display_name"))


# --- domanda -----------------------------------------------------------------------


@dataclass
class Demand:
    req: object
    participants: list
    tutors: list  # id tutor ammessi
    preferred: set
    mode: str
    weeks: dict = field(default_factory=dict)  # lunedì -> (giorni ammessi, quante)
    reason: str = ""

    @property
    def needed(self):
        return sum(n for _, n in self.weeks.values())


def week_needs(req, first, last, start, existing_dates):
    """Lezioni da collocare per settimana (lunedì -> (giorni del mese, quante))."""
    out = {}
    per_week = req.sessions_per_week
    monday = first - timedelta(days=first.weekday())
    while monday <= last:
        week = days_between(monday, monday + timedelta(days=6))
        active = [d for d in week if req.period_start <= d <= req.period_end]
        usable = [d for d in active if first <= d <= last and d >= start]
        if usable:
            target = per_week if len(active) == 7 else round(per_week * len(active) / 7)
            if (req.period_end - req.period_start).days < 7:
                target = max(1, target)  # richiesta più corta di una settimana
            existing = sum(1 for d in existing_dates if monday <= d <= week[-1])
            later = [d for d in active if d > last]
            if later:  # la settimana continua nel mese successivo
                in_month = [d for d in active if d <= last]
                share = round(target * len(in_month) / len(active))
                need = share - existing
            elif any(d < first for d in active):  # la settimana è iniziata nel mese precedente
                before = round(target * sum(1 for d in active if d < first) / len(active))
                need = min(target - existing, target - before)
            else:
                need = target - existing
            need = max(0, min(need, len(usable)))
            if need:
                out[monday] = (usable, need)
        monday += timedelta(days=7)
    return out


def build_demand(first, last, start, rooms_available, existing, only=None):
    from apps.education.models import TeachingRequest

    rows = TeachingRequest.objects.filter(
        status="APPROVED",
        period_start__lte=last,
        period_end__gte=first,
        subject__active=True,
    )
    if only is not None:
        rows = rows.filter(pk__in=list(only))
    else:
        # le richieste in verifica hanno già una bozza dedicata
        rows = rows.exclude(planning_state="REVIEW")
    reqs = list(
        rows.select_related("subject", "student", "group")
        .prefetch_related("preferred_tutors", "group__memberships", "participants")
        .order_by("priority", "created_at")
    )
    singles_done = ever_planned([r.id for r in reqs if r.kind == "SINGLE"])
    demands, skipped = [], []
    for req in reqs:
        people = participants_of(req, first, last)
        if not people:
            continue
        mode = req.mode or ("IN_PERSON" if rooms_available else "ONLINE")
        chosen = [t for t in req.preferred_tutors.all() if t.active]
        if req.kind == "SERIES" or req.tutor_choice == "REQUIRED":
            tutors, preferred = [t.id for t in chosen[:1]], set()
        else:
            competent = [t.id for t in competent_tutors(req, first, last)]
            preferred = {t.id for t in chosen} if req.tutor_choice == "PREFERRED" else set()
            tutors = list(dict.fromkeys([*[t for t in preferred], *competent]))
        d = Demand(req, people, tutors, preferred, mode)
        if req.kind == "SINGLE":
            if req.id in singles_done or (only is not None and existing.get(req.id)):
                continue
            usable = [
                x for x in days_between(max(first, req.period_start), min(last, req.period_end))
                if x >= start
            ]
            if not usable:
                if req.period_end >= first and req.period_start <= last:
                    d.reason = "PAST"
                    skipped.append(d)
                continue
            d.weeks = {usable[0]: (usable, 1)}
        else:
            d.weeks = week_needs(req, first, last, start, existing.get(req.id, []))
            if not d.weeks:
                continue
        if not tutors:
            d.reason = "TUTOR_MISSING" if (req.kind == "SERIES" or req.tutor_choice == "REQUIRED") else "NO_TUTOR"
        elif mode == "IN_PERSON" and not rooms_available:
            d.reason = "NO_ROOMS"
        (skipped if d.reason else demands).append(d)
    return demands, skipped


# --- candidati e modello -------------------------------------------------------------


@dataclass
class Cand:
    demand: int
    day: date
    start: int
    end: int
    tutor: object
    overflow: dict  # ("S"|"T", id) -> (minuti, [etichette])

    @property
    def over_total(self):
        return sum(m for m, _ in self.overflow.values())


def _busy(spans_dt, day, a, b):
    for s, e in spans_dt:
        span = local_span(s, e, day)
        if span and span[0] < b and span[1] > a:
            return True
    return False


def candidates(d, idx, hours, closed, commits, busy_t, busy_s, now):
    req, length, tol = d.req, d.req.duration_minutes, tolerance()
    out, why = [], defaultdict(int)  # why: codice e (lunedì, codice) -> conteggio

    def no(code, week):
        why[code] += 1
        why[(week, code)] += 1

    for monday, (days, _) in d.weeks.items():
        for day in days:
            windows = hours.get(day.weekday(), [])
            if not windows:
                no("CLOSED", monday)
                continue
            shut = closed.get(day, {})
            blocks = [*shut.get("ALL", []), *shut.get(d.mode, [])]
            people = [("S", s) for s in d.participants]
            starts = set()
            for a, b in windows:
                if req.fixed_time:
                    starts.add(minutes(req.fixed_time))
                    continue
                s0 = a + (-a) % 15
                starts.update(range(s0, b - length + 1, STEP))
                for key in people + [("T", t) for t in d.tutors]:
                    for ca, cb, _ in commits.get(key, {}).get(day, []):
                        for s in (cb, ca - length, cb - tol, ca - length + tol):
                            s += (-s) % 15
                            starts.add(s)
            for s in sorted(starts):
                e = s + length
                if not any(a <= s and e <= b for a, b in windows):
                    # gli inizi allineati agli impegni fuori orario non sono un motivo
                    if req.fixed_time:
                        no("FIXED_TIME", monday)
                    continue
                if any(ca < e and cb > s for ca, cb, _ in blocks):
                    no("CLOSED", monday)
                    continue
                if at(day, s) <= now:
                    no("PAST", monday)
                    continue
                over, ok = {}, True
                for key in people:
                    spans = commits.get(key, {}).get(day, [])
                    m = overlap(s, e, spans)
                    if m > tol:
                        no("STUDENT_BUSY", monday)
                        ok = False
                        break
                    if m:
                        over[key] = (m, sorted({l for ca, cb, l in spans if ca < e and cb > s}))
                    if _busy(busy_s.get(key[1], []), day, s, e):
                        no("BUSY", monday)
                        ok = False
                        break
                if not ok:
                    continue
                for t in d.tutors:
                    spans = commits.get(("T", t), {}).get(day, [])
                    m = overlap(s, e, spans)
                    if m > tol:
                        no("TUTOR_BUSY", monday)
                        continue
                    if _busy(busy_t.get(t, []), day, s, e):
                        no("BUSY", monday)
                        continue
                    o = dict(over)
                    if m:
                        o[("T", t)] = (m, sorted({l for ca, cb, l in spans if ca < e and cb > s}))
                    out.append(Cand(idx, day, s, e, t, o))
    return out, why


def week_reason(why, monday):
    """Motivo prevalente per la settimana senza candidati (poi per l'intera richiesta)."""
    week = {k[1]: v for k, v in why.items() if isinstance(k, tuple) and k[0] == monday}
    overall = {k: v for k, v in why.items() if not isinstance(k, tuple)}
    pool = week or overall
    return max(pool, key=pool.get) if pool else "CLOSED"


def solve(demands, cands, first, rooms, room_busy, time_limit):
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    x = [m.NewBoolVar(f"x{i}") for i in range(len(cands))]
    absolute = lambda c: (c.day - first).days * 1440
    obj = []
    by_demand = defaultdict(list)
    for i, c in enumerate(cands):
        by_demand[c.demand].append(i)
    placed_total = {}
    for di, d in enumerate(demands):
        idx = by_demand.get(di, [])
        weight = PRIORITY_WEIGHT.get(d.req.priority, 2) * (2 if d.req.mandatory else 1)
        # un solo tutor per richiesta nel mese
        z = {t: m.NewBoolVar(f"z{di}_{t}") for t in {cands[i].tutor for i in idx}}
        if z:
            m.Add(sum(z.values()) <= 1)
        for i in idx:
            m.AddImplication(x[i], z[cands[i].tutor])
        for t in d.preferred & set(z):
            obj.append(-W_PREFERRED * z[t])
        # al massimo una lezione al giorno per richiesta
        per_day = defaultdict(list)
        for i in idx:
            per_day[cands[i].day].append(x[i])
        for vs in per_day.values():
            if len(vs) > 1:
                m.AddAtMostOne(vs)
        placed = []
        for monday, (days, need) in d.weeks.items():
            vs = [x[i] for i in idx if cands[i].day in set(days)]
            if vs:
                m.Add(sum(vs) <= need)
            placed.extend(vs)
            obj.append(W_MISS * weight * (need - sum(vs)) if vs else W_MISS * weight * need)
        placed_total[di] = placed
        # regolarità settimanale (stesso giorno e ora) per le richieste ricorrenti
        if d.req.kind != "SINGLE" and len(d.weeks) > 1 and idx:
            keys = {(cands[i].day.weekday(), cands[i].start) for i in idx}
            y = {k: m.NewBoolVar(f"y{di}_{k[0]}_{k[1]}") for k in keys}
            m.Add(sum(y.values()) <= d.req.sessions_per_week)
            dev = {day: m.NewBoolVar(f"dev{di}_{day}") for day in per_day}
            for i in idx:
                c = cands[i]
                m.AddBoolOr([x[i].Not(), y[(c.day.weekday(), c.start)], dev[c.day]])
            obj.extend(W_PATTERN * v for v in dev.values())
    for i, c in enumerate(cands):
        if c.over_total:
            obj.append(W_OVER * c.over_total * x[i])
    # niente sovrapposizioni per tutor e studenti
    per_tutor, per_student, per_day_tutor, per_day_student = (
        defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    )
    for i, c in enumerate(cands):
        base = absolute(c)
        iv = m.NewOptionalFixedSizeIntervalVar(base + c.start, c.end - c.start, x[i], f"i{i}")
        per_tutor[c.tutor].append(iv)
        per_day_tutor[(c.tutor, c.day)].append(i)
        for s in demands[c.demand].participants:
            per_student[s].append(iv)
            per_day_student[(s, c.day)].append(i)
    for ivs in [*per_tutor.values(), *per_student.values()]:
        if len(ivs) > 1:
            m.AddNoOverlap(ivs)
    # aule: lezioni in presenza contemporanee ≤ aule libere
    presence = [i for i, c in enumerate(cands) if demands[c.demand].mode == "IN_PERSON"]
    if presence:
        ivs, dem = [], []
        for i in presence:
            c = cands[i]
            base = absolute(c)
            ivs.append(m.NewOptionalFixedSizeIntervalVar(base + c.start, c.end - c.start, x[i], f"r{i}"))
            dem.append(1)
        for k, (a, b) in enumerate(room_busy):
            ivs.append(m.NewFixedSizeIntervalVar(a, b - a, f"rb{k}"))
            dem.append(1)
        m.AddCumulative(ivs, dem, rooms)
    # buchi nelle giornate (solo dove possono esserci due o più lezioni)
    for weight, groups in ((W_GAP_TUTOR, per_day_tutor), (W_GAP_STUDENT, per_day_student)):
        for (who, day), idx in groups.items():
            if len({cands[i].demand for i in idx}) < 2:
                continue
            lo = min(cands[i].start for i in idx)
            hi = max(cands[i].end for i in idx)
            S = m.NewIntVar(lo, hi, "")
            E = m.NewIntVar(lo, hi, "")
            m.Add(E >= S)
            for i in idx:
                m.Add(S <= cands[i].start).OnlyEnforceIf(x[i])
                m.Add(E >= cands[i].end).OnlyEnforceIf(x[i])
            obj.append(weight * (E - S))
            obj.extend(-weight * (cands[i].end - cands[i].start) * x[i] for i in idx)
    m.Minimize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = int(getattr(settings, "AUTOPLAN_WORKERS", 8))
    solver.parameters.random_seed = 7
    status = solver.Solve(m)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return name, []
    return name, [c for i, c in enumerate(cands) if solver.Value(x[i])]


def assign_rooms(chosen, demands, spaces, room_busy_by_space, first):
    """Aule assegnate in ordine di inizio (ottimo per aule equivalenti)."""
    used = {s.id: list(room_busy_by_space.get(s.id, [])) for s in spaces}
    out = {}
    order = sorted(
        (c for c in chosen if demands[c.demand].mode == "IN_PERSON"),
        key=lambda c: (c.day, c.start),
    )
    for c in order:
        a = (c.day - first).days * 1440 + c.start
        b = a + c.end - c.start
        size = len(demands[c.demand].participants)
        free = [s for s in spaces if all(e <= a or s0 >= b for s0, e in used[s.id])]
        fit = [s for s in free if (s.student_capacity or 0) >= size]
        if fit:
            room = min(fit, key=lambda s: (s.student_capacity or 0, s.name))
            used[room.id].append((a, b))
            out[id(c)] = room.id
    return out


# --- ingresso principale ------------------------------------------------------------


def compute(first, last, now, only=None, extra=(), time_limit=None, exclude_plan=None):
    """Esegue il motore su [first, last] (al più un mese) e restituisce il risultato senza
    salvarlo. ``only``: limita la domanda a queste richieste; ``extra``: lezioni già scelte
    in questa stessa esecuzione (mesi precedenti) che occupano persone e aule."""
    from apps.education.models import Resource

    start = max(first, now.astimezone(ROME).date())
    spaces = list(Resource.objects.filter(kind="SPACE", active=True).order_by("name"))
    hours = opening_hours()
    closed = closures(first, last)
    busy_t, busy_s, busy_r, existing = occupied(first, last, exclude_plan=exclude_plan)
    for row in extra:
        busy_t[row["tutor_id"]].append((row["start_at"], row["end_at"]))
        for sid in row["participants"]:
            busy_s[UUID(str(sid))].append((row["start_at"], row["end_at"]))
        if row["space_id"]:
            busy_r[row["space_id"]].append((row["start_at"], row["end_at"]))
        existing[row["request"].id].append(row["start_at"].astimezone(ROME).date())
    demands, skipped = build_demand(first, last, start, bool(spaces), existing, only=only)
    students = {s for d in demands for s in d.participants}
    tutors = {t for d in demands for t in d.tutors}
    commits = commitments(first, last, students, tutors)
    cands, why = [], {}
    for i, d in enumerate(demands):
        c, w = candidates(d, i, hours, closed, commits, busy_t, busy_s, now)
        cands.extend(c)
        why[i] = w
    room_busy, room_busy_by_space = [], defaultdict(list)
    for sid, spans in busy_r.items():
        for s, e in spans:
            a = int((s.astimezone(ROME) - at(first, 0)).total_seconds() // 60)
            b = int(ceil((e.astimezone(ROME) - at(first, 0)).total_seconds() / 60))
            if b > 0 and a < (last - first).days * 1440 + 1440:
                room_busy.append((max(a, 0), b))
                room_busy_by_space[sid].append((max(a, 0), b))
    limit = time_limit or getattr(settings, "AUTOPLAN_TIME_LIMIT_SECONDS", 12)
    status, chosen = ("NO_CANDIDATES", []) if not cands else solve(
        demands, cands, first, len(spaces), room_busy, limit
    )
    rooms = assign_rooms(chosen, demands, spaces, room_busy_by_space, first)
    # una lezione in presenza senza aula adatta non si può pubblicare: resta da collocare
    chosen = [c for c in chosen if demands[c.demand].mode != "IN_PERSON" or id(c) in rooms]
    placed = defaultdict(int)
    for c in chosen:
        placed[c.demand] += 1
    unplaced = []
    for d in skipped:
        unplaced.append({**_unplaced(d, d.needed, d.reason), "weeks": sorted(min(days).isoformat() for days, _ in d.weeks.values())})
    for i, d in enumerate(demands):
        missing = d.needed - placed[i]
        if missing <= 0:
            continue
        mine = [c for c in chosen if c.demand == i]
        offered = [c for c in cands if c.demand == i]
        weeks, reasons = [], defaultdict(int)
        for monday, (days, need) in d.weeks.items():
            got = sum(1 for c in mine if c.day in days)
            if got >= need:
                continue
            weeks.append(min(days).isoformat())
            if any(c.day in days for c in offered):
                reasons["FULL"] += need - got
            else:
                reasons[week_reason(why[i], monday)] += need - got
        reason = max(reasons, key=reasons.get) if reasons else "FULL"
        unplaced.append({**_unplaced(d, missing, reason), "weeks": weeks})
    rows = []
    for c in chosen:
        d = demands[c.demand]
        rows.append({
            "request": d.req,
            "tutor_id": c.tutor,
            "subject_id": d.req.subject_id,
            "mode": d.mode,
            "space_id": rooms.get(id(c)),
            "start_at": at(c.day, c.start),
            "end_at": at(c.day, c.end),
            "participants": [str(s) for s in d.participants],
            "overflow": c.overflow,
        })
    stats = {
        "requests": len(demands) + len(skipped),
        "needed": sum(d.needed for d in demands) + sum(d.needed for d in skipped),
        "placed": len(chosen),
        "overflow": sum(1 for c in chosen if c.overflow),
        "candidates": len(cands),
        "tolerance_minutes": tolerance(),
        "opening_days": sorted(hours),
    }
    return status, rows, unplaced, stats


def save_lessons(plan, rows):
    from .models import AutoPlanConfirmation, AutoPlanLesson

    for row in rows:
        lesson = AutoPlanLesson.objects.create(
            plan=plan,
            request=row["request"],
            tutor_id=row["tutor_id"],
            subject_id=row["subject_id"],
            mode=row["mode"],
            space_id=row["space_id"],
            start_at=row["start_at"],
            end_at=row["end_at"],
            participants=row["participants"],
            overflow_minutes=max((m for m, _ in row["overflow"].values()), default=0),
        )
        for (kind, who), (mins, labels) in sorted(row["overflow"].items(), key=str):
            AutoPlanConfirmation.objects.create(
                lesson=lesson,
                party="STUDENT" if kind == "S" else "TUTOR",
                student_id=who if kind == "S" else None,
                tutor_id=who if kind == "T" else None,
                minutes=mins,
                labels=labels,
            )


def plan_month(month, actor, time_limit=None, now=None):
    """Calcola e salva una bozza (``AutoPlan``) per il mese. Sostituisce le bozze."""
    from django.db import transaction
    from .models import AutoPlan

    now = now or timezone.now()
    first = month_start(month)
    last = month_end(first)
    status, rows, unplaced, stats = compute(first, last, now, time_limit=time_limit)
    with transaction.atomic():
        AutoPlan.objects.filter(month=first, state="DRAFT", request__isnull=True).update(state="DISCARDED")
        plan = AutoPlan.objects.create(
            month=first, actor=actor, solver_status=status, unplaced=unplaced, stats=stats,
        )
        save_lessons(plan, rows)
    return plan


# --- ricalcolo automatico di una singola richiesta (v0.9.9) ------------------------------


def request_months(req, now):
    """Mesi da pianificare per la richiesta: dal primo giorno utile alla fine del periodo."""
    today = now.astimezone(ROME).date()
    first = month_start(max(req.period_start, today))
    out = []
    while first <= req.period_end:
        out.append(first)
        first = month_end(first) + timedelta(days=1)
    return out


def request_month(req, now, month=None):
    """Mese su cui lavora la verifica: quello chiesto (se nel periodo della richiesta),
    altrimenti il primo mese utile. Il motore lavora sempre su un solo mese."""
    months = request_months(req, now)
    if month is not None:
        wanted = month_start(month)
        if wanted in months:
            return wanted, months
    return (months[0] if months else None), months


def plan_request(req, actor, now=None, time_limit=None, month=None):
    """Ricalcola il motore per una sola richiesta approvata, **su un solo mese** (il primo
    utile o quello indicato), e salva una bozza dedicata che il centro verifica prima di
    completare la richiesta. I mesi successivi li pianifica il calendario mensile.
    Le lezioni già pubblicate restano ferme e occupano tutor, studenti e aule; le bozze
    delle altre richieste in verifica sono considerate occupate."""
    from django.db import transaction
    from .models import AutoPlan

    now = now or timezone.now()
    limit = time_limit or getattr(settings, "AUTOPLAN_REQUEST_TIME_LIMIT_SECONDS", 5)
    old = list(AutoPlan.objects.filter(request=req, state="DRAFT"))
    rows, unplaced, statuses = [], [], []
    stats = {"requests": 1, "needed": 0, "placed": 0, "overflow": 0, "candidates": 0, "tolerance_minutes": tolerance()}
    chosen_month, all_months = request_month(req, now, month)
    # una richiesta singola dura al più una settimana (anche a cavallo di due mesi)
    months = all_months if req.kind == "SINGLE" else ([chosen_month] if chosen_month else [])
    for first in months:
        last = min(month_end(first), req.period_end)
        status, chosen, missing, st = compute(
            first, last, now, only=[req.id], extra=rows, time_limit=limit,
            exclude_plan=old,
        )
        statuses.append(status)
        rows.extend(chosen)
        unplaced.extend(missing)
        for k in ("needed", "placed", "overflow", "candidates"):
            stats[k] += st.get(k, 0)
        stats["opening_days"] = st.get("opening_days", [])
    if not months:
        unplaced.append({
            "request_id": str(req.id), "subject": req.subject.name, "who": request_who(req), "kind": req.kind,
            "missing": 1 if req.kind == "SINGLE" else 0, "reason": "PAST", "message": REASONS["PAST"], "weeks": [],
        })
    merged = {}
    for u in unplaced:  # un elemento per motivo, con tutte le settimane scoperte
        m = merged.setdefault(u["reason"], {**u, "missing": 0, "weeks": []})
        m["missing"] += u["missing"]
        m["weeks"] = sorted(set(m["weeks"]) | set(u.get("weeks") or []))
    if req.kind == "SINGLE":  # una sola lezione, anche se la settimana è a cavallo di due mesi
        if rows:
            merged = {}
        else:
            merged = dict(list(merged.items())[:1])
            for m in merged.values():
                m["missing"] = 1
    status = "OPTIMAL" if statuses and all(s == "OPTIMAL" for s in statuses) else (
        "FEASIBLE" if any(s in ("OPTIMAL", "FEASIBLE") for s in statuses) else (statuses[-1] if statuses else "NO_CANDIDATES")
    )
    from .corrections import discard_for_plans

    with transaction.atomic():
        discard_for_plans([p.id for p in old])
        for p in old:
            p.state = "DISCARDED"
            p.save(update_fields=["state", "updated_at"])
            p.lessons.filter(state="PROPOSED").update(state="DISCARDED")
        plan = AutoPlan.objects.create(
            month=months[0] if months else month_start(req.period_start),
            actor=actor,
            request=req,
            solver_status=status,
            unplaced=[m for m in merged.values() if m["missing"] > 0],
            stats={
                **stats,
                "months": [m.isoformat()[:7] for m in months],
                "request_months": [m.isoformat()[:7] for m in all_months],
            },
        )
        save_lessons(plan, rows)
        type(req).objects.filter(pk=req.pk).update(planning_state="REVIEW", completed_at=None)
    req.planning_state, req.completed_at = "REVIEW", None
    return plan


def request_who(req):
    if req.group_label:
        return req.group_label
    return req.student.display_name if req.student_id else (req.group.name if req.group_id else "")


def _unplaced(d, missing, reason):
    req = d.req
    who = request_who(req)
    return {
        "request_id": str(req.id),
        "subject": req.subject.name,
        "who": who,
        "kind": req.kind,
        "missing": missing,
        "reason": reason,
        "message": REASONS.get(reason, reason),
    }


# --- spostamenti manuali dall'agenda ----------------------------------------------------


def is_monthly_lesson(lesson):
    """Lezione nata dal pianificatore mensile (o senza catena del motore settimanale)."""
    publication = getattr(lesson, "publication", None)
    if publication is None:
        return True
    try:
        data = publication.plan.run.snapshot.data or {}
    except AttributeError:
        return True
    return data.get("source") == "autoplan" or "mode" not in data


def _move_checker(lesson, day, duration=None, ignore=()):
    """Prepara i dati del giorno ``day`` e restituisce ``check(target) -> [codici]``.

    ``duration`` (timedelta) permette di verificare anche un cambio di durata."""
    from apps.calendar.models import LessonOccurrence

    duration = duration or (lesson.end_at - lesson.start_at)
    length = int(duration.total_seconds() // 60)
    windows = opening_hours().get(day.weekday(), [])
    shut = closures(day, day).get(day, {})
    blocks = [*shut.get("ALL", []), *shut.get(lesson.mode, [])]
    students = list(lesson.participants.values_list("student_id", flat=True))
    sids = {str(x) for x in students}
    commits = commitments(day, day, students, [lesson.tutor_id])
    tutor_commits = commits.get(("T", lesson.tutor_id), {}).get(day, [])
    student_commits = [commits.get(("S", sid), {}).get(day, []) for sid in students]
    tol = tolerance()
    lo, hi = at(day, 0) - timedelta(hours=6), at(day, 1440) + timedelta(hours=6)
    busy = []  # (inizio, fine) che occupano tutor, studenti o aula della lezione
    for o in (
        LessonOccurrence.objects.filter(state__in=("PUBLISHED", "COMPLETED"), start_at__lt=hi, end_at__gt=lo)
        .exclude(pk=lesson.pk)
        .exclude(pk__in=list(ignore))
        .prefetch_related("participants")
    ):
        if o.tutor_id == lesson.tutor_id:
            busy.append((o.start_at, o.tutor_occupied_until or o.end_at))
        if sids & {str(p.student_id) for p in o.participants.all()}:
            busy.append((o.start_at, o.end_at))
        if lesson.space_id and o.space_id == lesson.space_id:
            busy.append((o.start_at, o.space_occupied_until or o.end_at))
    for w in reserved_lessons().filter(start_at__lt=hi, end_at__gt=lo).exclude(occurrence=lesson).exclude(occurrence__in=list(ignore)):
        if w.tutor_id == lesson.tutor_id or sids & {str(x) for x in w.participants} or (lesson.space_id and w.space_id == lesson.space_id):
            busy.append((w.start_at, w.end_at))

    def check(target, now=None):
        now = now or timezone.now()
        local = target.astimezone(ROME)
        s = local.hour * 60 + local.minute
        e = s + length
        end_at = target + duration
        if target <= now:
            return ["PAST_LESSON"]
        if e > 1440:
            return ["CROSS_LOCAL_MIDNIGHT"]
        codes = []
        if windows and not any(a <= s and e <= b for a, b in windows):
            codes.append("SERVICE_CLOSED")
        if any(ca < e and cb > s for ca, cb, _ in blocks):
            codes.append("CLOSURE")
        if overlap(s, e, tutor_commits) > tol:
            codes.append("TUTOR_AVAILABILITY")
        if any(overlap(s, e, spans) > tol for spans in student_commits):
            codes.append("STUDENT_AVAILABILITY")
        if any(a < end_at and b > target for a, b in busy):
            codes.append("RESOURCE_OVERLAP")
        return codes

    return check


def move_codes(lesson, target, now=None, duration=None, ignore=()):
    """Motivi per cui ``lesson`` non può iniziare a ``target`` (lista vuota = spostamento ammesso).

    Stessi vincoli del pianificatore mensile: orari di apertura e chiusure (rigidi), impegni
    di tutor e studenti oltre la tolleranza, lezioni e aule già occupate.
    """
    return _move_checker(lesson, target.astimezone(ROME).date(), duration, ignore)(target, now)


def move_options(lesson, day, now=None, duration=None):
    """Esito per ogni inizio a 15 minuti del giorno ``day`` (nessun effetto)."""
    from datetime import timezone as dt_timezone

    check = _move_checker(lesson, day, duration)
    local = datetime.combine(day, time(0), tzinfo=ROME)
    out = []
    while local.date() == day:
        start = local.astimezone(dt_timezone.utc)
        codes = check(start, now)
        out.append({"start_at": start.isoformat(), "ok": not codes, "codes": codes})
        local = (start + timedelta(minutes=15)).astimezone(ROME)
    return out
