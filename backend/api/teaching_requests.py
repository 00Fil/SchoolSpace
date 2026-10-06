"""Richieste didattiche (v0.9.4).

Il centro crea richieste già approvate; le famiglie inviano richieste per i
propri figli, che restano PENDING finché il centro non le approva. Il motore
di pianificazione considera solo le richieste APPROVED (apps.scheduling.source).
Il tutor può essere libero (ANY), preferito (PREFERRED, vincolo morbido) o
obbligatorio (REQUIRED, vincolo duro).
"""

from datetime import date
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from apps.identity.policies import is_center, visible_students, active_roles
from apps.education.models import RequestParticipant, Student, Subject, Tutor, TeachingRequest
from apps.scheduling import request_review
from apps.scheduling.models import TutorSkill
from .serializers import RequestSerializer

EDITABLE_BY_CENTER = {
    "mode",
    "duration_minutes",
    "sessions_per_week",
    "priority",
    "mandatory",
    "period_start",
    "period_end",
    "tutor_choice",
    "preferred_tutor_ids",
    "notes",
    "fixed_time",
}

KINDS = ["SINGLE", "SERIES", "WEEKLY"]


MAX_GROUP = 8


class RequestInput(serializers.Serializer):
    # Uno studente, oppure (solo centro) una lezione di gruppo con 2–8 partecipanti.
    student = serializers.UUIDField(required=False, allow_null=True)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=MAX_GROUP
    )
    group_label = serializers.CharField(max_length=100, required=False, allow_blank=True)
    subject = serializers.UUIDField()
    # Senza tipo la richiesta resta settimanale sul periodo (compatibilità v0.9.4).
    kind = serializers.ChoiceField(choices=KINDS, required=False, default="WEEKLY")
    mode = serializers.ChoiceField(choices=["IN_PERSON", "ONLINE"])
    duration_minutes = serializers.ChoiceField(choices=[60, 90, 120])
    sessions_per_week = serializers.IntegerField(
        min_value=1, max_value=7, required=False, default=1
    )
    period_start = serializers.DateField()
    period_end = serializers.DateField(required=False, allow_null=True)
    fixed_time = serializers.TimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=["P0", "P1", "P2"], required=False)
    mandatory = serializers.BooleanField(required=False)
    tutor_choice = serializers.ChoiceField(
        choices=["ANY", "PREFERRED", "REQUIRED"], required=False
    )
    preferred_tutor_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=5
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, data):
        return normalize(data, center=self.context.get("center", False))


class RequestPatch(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["IN_PERSON", "ONLINE"], required=False)
    duration_minutes = serializers.ChoiceField(choices=[60, 90, 120], required=False)
    sessions_per_week = serializers.IntegerField(
        min_value=1, max_value=7, required=False
    )
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False, allow_null=True)
    fixed_time = serializers.TimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=["P0", "P1", "P2"], required=False)
    mandatory = serializers.BooleanField(required=False)
    tutor_choice = serializers.ChoiceField(
        choices=["ANY", "PREFERRED", "REQUIRED"], required=False
    )
    preferred_tutor_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=5
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, data):
        current = self.context["instance"]
        merged = {
            "kind": current.kind,
            "mode": current.mode,
            "duration_minutes": current.duration_minutes,
            "sessions_per_week": current.sessions_per_week,
            "period_start": current.period_start,
            "period_end": current.period_end,
            "fixed_time": current.fixed_time,
            "tutor_choice": current.tutor_choice,
            "preferred_tutor_ids": [t.id for t in current.preferred_tutors.all()],
        }
        merged.update(data)
        cleaned = normalize(merged, center=True)
        # Il tipo non cambia; i campi derivati (fine del periodo, tutor del
        # percorso) vengono riscritti insieme a quelli modificati.
        cleaned.pop("kind")
        return cleaned


