"""Exploratory curriculum service: no solver, published calendar or lesson credit."""

import hashlib
import json
from django.db import transaction
from django.db.models import F
from apps.scheduling.revision import lock_revision
from rest_framework.exceptions import APIException
from apps.identity.models import Account
from apps.governance.models import CommandReceipt, PathAuditEvent
from .models import (
    LearningPath,
    PathEnrollment,
    CurriculumBlock,
    TeachingRequest,
    RequestParticipant,
)


class DomainError(APIException):
    status_code = 422
    default_code = "DOMAIN_VIOLATION"

    def __init__(self, code, message, **extra):
        super().__init__({"code": code, "message": message, **extra})


class Conflict(DomainError):
    status_code = 409


def assert_period(path, first, last):
    if first > last or first < path.period_start or last > path.period_end:
        raise DomainError(
            "PERIOD_OUTSIDE_PATH", "Il periodo deve essere contenuto nel percorso"
        )


def participant_ids(block):
    if block.student_id:
        ids = [block.student_id]
    else:
        group = block.group
        if (
            group.path_id != block.path_id
            or group.subject_id != block.subject_id
            or not group.approved
        ):
            raise DomainError(
                "GROUP_NOT_APPROVED",
                "Gruppo approvato, materia e percorso devono corrispondere",
            )
        memberships = list(group.memberships.order_by("student_id"))
        overlapping = [
            m
            for m in memberships
            if m.period_start <= block.period_end and m.period_end >= block.period_start
        ]
        # Segmentation across a membership change is required, not guessed.
        if any(
            m.period_start > block.period_start or m.period_end < block.period_end
            for m in overlapping
        ):
            raise DomainError(
                "MEMBERSHIP_SEGMENT_REQUIRED",
                "Suddividere il blocco sulle date di cambio dei membri",
            )
        ids = [m.student_id for m in overlapping]
        if len(ids) < 2:
            raise DomainError(
                "GROUP_TOO_SMALL", "Un gruppo deve contenere almeno due partecipanti"
            )
        if block.mode == "IN_PERSON" and len(ids) > 2:
            raise DomainError(
                "SPACE_CAPACITY",
                "Massimo due studenti in una sessione in presenza; nessuna suddivisione automatica",
            )
        if block.mode == "ONLINE" and (
            group.online_capacity is None or len(ids) > group.online_capacity
        ):
            raise DomainError(
                "ONLINE_CAPACITY",
                "Capienza online esplicita necessaria e non superabile",
            )
    enrolled = set(
        PathEnrollment.objects.filter(
            path_id=block.path_id,
            active=True,
            student__active=True,
            student_id__in=ids,
            period_start__lte=block.period_start,
            period_end__gte=block.period_end,
        ).values_list("student_id", flat=True)
    )
    if set(ids) != enrolled:
        raise DomainError(
            "ENROLLMENT_NOT_COVERED",
            "Tutti i partecipanti devono essere iscritti per l'intero blocco",
        )
    return sorted(ids, key=str)


def validate_blocks(path, require_complete=False):
    blocks = list(
        path.blocks.select_related("group", "subject", "student").order_by("id")
    )
    required = set(path.required_subjects.values_list("id", flat=True))
    if not required:
        raise DomainError(
            "REQUIRED_SUBJECTS_MISSING",
            "Dichiarare tutte le materie previste per questo anno e livello",
        )
    coverage = {}
    compiled = []
    for block in blocks:
        assert_period(path, block.period_start, block.period_end)
        if block.subject_id not in required:
            raise DomainError(
                "SUBJECT_OUTSIDE_CURRICULUM",
                "La materia non appartiene al programma dichiarato",
            )
        if (
            block.duration_minutes not in (60, 90, 120)
            or block.sessions_per_week < 1
            or block.minutes_per_week
            != block.duration_minutes * block.sessions_per_week
        ):
            raise DomainError(
                "MINUTES_MISMATCH",
                "Minuti settimanali e durata per numero sessioni devono coincidere",
            )
        ids = participant_ids(block)
        for student_id in ids:
            key = (student_id, block.subject_id)
            intervals = coverage.setdefault(key, [])
            if any(
                first <= block.period_end and last >= block.period_start
                for first, last in intervals
            ):
                raise DomainError(
                    "DUPLICATE_CURRICULUM_COVERAGE",
                    "Stesso studente e materia in blocchi sovrapposti: rischio di doppio conteggio",
                )
            intervals.append((block.period_start, block.period_end))
        compiled.append((block, ids))
    if require_complete:
        enrollments = list(path.enrollments.filter(active=True, student__active=True))
        if not enrollments:
            raise DomainError(
                "EMPTY_COHORT", "Iscrivere almeno uno studente al percorso"
            )
        for enrollment in enrollments:
            for subject_id in required:
                spans = sorted(coverage.get((enrollment.student_id, subject_id), []))
                cursor = enrollment.period_start
                from datetime import timedelta

                for first, last in spans:
                    if last < cursor:
                        continue
                    if first > cursor:
                        break
                    cursor = max(cursor, last + timedelta(days=1))
                if cursor <= enrollment.period_end:
                    raise DomainError(
                        "INCOMPLETE_PROGRAM",
                        "Programma incompleto: una materia non copre tutto il periodo di un iscritto; verificare il riepilogo",
                    )
    return compiled


