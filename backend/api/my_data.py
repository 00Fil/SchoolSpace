"""P5 · «I miei dati» nei portali: informativa, consenso dello studente, export personale
e richieste degli interessati (artt. 15-21 GDPR).

Autorizzazione: l'account agisce su sé stesso (ACCOUNT); il genitore anche sugli studenti
che vede con delega attiva (STUDENT). Lo studente minorenne vede ed esporta solo i propri
dati di account (D07: sola visione), non apre richieste sui dati dello studente.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.identity.policies import active_roles, is_center, visible_students
from apps.privacy import exports, requests as rights
from apps.privacy.models import NoticeAcknowledgement, PrivacyRequest, ProtectedExport

from ._privacy_common import BadPayload, handle_errors, payload, text
from .privacy import export_json, request_json

NOTICE_VERSION = getattr(settings, "PRIVACY_NOTICE_VERSION", "2026-10")


def notice_acknowledged(user):
    """C04: True se l'account ha preso visione della versione corrente dell'informativa."""
    return NoticeAcknowledgement.objects.filter(account=user, version=NOTICE_VERSION).exists()


@api_view(["POST"])
@handle_errors
def my_notice_ack(request):
    user = request.user
    if is_center(user):
        raise PermissionDenied()
    data = payload(request, ["version"])
    if data["version"] != NOTICE_VERSION:
        return Response({"code": "NOTICE_OUTDATED", "current": NOTICE_VERSION}, status=409)
    ack, _ = NoticeAcknowledgement.objects.get_or_create(account=user, version=NOTICE_VERSION)
    return Response({"version": ack.version, "acknowledged_at": ack.acknowledged_at.isoformat()})


class ExportThrottle(UserRateThrottle):
    rate = "5/hour"


def subjects_of(user):
    rows = [{"type": "ACCOUNT", "id": str(user.pk), "label": "I miei dati di accesso"}]
    if "GUARDIAN" in active_roles(user):
        for s in visible_students(user).exclude(account=user):
            rows.append({"type": "STUDENT", "id": str(s.pk), "label": s.display_name})
    return rows


def resolve(user, data):
    subject_type = text(data, "subject_type", 8)
    subject_id = text(data, "subject_id", 40)
    allowed = {(r["type"], r["id"]) for r in subjects_of(user)}
    if (subject_type, subject_id) not in allowed:
        # Nessuna enumerazione: stesso esito per inesistente e non visibile.
        raise PermissionDenied()
    return subject_type, subject_id


def role_of(user):
    roles = active_roles(user)
    for r in ("GUARDIAN", "TUTOR", "STUDENT"):
        if r in roles:
            return r
    return "ACCOUNT"


def consent_of(user):
    if "STUDENT" not in active_roles(user):
        return None
    from apps.education.models import Student

    student = Student.objects.filter(account=user).first()
    policy = getattr(student, "access_policy", None) if student else None
    pending = []
    if student and policy and policy.adult_confirmed:
        from apps.education.models import GuardianLink

        links = GuardianLink.objects.filter(
            student=student, revoked_at__isnull=True, detail__reconfirmation="PENDING"
        ).select_related("account", "detail")
        for link in links:
            acc = link.account
            pending.append({
                "link_id": str(link.pk),
                "guardian": getattr(acc, "display_name", None) or getattr(acc, "email", "") or "Genitore",
                "due_at": link.detail.reconfirmation_due_at.isoformat() if link.detail.reconfirmation_due_at else None,
            })
    return {
        "reconfirmations": pending,
        "adult_confirmed": bool(policy and policy.adult_confirmed),
        "guardian_access": policy.guardian_access if policy else "DEFAULT",
        "consent_at": policy.student_consent_at.isoformat() if policy and policy.student_consent_at else None,
    }


@api_view(["GET"])
@handle_errors
def my_data(request):
    user = request.user
    if is_center(user):
        raise PermissionDenied()  # il centro usa l'area privacy
    subjects = subjects_of(user)
    ids = [r["id"] for r in subjects]
    reqs = PrivacyRequest.objects.filter(subject_id__in=ids).order_by("-received_at")[:20]
    exps = ProtectedExport.objects.filter(audience=user).order_by("-created_at")[:10]
    return Response({
        "notice_version": NOTICE_VERSION,
        "notice_acknowledged": notice_acknowledged(user),
        "role": role_of(user),
        "subjects": subjects,
        "consent": consent_of(user),
        "requests": [{k: v for k, v in request_json(r).items() if k not in ("subject_pseudonym",)} for r in reqs],
        "exports": [export_json(e) for e in exps],
        "self_service_kinds": list(rights.SELF_SERVICE_KINDS),
    })


@api_view(["POST"])
@throttle_classes([ExportThrottle])
@handle_errors
def my_export(request):
    """Export personale (artt. 15 e 20): file JSON scaricabile una volta, con scadenza."""
    user = request.user
    if is_center(user):
        raise PermissionDenied()
    data = payload(request, ["subject_type", "subject_id"])
    subject_type, subject_id = resolve(user, data)
    recent = ProtectedExport.objects.filter(
        audience=user,
        purpose="interessato",
        created_at__gte=timezone.now() - timedelta(hours=24),
        downloaded_at__isnull=True,
        revoked_at__isnull=True,
    )
    if recent.exists():
        return Response({"code": "EXPORT_RECENT", "message": "Hai già un export da scaricare"}, status=409)
    from apps.privacy.subjects import collect, render

    req = rights.open_self_request(
        user, kind="ACCESS", subject_type=subject_type, subject_id=subject_id, requester_role=role_of(user)
    ) if not PrivacyRequest.objects.filter(
        kind="ACCESS", subject_type=subject_type, subject_id=subject_id, status__in=rights.OPEN
    ).exists() else None
    content = render(
        collect(subject_type, subject_id), "json",
        subject_type=subject_type, subject_id=subject_id, purpose="interessato",
    )
    export, token = exports.create_export(
        actor=user, audience=user, content=content, fmt="json",
        filename="miei-dati.json", purpose="interessato", privacy_request=req,
    )
    return Response(export_json(export, token), status=201)


@api_view(["POST"])
@handle_errors
def my_request(request):
    """Rettifica, cancellazione, limitazione, opposizione: le evade il centro entro un mese."""
    user = request.user
    if is_center(user):
        raise PermissionDenied()
    data = payload(request, ["kind", "subject_type", "subject_id"])
    kind = text(data, "kind", 14)
    if kind not in rights.SELF_SERVICE_KINDS:
        raise BadPayload("Tipo di richiesta non ammesso")
    subject_type, subject_id = resolve(user, data)
    req = rights.open_self_request(
        user, kind=kind, subject_type=subject_type, subject_id=subject_id, requester_role=role_of(user)
    )
    return Response(request_json(req), status=201)


def urlpatterns():
    from django.urls import path

    return [
        path("api/v1/me/data", my_data),
        path("api/v1/me/data/export", my_export),
        path("api/v1/me/data/requests", my_request),
        path("api/v1/me/notice/acknowledge", my_notice_ack),
    ]
