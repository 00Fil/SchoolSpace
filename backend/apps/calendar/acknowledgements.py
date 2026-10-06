"""P3 (DC-APPROVAZIONI): presa visione degli orari da parte del tutor.

Il motore propone, il centro pubblica. Ogni tutor coinvolto in una pubblicazione
riceve una presa visione: la conferma oppure propone modifiche. Le controproposte
tornano al centro, che decide: le accoglie (diventano richieste di modifica del
tutor), le gira alle famiglie (richieste con conferma dei genitori) o le respinge
(il tutor deve rivedere gli orari). Nessuna lezione viene spostata qui: gli
spostamenti passano dalla coda delle richieste (P4).
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.education.models import Tutor
from apps.education.path_services import Conflict, DomainError
from apps.identity.policies import active_roles, is_center

from .commands import audit
from .models import (
    ChangeRequest,
    LessonOccurrence,
    LessonParticipant,
    Publication,
    TutorAcknowledgement,
)

MAX_ITEMS = 20


def own_tutor(user):
    if "TUTOR" not in active_roles(user):
        return None
    return Tutor.objects.filter(account=user).first()


def ensure_for_publication(publication):
    tutors = (
        LessonOccurrence.objects.filter(publication=publication)
        .values_list("tutor_id", flat=True)
        .distinct()
    )
    for tutor_id in tutors:
        TutorAcknowledgement.objects.get_or_create(
            publication=publication, tutor_id=tutor_id
        )


def ensure_missing(tutor=None):
    """Crea le prese visione mancanti (pubblicazioni precedenti a P3 comprese)."""
    pubs = Publication.objects.all()
    if tutor is not None:
        pubs = pubs.filter(lessonoccurrence__tutor=tutor).exclude(
            acknowledgements__tutor=tutor
        )
    else:
        pubs = pubs.filter(acknowledgements__isnull=True)
    for pub in pubs.distinct()[:50]:
        ensure_for_publication(pub)


def lessons_of(ack):
    rows = (
        LessonOccurrence.objects.filter(publication=ack.publication, tutor=ack.tutor)
        .select_related("subject")
        .order_by("start_at")
    )
    return list(rows)


def ack_json(ack, with_lessons=True):
    out = {
        "id": str(ack.pk),
        "publication": str(ack.publication_id),
        "published_at": ack.publication.created_at.isoformat(),
        "tutor": str(ack.tutor_id),
        "tutor_name": ack.tutor.display_name,
        "state": ack.state,
        "note": ack.note,
        "items": ack.items,
        "decision": ack.decision,
        "decision_note": ack.decision_note,
        "acknowledged_at": ack.acknowledged_at.isoformat() if ack.acknowledged_at else None,
        "decided_at": ack.decided_at.isoformat() if ack.decided_at else None,
        "version": ack.version,
    }
    if with_lessons:
        out["lessons"] = [
            {
                "id": str(l.pk),
                "start_at": l.start_at.isoformat(),
                "end_at": l.end_at.isoformat(),
                "subject": getattr(l.subject, "name", ""),
                "mode": l.mode,
            }
            for l in lessons_of(ack)
        ]
    return out


def _locked(ack_id):
    ack = (
        TutorAcknowledgement.objects.select_for_update()
        .filter(pk=ack_id)
        .first()
    )
    if ack is None:
        raise DomainError("NOT_FOUND", "Presa visione inesistente")
    return ack


def _snapshot(ack):
    return {"state": ack.state, "decision": ack.decision, "version": ack.version}


def _own(user, ack):
    tutor = own_tutor(user)
    if tutor is None or tutor.pk != ack.tutor_id:
        # Non rivela l'esistenza di prese visione altrui (BOLA).
        raise DomainError("NOT_FOUND", "Presa visione inesistente")


def _version(ack, expected):
    if ack.version != expected:
        raise Conflict("VERSION_CONFLICT", "Oggetto cambiato: ricaricare")


@transaction.atomic
def acknowledge(user, ack_id, expected_version):
    ack = _locked(ack_id)
    _own(user, ack)
    _version(ack, expected_version)
    if ack.state != "PENDING":
        raise DomainError("ACK_STATE_INVALID", f"Presa visione in stato {ack.state}")
    before = _snapshot(ack)
    ack.state, ack.acknowledged_at = "ACKNOWLEDGED", timezone.now()
    ack.version += 1
    ack.save()
    audit(user, "ack:acknowledge", "Presa visione degli orari", obj=ack, before=before, after=_snapshot(ack))
    return ack


@transaction.atomic
def counter(user, ack_id, expected_version, note, items):
    ack = _locked(ack_id)
    _own(user, ack)
    _version(ack, expected_version)
    if ack.state not in ("PENDING", "ACKNOWLEDGED"):
        raise DomainError("ACK_STATE_INVALID", f"Presa visione in stato {ack.state}")
    if not items or len(items) > MAX_ITEMS:
        raise DomainError("INVALID_ITEMS", f"Indica da 1 a {MAX_ITEMS} lezioni")
    own = {str(l.pk) for l in lessons_of(ack)}
    clean = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"lesson_id", "proposal"}:
            raise DomainError("INVALID_ITEMS", "Voce non valida")
        lesson_id, proposal = str(item.get("lesson_id", "")), item.get("proposal")
        if lesson_id not in own:
            raise DomainError("INVALID_ITEMS", "Lezione non inclusa in questa pubblicazione")
        if not isinstance(proposal, str) or not proposal.strip() or len(proposal) > 200:
            raise DomainError("INVALID_ITEMS", "Per ogni lezione scrivi la modifica (max 200)")
        clean.append({"lesson_id": lesson_id, "proposal": proposal.strip()})
    before = _snapshot(ack)
    ack.state, ack.note, ack.items = "COUNTER", note, clean
    ack.decision, ack.decision_note = "", ""
    ack.version += 1
    ack.save()
    audit(user, "ack:counter", note or "Controproposta del tutor", obj=ack, before=before, after={**_snapshot(ack), "items": clean})
    return ack


@transaction.atomic
def decide(user, ack_id, expected_version, decision, note):
    if not is_center(user):
        raise DomainError("FORBIDDEN", "Decide solo il centro")
    ack = _locked(ack_id)
    _version(ack, expected_version)
    if ack.state != "COUNTER":
        raise DomainError("ACK_STATE_INVALID", f"Presa visione in stato {ack.state}")
    if decision not in TutorAcknowledgement.DECISIONS:
        raise DomainError("INVALID_DECISION", "Decisione non valida")
    note = (note or "").strip() or {"ACCEPTED": "Accolta dal centro", "REJECTED": "Respinta dal centro"}.get(decision, "Inoltrata alle famiglie")
    before = _snapshot(ack)
    created = []
    if decision in ("ACCEPTED", "ASK_GUARDIANS"):
        account = ack.tutor.account or user
        for item in ack.items:
            lesson = LessonOccurrence.objects.get(pk=item["lesson_id"])
            first = LessonParticipant.objects.filter(lesson=lesson).first()
            cr = ChangeRequest.objects.create(
                lesson=lesson,
                kind="RESCHEDULE",
                origin="TUTOR",
                requested_by=account,
                student=first.student if first else None,
                reason=item["proposal"][:200],
                proposal={
                    "note": item["proposal"],
                    "acknowledgement": str(ack.pk),
                    "center_accepted": True,
                    # DC-CONFERMA-GENITORI: sempre, salvo impostazione contraria.
                    "guardians_confirmation_required": decision == "ASK_GUARDIANS"
                    or bool(getattr(settings, "TUTOR_CHANGES_REQUIRE_GUARDIANS", True)),
                    # Il proponente è il tutor: la sua conferma è implicita.
                    "tutor_confirmed": True,
                },
            )
            created.append(str(cr.pk))
    ack.decision, ack.decision_note = decision, note
    ack.decided_by, ack.decided_at = user, timezone.now()
    # Respinta: il tutor rivede gli orari pubblicati e conferma di nuovo.
    ack.state = "PENDING" if decision == "REJECTED" else "RESOLVED"
    ack.version += 1
    ack.save()
    audit(user, "ack:decide", note, obj=ack, before=before, after={**_snapshot(ack), "change_requests": created})
    return ack, created