def fingerprint(block, ids):
    value = {
        "block_id": str(block.id),
        "block_version": block.version,
        "subject": str(block.subject_id),
        "student": str(block.student_id) if block.student_id else None,
        "group": str(block.group_id) if block.group_id else None,
        "participants": [str(i) for i in ids],
        "period_start": str(block.period_start),
        "period_end": str(block.period_end),
        "duration": block.duration_minutes,
        "sessions": block.sessions_per_week,
        "minutes": block.minutes_per_week,
        "mode": block.mode,
        "priority": block.priority,
        "mandatory": block.mandatory,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def touch_path(path, actor, operation, details):
    LearningPath.objects.filter(pk=path.pk).update(version=F("version") + 1)
    path.refresh_from_db()
    PathAuditEvent.objects.create(
        path=path, actor=actor, operation=operation, details=details
    )


@transaction.atomic
def derive_requests(path_id, actor, expected_version, key):
    if not key or len(key) > 255 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise DomainError(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Indicare Idempotency-Key non vuota, massimo 255 caratteri ASCII stampabili senza spazi",
        )
    # Lock actor first to serialize this actor's keys even across different paths.
    lock_revision()
    Account.objects.select_for_update().get(pk=actor.pk)
    body_hash = hashlib.sha256(
        json.dumps(
            {"path_id": str(path_id), "expected_version": expected_version},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    receipt = CommandReceipt.objects.filter(
        actor=actor, operation="derive_curriculum", key=key
    ).first()
    if receipt:
        if receipt.body_hash != body_hash:
            raise Conflict("IDEMPOTENCY_CONFLICT", "Stessa chiave con comando diverso")
        return receipt.response
    path = LearningPath.objects.select_for_update().get(pk=path_id)
    if path.version != expected_version:
        raise Conflict(
            "VERSION_CONFLICT",
            "Il percorso è cambiato: ricaricare prima di derivare le richieste",
        )
    compiled = validate_blocks(path, require_complete=True)
    created = 0
    request_ids = []
    for block, ids in compiled:
        source = fingerprint(block, ids)
        defaults = {
            "student_id": block.student_id,
            "group_id": block.group_id,
            "subject_id": block.subject_id,
            "duration_minutes": block.duration_minutes,
            "sessions_per_week": block.sessions_per_week,
            "priority": block.priority,
            "mandatory": block.mandatory,
            "mode": block.mode,
            "period_start": block.period_start,
            "period_end": block.period_end,
            "source_fingerprint": source,
        }
        request, is_new = TeachingRequest.objects.get_or_create(
            curriculum_block=block, defaults=defaults
        )
        if not is_new:
            matches = all(getattr(request, k) == v for k, v in defaults.items())
            stored = set(request.participants.values_list("student_id", flat=True))
            if not matches or stored != set(ids):
                raise Conflict(
                    "DERIVED_REQUEST_CHANGED",
                    "Richiesta derivata alterata: occorre un flusso di revisione esplicito",
                )
        else:
            RequestParticipant.objects.bulk_create(
                [RequestParticipant(request=request, student_id=i) for i in ids]
            )
            created += 1
        request_ids.append(str(request.id))
    if created:
        touch_path(path, actor, "derive_curriculum", {"created_requests": created})
    result = {
        "path_id": str(path.id),
        "created": created,
        "request_ids": request_ids,
        "version": path.version,
        "calendar_changed": False,
    }
    CommandReceipt.objects.create(
        actor=actor,
        operation="derive_curriculum",
        key=key,
        body_hash=body_hash,
        response=result,
    )
    return result
