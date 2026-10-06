"""Orari suggeriti dal motore (v0.9.8): recuperi, nuove lezioni, trascinamento in agenda.

Stessi vincoli del pianificatore mensile, applicati a una lezione alla volta:
- orari di apertura del centro e chiusure (rigidi);
- impegni di **tutte** le persone coinvolte — il tutor e ogni studente — senza sforamenti;
- lezioni già in calendario o in attesa di conferma che occupano tutor, studenti o aule;
- in presenza serve un'aula libera con posti sufficienti (se il centro ha aule).

Le proposte sono ordinate come farebbe il motore: vicine all'orario preferito (per un
recupero, quello della lezione persa), con il tutor preferito, e attaccate ad altre lezioni
del tutor per non lasciare buchi nella giornata.
"""

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .autoplan import ROME, at, closures, commitments, days_between, opening_hours, overlap

DEFAULT_HOURS = [(14 * 60, 20 * 60)]  # se il centro non ha ancora orari di apertura
STEP = 30

TEXT = {
    "PAST_LESSON": "l’orario è già passato",
    "CROSS_LOCAL_MIDNIGHT": "la lezione supererebbe la mezzanotte",
    "SERVICE_CLOSED": "il centro è chiuso in quell’orario",
    "CLOSURE": "c’è una chiusura programmata",
    "TUTOR_AVAILABILITY": "il tutor ha un impegno",
    "STUDENT_AVAILABILITY": "lo studente ha un impegno",
    "TUTOR_BUSY": "il tutor ha già un’altra lezione",
    "STUDENT_BUSY": "lo studente ha già un’altra lezione",
    "NO_ROOM": "nessuna aula libera con posti sufficienti",
    "NO_STUDENTS": "nessuno studente partecipante",
}


def _occupancy(lo, hi, ignore, ignore_auto=()):
    from apps.calendar.models import LessonOccurrence
    from .autoplan import reserved_lessons

    ignore = [i for i in ignore if i]
    ignore_auto = [i for i in ignore_auto if i]
    tutor, student, room = defaultdict(list), defaultdict(list), defaultdict(list)
    rows = (
        LessonOccurrence.objects.filter(
            state__in=("PUBLISHED", "COMPLETED"), start_at__lt=hi, end_at__gt=lo
        )
        .exclude(pk__in=ignore)
        .prefetch_related("participants")
    )
    for o in rows:
        tutor[str(o.tutor_id)].append((o.start_at, o.tutor_occupied_until or o.end_at))
        for p in o.participants.all():
            student[str(p.student_id)].append((o.start_at, o.end_at))
        if o.space_id:
            room[str(o.space_id)].append((o.start_at, o.space_occupied_until or o.end_at))
    # in attesa di conferma o proposte in una richiesta in verifica (v0.9.9)
    waiting = reserved_lessons().filter(start_at__lt=hi, end_at__gt=lo)
    if ignore:
        waiting = waiting.exclude(occurrence_id__in=ignore)
    if ignore_auto:
        waiting = waiting.exclude(pk__in=ignore_auto)
    for w in waiting:
        tutor[str(w.tutor_id)].append((w.start_at, w.end_at))
        for sid in w.participants:
            student[str(sid)].append((w.start_at, w.end_at))
        if w.space_id:
            room[str(w.space_id)].append((w.start_at, w.end_at))
    return tutor, student, room


def _hits(spans, a, b):
    return any(s < b and e > a for s, e in spans)