def closed_reason(day, fixed, minutes, mode=None):
    """Testo d'errore se la lezione a orario fisso cade quando il centro è chiuso
    (fuori dagli orari di apertura o durante una chiusura), altrimenti ``None``."""
    from apps.scheduling.autoplan import closures, opening_hours

    hours = opening_hours()
    if not hours:  # orari del centro non ancora configurati: nessun vincolo
        return None
    a = fixed.hour * 60 + fixed.minute
    b = a + int(minutes)
    if not any(x <= a and b <= y for x, y in hours.get(day.weekday(), [])):
        return "Il centro è chiuso in quell'orario: scegli un orario dentro l'apertura"
    shut = closures(day, day).get(day, {})
    spans = [*shut.get("ALL", []), *shut.get(mode or "IN_PERSON", [])]
    hit = next((r for x, y, r in spans if x < b and y > a), None)
    if hit is not None:
        return "Il centro è chiuso in quell'orario" + (f" ({hit})" if hit else "")
    return None


def normalize(data, center):
    """Regole per tipo di richiesta. Ricalcola i campi derivati e rifiuta le
    combinazioni ambigue, così che il motore riceva sempre una domanda chiara."""
    kind = data.get("kind") or "WEEKLY"
    start = data["period_start"]
    end = data.get("period_end")
    fixed = data.get("fixed_time")
    errors = {}
    if kind == "SINGLE":
        data["sessions_per_week"] = 1
        if fixed is not None:
            # Lezione piazzata: giorno e orario precisi.
            end = start
            if fixed.minute % 15 or fixed.second:
                errors["fixed_time"] = "L'orario deve essere a quarti d'ora"
            else:
                closed = closed_reason(start, fixed, data.get("duration_minutes") or 60, data.get("mode"))
                if closed:
                    errors["fixed_time"] = closed
        elif end is None:
            end = start
        elif end < start or end.isocalendar()[:2] != start.isocalendar()[:2]:
            errors["period_end"] = (
                "Una lezione singola si colloca in un giorno o in una sola settimana"
            )
        data["period_end"] = end
    elif kind == "SERIES":
        # Ricorrente: solo il numero di lezioni a settimana, dal primo giorno
        # fino alla fine indicata (di norma la fine dell'anno scolastico).
        if (data.get("sessions_per_week") or 1) > 5:
            errors["sessions_per_week"] = "Massimo 5 lezioni a settimana"
        if end is None:
            errors["period_end"] = "Indicare fino a quando si ripetono le lezioni"
        elif end < start:
            errors["period_end"] = "La fine deve seguire l'inizio"
        if fixed is not None:
            errors["fixed_time"] = "L'orario fisso vale solo per una lezione singola"
    else:
        if fixed is not None:
            errors["fixed_time"] = "L'orario fisso vale solo per una lezione singola"
        if end is None:
            errors["period_end"] = "Indicare la fine del periodo"
        elif end < start:
            errors["period_end"] = "La fine deve seguire l'inizio"
    if errors:
        raise serializers.ValidationError(errors)
    ids = list(dict.fromkeys(data.get("preferred_tutor_ids") or []))
    choice = data.get("tutor_choice") or "ANY"
    if kind == "SERIES":
        # Ricorrente: sempre lo stesso tutor. La famiglia può lasciarlo scegliere
        # al centro, che lo assegna all'approvazione.
        if len(ids) > 1:
            raise serializers.ValidationError(
                {"preferred_tutor_ids": "Una richiesta ricorrente ha un solo tutor"}
            )
        if center and not ids:
            raise serializers.ValidationError(
                {"preferred_tutor_ids": "Scegliere il tutor delle lezioni ricorrenti"}
            )
        choice = "REQUIRED" if ids else "ANY"
    data["tutor_choice"] = choice
    data["preferred_tutor_ids"] = ids if choice != "ANY" else []
    data["kind"] = kind
    check_tutors(data)
    return data


def check_tutors(data):
    choice = data.get("tutor_choice", "ANY")
    ids = data.get("preferred_tutor_ids") or []
    if choice != "ANY" and not ids:
        raise serializers.ValidationError(
            {"preferred_tutor_ids": "Indicare almeno un tutor"}
        )
    if ids and Tutor.objects.filter(id__in=ids, active=True).count() != len(set(ids)):
        raise serializers.ValidationError(
            {"preferred_tutor_ids": "Tutor inesistente o non attivo"}
        )


def is_guardian(user):
    return "GUARDIAN" in active_roles(user)


class RequestsView(viewsets.ModelViewSet):
    serializer_class = RequestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        from django.db.models import Q

        scope = visible_students(self.request.user)
        query = (
            TeachingRequest.objects.all()
            if is_center(self.request.user)
            else TeachingRequest.objects.filter(
                Q(student__in=scope) | Q(participants__student__in=scope)
            )
        )
        status = self.request.query_params.get("status")
        if status:
            query = query.filter(status__in=status.split(","))
        return (
            query.select_related("subject", "student", "requested_by")
            .prefetch_related("participants__student", "preferred_tutors")
            .distinct()
            .order_by("id")
        )

    def create(self, request, *args, **kwargs):
        center = is_center(request.user)
        if not center and not is_guardian(request.user):
            raise PermissionDenied()
        body = RequestInput(data=request.data, context={"center": center})
        body.is_valid(raise_exception=True)
        data = body.validated_data
        ids = list(dict.fromkeys(data.get("participant_ids") or []))
        members, label = [], ""
        if len(ids) >= 2:
            # Lezione di gruppo: la crea il centro, con studenti attivi.
            if not center:
                raise PermissionDenied("Le lezioni di gruppo sono create dal centro")
            members = list(Student.objects.filter(pk__in=ids, active=True).order_by("display_name"))
            if len(members) != len(ids):
                raise serializers.ValidationError(
                    {"participant_ids": "Studente inesistente o non attivo"}
                )
            student = members[0]
            label = (data.get("group_label") or "").strip() or (
                "Gruppo: " + ", ".join(m.display_name for m in members)
            )[:100]
        else:
            sid = data.get("student") or (ids[0] if ids else None)
            if not sid:
                raise serializers.ValidationError({"student": "Indicare lo studente"})
            student = visible_students(request.user).filter(pk=sid, active=True).first()
            if not student:
                raise PermissionDenied()
        subject = Subject.objects.filter(pk=data["subject"]).first()
        if not subject:
            raise serializers.ValidationError({"subject": "Materia inesistente"})
        if not subject.active:
            raise serializers.ValidationError(
                {"subject": "Materia archiviata: riattivarla dalla pagina Materie"}
            )
        with transaction.atomic():
            req = TeachingRequest(
                student=student,
                subject=subject,
                kind=data["kind"],
                mode=data["mode"],
                duration_minutes=data["duration_minutes"],
                sessions_per_week=data["sessions_per_week"],
                fixed_time=data.get("fixed_time"),
                period_start=data["period_start"],
                period_end=data["period_end"],
                # Le famiglie non scelgono priorità e obbligatorietà: le decide il centro.
                priority=data.get("priority", "P1") if center else "P1",
                mandatory=data.get("mandatory", False) if center else False,
                tutor_choice=data.get("tutor_choice", "ANY"),
                notes=data.get("notes", ""),
                status="APPROVED" if center else "PENDING",
                origin="CENTER" if center else "GUARDIAN",
                requested_by=request.user,
                reviewed_at=timezone.now() if center else None,
                group_label=label,
            )
            req.save()
            for m in members:
                RequestParticipant.objects.create(request=req, student=m)
            set_tutors(req, data.get("preferred_tutor_ids") or [])
        # v0.9.9: richiesta del centro già approvata → il motore colloca subito le lezioni
        if req.status == "APPROVED":
            request_review.auto_run(req, request.user)
        return Response(self.serialize(req), status=201)

    def partial_update(self, request, *args, **kwargs):
        req = self.get_object()
        if not is_center(request.user):
            raise PermissionDenied()
        if req.curriculum_block_id:
            return Response(
                {
                    "code": "DERIVED_REQUEST",
                    "message": "Richiesta derivata da un percorso: modificarla dal percorso",
                },
                status=409,
            )
        unknown = set(request.data) - EDITABLE_BY_CENTER
        if unknown:
            raise serializers.ValidationError(
                {"non_field_errors": [f"Campi non modificabili: {sorted(unknown)}"]}
            )
        body = RequestPatch(data=request.data, context={"instance": req})
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        tutors = data.pop("preferred_tutor_ids", None)
        with transaction.atomic():
            for key, value in data.items():
                setattr(req, key, value)
            req.save()
            if tutors is not None:
                set_tutors(req, tutors)
        # v0.9.9: vincoli cambiati → nuova verifica delle lezioni
        if req.status == "APPROVED":
            request_review.auto_run(req, request.user)
        return Response(self.serialize(req))

    def review(self, request, status):
        req = self.get_object()
        if not is_center(request.user):
            raise PermissionDenied()
        if req.status not in ("PENDING", "APPROVED", "REJECTED") or (
            req.status == status
        ):
            return Response(
                {"code": "INVALID_STATE", "message": "Stato non modificabile"},
                status=409,
            )
        tutor_id = request.data.get("tutor_id") if status == "APPROVED" else None
        tutor = None
        if tutor_id:
            tutor = Tutor.objects.filter(pk=tutor_id, active=True).first()
            if not tutor:
                raise serializers.ValidationError({"tutor_id": "Tutor inesistente o non attivo"})
        if (
            status == "APPROVED"
            and req.kind == "SERIES"
            and not tutor
            and not (req.tutor_choice == "REQUIRED" and req.preferred_tutors.exists())
        ):
            return Response(
                {
                    "code": "TUTOR_REQUIRED",
                    "message": "Per approvare una richiesta ricorrente scegliere il tutor che la seguirà",
                },
                status=400,
            )
        with transaction.atomic():
            req.status = status
            req.review_note = str(request.data.get("note", ""))[:300]
            req.reviewed_at = timezone.now()
            if tutor:
                req.tutor_choice = "REQUIRED"
            req.save()
            if tutor:
                set_tutors(req, [tutor.id])
        # v0.9.9: approvata → ricalcolo automatico del motore e verifica;
        # rifiutata → le lezioni proposte si liberano.
        if status == "APPROVED":
            request_review.auto_run(req, request.user)
        else:
            request_review.cancel(req)
        return Response(self.serialize(req))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.review(request, "APPROVED")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.review(request, "REJECTED")

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        req = self.get_object()
        own = req.requested_by_id == request.user.id and req.status == "PENDING"
        if not (own or (is_center(request.user) and not req.curriculum_block_id)):
            raise PermissionDenied()
        req.status = "WITHDRAWN"
        req.reviewed_at = timezone.now()
        req.save()
        request_review.cancel(req)
        return Response(self.serialize(req))

    @action(detail=False, methods=["get"])
    def options(self, request):
        """Catalogo per il modulo di richiesta: materie insegnate e tutor
        competenti (solo nome), senza esporre dati personali dei tutor."""
        center = is_center(request.user)
        if not center and not is_guardian(request.user):
            raise PermissionDenied()
        today = date.today()
        skills = (
            TutorSkill.objects.filter(
                approved=True,
                valid_until__gte=today,
                tutor__active=True,
                subject__active=True,
            )
            .select_related("tutor", "subject")
            .order_by("subject__name", "tutor__display_name")
        )
        subjects = {}
        for s in skills:
            row = subjects.setdefault(
                str(s.subject_id),
                {"id": str(s.subject_id), "name": s.subject.name, "tutors": {}},
            )
            tutor = row["tutors"].setdefault(
                str(s.tutor_id),
                {
                    "id": str(s.tutor_id),
                    "display_name": s.tutor.display_name,
                    "modes": set(),
                    "levels": set(),
                },
            )
            tutor["modes"].add(s.mode)
            tutor["levels"].add(s.level)
        if center:
            for subject in Subject.objects.filter(active=True).order_by("name"):
                subjects.setdefault(
                    str(subject.id),
                    {"id": str(subject.id), "name": subject.name, "tutors": {}},
                )
        out = []
        for row in sorted(subjects.values(), key=lambda r: r["name"]):
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "tutors": [
                        {
                            "id": t["id"],
                            "display_name": t["display_name"],
                            "modes": sorted(t["modes"]),
                            # I livelli servono solo al centro per capire la competenza.
                            **({"levels": sorted(t["levels"])} if center else {}),
                        }
                        for t in row["tutors"].values()
                    ],
                }
            )
        return Response({"subjects": out})

    def serialize(self, req):
        req = self.get_queryset().get(pk=req.pk)
        return RequestSerializer(req, context={"request": self.request}).data


def set_tutors(req, ids):
    # La revisione degli input è aggiornata dal segnale m2m (scheduling.signals).
    req.preferred_tutors.set(Tutor.objects.filter(id__in=ids))