class Finder:
    """Verifica e propone orari per una lezione di ``minutes`` minuti fra ``first`` e ``last``."""

    def __init__(self, students, tutors, mode, minutes, first, last, ignore=(), ignore_auto=()):
        from apps.education.models import Resource

        self.students = [str(s) for s in students]
        self.tutors = list(dict.fromkeys(str(t) for t in tutors))
        self.mode = mode
        self.length = int(minutes)
        self.hours = opening_hours()
        self.closed = closures(first, last)
        raw = commitments(first, last, self.students, self.tutors)
        self.commits = {(k[0], str(k[1])): v for k, v in raw.items()}
        lo, hi = at(first, 0) - timedelta(hours=8), at(last, 1440) + timedelta(hours=8)
        self.busy_t, self.busy_s, self.busy_r = _occupancy(lo, hi, list(ignore), list(ignore_auto))
        self.rooms = (
            list(Resource.objects.filter(kind="SPACE", active=True).order_by("name"))
            if mode == "IN_PERSON"
            else []
        )

    def windows(self, day):
        if not self.hours:
            return DEFAULT_HOURS
        return self.hours.get(day.weekday(), [])

    def check(self, tutor_id, start, now=None):
        """{"codes": [...], "space_id": aula scelta o None}. Nessun codice = orario valido."""
        now = now or timezone.now()
        tutor_id = str(tutor_id)
        local = start.astimezone(ROME)
        day = local.date()
        s = local.hour * 60 + local.minute
        e = s + self.length
        end = start + timedelta(minutes=self.length)
        codes = []
        if start <= now:
            codes.append("PAST_LESSON")
        if e > 1440:
            return {"codes": [*codes, "CROSS_LOCAL_MIDNIGHT"], "space_id": None}
        if not any(a <= s and e <= b for a, b in self.windows(day)):
            codes.append("SERVICE_CLOSED")
        shut = self.closed.get(day, {})
        if any(ca < e and cb > s for ca, cb, _ in [*shut.get("ALL", []), *shut.get(self.mode, [])]):
            codes.append("CLOSURE")
        if overlap(s, e, self.commits.get(("T", tutor_id), {}).get(day, [])):
            codes.append("TUTOR_AVAILABILITY")
        if any(overlap(s, e, self.commits.get(("S", sid), {}).get(day, [])) for sid in self.students):
            codes.append("STUDENT_AVAILABILITY")
        if _hits(self.busy_t.get(tutor_id, []), start, end):
            codes.append("TUTOR_BUSY")
        if any(_hits(self.busy_s.get(sid, []), start, end) for sid in self.students):
            codes.append("STUDENT_BUSY")
        space = None
        if self.mode == "IN_PERSON":
            # solo aule libere e abbastanza grandi per tutti i partecipanti
            free = [r for r in self.rooms if not _hits(self.busy_r.get(str(r.id), []), start, end)]
            fit = [r for r in free if (r.student_capacity or 0) >= len(self.students)]
            if fit:
                space = min(fit, key=lambda r: (r.student_capacity or 0, r.name)).id
            else:
                codes.append("NO_ROOM")
        return {"codes": codes, "space_id": space}

    def _starts(self, day):
        """Inizi candidati: ogni mezz'ora nelle aperture, più subito dopo la fine di impegni
        e lezioni delle persone coinvolte (es. 14:15 se la scuola finisce alle 14:15)."""
        starts = set()
        for a, b in self.windows(day):
            m = a
            while m + self.length <= b:
                starts.add(m)
                m += STEP
        ends = []
        for key in [("T", t) for t in self.tutors] + [("S", s) for s in self.students]:
            ends += [b for _, b, *_ in self.commits.get(key, {}).get(day, [])]
        base = at(day, 0)
        for spans in [*(self.busy_t.get(t, []) for t in self.tutors), *(self.busy_s.get(s, []) for s in self.students)]:
            for _, b in spans:
                if b.astimezone(ROME).date() == day:
                    ends.append(int((b.astimezone(ROME) - base).total_seconds() // 60))
        for m in ends:
            if any(a <= m and m + self.length <= b for a, b in self.windows(day)):
                starts.add(m)
        return sorted(starts)

    def _adjacent(self, tutor_id, start, end):
        return any(abs((b - start).total_seconds()) < 60 or abs((a - end).total_seconds()) < 60 for a, b in self.busy_t.get(tutor_id, []))

    def suggest(self, first, last, prefer_tutor=None, prefer_minute=None, limit=12, per_day=3, now=None):
        from apps.education.models import Resource, Tutor

        now = now or timezone.now()
        names = dict(Tutor.objects.filter(pk__in=self.tutors).values_list("id", "display_name"))
        names = {str(k): v for k, v in names.items()}
        prefer_tutor = str(prefer_tutor) if prefer_tutor else None
        out = []
        for day in days_between(first, last):
            found = []
            for rank, tutor_id in enumerate(self.tutors):
                for m in self._starts(day):
                    start = at(day, m)
                    res = self.check(tutor_id, start, now)
                    if res["codes"]:
                        continue
                    end = start + timedelta(minutes=self.length)
                    target = prefer_minute if prefer_minute is not None else 16 * 60
                    score = abs(m - target) // 2 + rank * 5
                    if prefer_tutor and tutor_id != prefer_tutor:
                        score += 45
                    if self._adjacent(tutor_id, start, end):
                        score -= 20
                    if m % STEP:
                        score += 5
                    found.append((score, m, tutor_id, res["space_id"], start, end))
            found.sort(key=lambda x: (x[0], x[1]))
            taken = []
            for score, m, tutor_id, space, start, end in found:
                if any(abs(m - t) < self.length // 2 for t in taken):
                    continue
                taken.append(m)
                out.append({
                    "date": day.isoformat(),
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "tutor_id": tutor_id,
                    "tutor_name": names.get(tutor_id, ""),
                    "space_id": str(space) if space else None,
                    "score": score,
                    "same_tutor": bool(prefer_tutor) and tutor_id == prefer_tutor,
                })
                if len(taken) >= per_day:
                    break
            if len(out) >= limit:
                break
        spaces = {str(r.id): r.name for r in Resource.objects.filter(pk__in=[o["space_id"] for o in out if o["space_id"]])}
        for o in out:
            o["space_name"] = spaces.get(o["space_id"]) if o["space_id"] else None
        return out[:limit]


def explain(codes):
    return [TEXT.get(c, c.lower().replace("_", " ")) for c in codes]


def competent(subject_id, mode, first, last):
    """Tutor attivi con competenza approvata per materia e modalità nel periodo."""
    from types import SimpleNamespace
    from .autoplan import competent_tutors

    return [t.id for t in competent_tutors(SimpleNamespace(subject_id=subject_id, mode=mode), first, last)]
