"""API privacy: matrice di retention, job con ricevuta, richieste degli interessati,
export protetti, import iniziale e consultazione dell'audit (GAP-H04/H05/H06/H07)."""

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, parser_classes, throttle_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.governance.models import AuditEvent
from apps.identity.policies import is_center
from apps.privacy import exports, importer, majority, requests as rights, retention
from apps.privacy.models import (
    ImportBatch,
    PrivacyRequest,
    ProtectedExport,
    RetentionPolicy,
    RetentionRun,
)

from ._privacy_common import (
    BadPayload,
    boolean,
    center_only,
    handle_errors,
    integer,
    iso,
    paginate,
    payload,
    text,
)


def policy_json(p):
    return {
        "id": str(p.pk),
        "category": p.category,
        "label": p.label,
        "purpose": p.purpose,
        "legal_basis": p.legal_basis,
        "duration_days": p.duration_days,
        "action": p.action,
        "backup_note": p.backup_note,
        "source": p.source,
        "status": p.status,
        "approved_at": iso(p.approved_at),
        "approval_reference": p.approval_reference,
        "version": p.version,
    }


def run_json(r):
    return {
        "id": str(r.pk),
        "started_at": iso(r.started_at),
        "finished_at": iso(r.finished_at),
        "dry_run": r.dry_run,
        "reference_time": iso(r.reference_time),
        "results": r.results,
        "receipt_hash": r.receipt_hash,
    }


def request_json(r):
    return {
        "id": str(r.pk),
        "kind": r.kind,
        "subject_type": r.subject_type,
        "subject_id": str(r.subject_id),
        "subject_pseudonym": r.subject_pseudonym,
        "channel": r.channel,
        "requester_role": r.requester_role,
        "received_at": iso(r.received_at),
        "due_at": iso(r.due_at),
        "status": r.status,
        "identity_verified_at": iso(r.identity_verified_at),
        "extension_reason": r.extension_reason,
        "outcome": r.outcome,
        "motivation": r.motivation,
        "closed_at": iso(r.closed_at),
        "version": r.version,
    }


def export_json(e, token=None):
    data = {
        "id": str(e.pk),
        "created_at": iso(e.created_at),
        "audience": str(e.audience_id),
        "purpose": e.purpose,
        "format": e.format,
        "filename": e.filename,
        "size_bytes": e.size_bytes,
        "sha256": e.sha256,
        "expires_at": iso(e.expires_at),
        "downloaded_at": iso(e.downloaded_at),
        "revoked_at": iso(e.revoked_at),
        "available": not (e.downloaded_at or e.revoked_at or e.purged_at),
    }
    if token:
        data["token"] = token  # una sola volta, da consegnare all'audience
    return data


def batch_json(b):
    return {
        "id": str(b.pk),
        "created_at": iso(b.created_at),
        "template_version": b.template_version,
        "file_sha256": b.file_sha256,
        "dry_run": b.dry_run,
        "status": b.status,
        "rows": b.rows,
        "summary": b.summary,
        "errors": b.errors,
    }


def audit_json(e):
    return {
        "id": str(e.pk),
        "occurred_at": iso(e.occurred_at),
        "category": e.category,
        "operation": e.operation,
        "actor": str(e.actor_id) if e.actor_id else None,
        "object_type": e.object_type,
        "object_id": e.object_id,
        "object_version": e.object_version,
        "purpose": e.purpose,
        "reason": e.reason,
        "command": e.command,
        "correlation_id": str(e.correlation_id),
        "details": e.details,
    }


# --- Retention ---------------------------------------------------------------------


@api_view(["GET"])
@handle_errors
def policies(request):
    center_only(request)
    return paginate(request, RetentionPolicy.objects.all(), policy_json)


@api_view(["PATCH"])
@handle_errors
def policy_detail(request, pk):
    center_only(request)
    data = payload(request, ["expected_version", "reason"], sorted(retention.EDITABLE))
    changes = {k: v for k, v in data.items() if k in retention.EDITABLE}
    if "duration_days" in changes and changes["duration_days"] is not None:
        integer(changes, "duration_days")
        if changes["duration_days"] < 0:
            raise BadPayload("duration_days >= 0")
    if "action" in changes and changes["action"] not in RetentionPolicy.Action.values:
        raise BadPayload("action non valida")
    for key in ("purpose", "legal_basis", "backup_note"):
        if key in changes:
            changes[key] = text(changes, key, 200, required=False)
    policy = retention.update_policy(
        request.user,
        get_object_or_404(RetentionPolicy, pk=pk),
        expected_version=integer(data, "expected_version"),
        changes=changes,
        reason=data["reason"],
    )
    return Response(policy_json(policy))


@api_view(["POST"])
@handle_errors
def policy_approve(request, pk):
    center_only(request)
    data = payload(request, ["expected_version", "reference", "reason"])
    policy = retention.approve_policy(
        request.user,
        get_object_or_404(RetentionPolicy, pk=pk),
        expected_version=integer(data, "expected_version"),
        reference=data["reference"],
        reason=data["reason"],
    )
    return Response(policy_json(policy))


@api_view(["GET", "POST"])
@handle_errors
def runs(request):
    center_only(request)
    if request.method == "GET":
        return paginate(request, RetentionRun.objects.all(), run_json)
    data = payload(request, [], ["dry_run", "categories"])
    categories = data.get("categories")
    if categories is not None and (
        not isinstance(categories, list)
        or not all(isinstance(c, str) for c in categories)
    ):
        raise BadPayload("categories: elenco di stringhe")
    run = retention.run_retention(
        actor=request.user,
        dry_run=boolean(data, "dry_run", default=True),
        categories=categories,
    )
    return Response(run_json(run), status=201)


# --- Richieste degli interessati -------------------------------------------------


@api_view(["GET", "POST"])
@handle_errors
def privacy_requests(request):
    center_only(request)
    if request.method == "GET":
        query = PrivacyRequest.objects.all()
        if request.query_params.get("status") == "open":
            query = query.filter(status__in=rights.OPEN)
        elif request.query_params.get("status") == "overdue":
            query = rights.overdue()
        return paginate(request, query, request_json)
    data = payload(
        request, ["kind", "subject_type", "subject_id", "channel", "requester_role"]
    )
    req = rights.open_request(
        request.user,
        kind=data["kind"],
        subject_type=data["subject_type"],
        subject_id=data["subject_id"],
        channel=text(data, "channel", 60),
        requester_role=text(data, "requester_role", 60),
    )
    return Response(request_json(req), status=201)


@api_view(["GET"])
@handle_errors
def privacy_request_detail(request, pk):
    center_only(request)
    return Response(request_json(get_object_or_404(PrivacyRequest, pk=pk)))


@api_view(["POST"])
@handle_errors
def privacy_request_action(request, pk, action):
    center_only(request)
    req = get_object_or_404(PrivacyRequest, pk=pk)
    user = request.user
    if action == "verify-identity":
        data = payload(request, ["method"])
        req = rights.verify_identity(user, req, method=data["method"])
    elif action == "extend":
        req = rights.extend(user, req, reason=payload(request, ["reason"])["reason"])
    elif action == "export":
        data = payload(request, ["audience"], ["format"])
        audience = get_object_or_404(
            get_user_model(), pk=data["audience"], is_active=True
        )
        export, token = rights.fulfil_export(
            user, req, audience=audience, fmt=data.get("format", "json")
        )
        return Response(
            {
                "request": request_json(PrivacyRequest.objects.get(pk=req.pk)),
                "export": export_json(export, token),
            },
            status=201,
        )
    elif action == "rectify":
        data = payload(request, ["changes", "reason"])
        rights.fulfil_rectification(
            user, req, changes=data["changes"], reason=data["reason"]
        )
    elif action == "erase":
        data = payload(request, ["motivation"])
        rights.fulfil_erasure(user, req, motivation=data["motivation"])
    elif action == "close":
        data = payload(request, ["outcome", "motivation"])
        rights.close_manually(
            user, req, outcome=data["outcome"], motivation=data["motivation"]
        )
    elif action == "reject":
        rights.reject(
            user, req, motivation=payload(request, ["motivation"])["motivation"]
        )
    else:
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response(request_json(PrivacyRequest.objects.get(pk=req.pk)))


@api_view(["GET"])
@handle_errors
def privacy_request_audiences(request, pk):
    """P6 · Account a cui il centro può consegnare l'export: l'interessato stesso o, per uno
    studente, il suo account e i genitori con delega attiva."""
    center_only(request)
    from apps.education.models import GuardianLink, Student

    req = get_object_or_404(PrivacyRequest, pk=pk)
    users = []
    if req.subject_type == "ACCOUNT":
        users = list(get_user_model().objects.filter(pk=req.subject_id, is_active=True))
    else:
        student = Student.objects.filter(pk=req.subject_id).first()
        if student is not None:
            if student.account_id and student.account.is_active:
                users.append(student.account)
            for link in GuardianLink.objects.filter(student=student, revoked_at__isnull=True).select_related("account"):
                if link.account.is_active and link.account not in users:
                    users.append(link.account)
    return Response({"results": [
        {"id": str(u.pk), "label": (u.get_full_name() or u.username)
         + (" (studente)" if req.subject_type == "STUDENT" and u.pk == getattr(Student.objects.filter(pk=req.subject_id).first(), "account_id", None) else "")}
        for u in users
    ]})


# --- Export protetti ---------------------------------------------------------------


@api_view(["GET"])
@handle_errors
def export_list(request):
    query = ProtectedExport.objects.all()
    if not is_center(request.user):
        query = query.filter(audience=request.user)
    return paginate(request, query, export_json)


class DownloadThrottle(UserRateThrottle):
    rate = "20/minute"


@api_view(["POST"])
@throttle_classes([DownloadThrottle])
@handle_errors
def export_download(request, pk):
    """Token nel corpo della POST (mai nell'URL, che finirebbe nei log)."""
    data = payload(request, ["token"])
    export, content = exports.consume(pk, user=request.user, token=data["token"])
    mime = "application/json" if export.format == "json" else "text/csv"
    response = HttpResponse(content, content_type=mime + "; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{export.filename}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
@handle_errors
def export_revoke(request, pk):
    center_only(request)
    data = payload(request, ["reason"])
    export = get_object_or_404(ProtectedExport, pk=pk)
    exports.revoke_export(request.user, export, reason=data["reason"])
    return Response(export_json(ProtectedExport.objects.get(pk=pk)))


@api_view(["POST"])
@handle_errors
def operational_export(request):
    """Export operativo del centro (es. elenco famiglie) con le stesse protezioni."""
    center_only(request)
    data = payload(request, ["subject_type", "subject_id"], ["format", "audience"])
    from apps.privacy.subjects import collect, render

    fmt = data.get("format", "json")
    if fmt not in ("json", "csv"):
        raise BadPayload("format json o csv")
    if data["subject_type"] not in PrivacyRequest.SubjectType.values:
        raise BadPayload("subject_type STUDENT o ACCOUNT")
    audience = (
        get_object_or_404(get_user_model(), pk=data["audience"], is_active=True)
        if data.get("audience")
        else request.user
    )
    content = render(
        collect(data["subject_type"], data["subject_id"]),
        fmt,
        subject_type=data["subject_type"],
        subject_id=data["subject_id"],
        purpose="operativo",
    )
    export, token = exports.create_export(
        actor=request.user,
        audience=audience,
        content=content,
        fmt=fmt,
        filename=f"export-operativo.{fmt}",
        purpose="operativo",
    )
    return Response(export_json(export, token), status=201)


# --- Import iniziale ---------------------------------------------------------------


@api_view(["GET", "POST"])
@parser_classes([JSONParser, MultiPartParser])
@handle_errors
def imports(request):
    center_only(request)
    if request.method == "GET":
        return paginate(request, ImportBatch.objects.all(), batch_json)
    if request.content_type and request.content_type.startswith("multipart/"):
        upload = request.FILES.get("file")
        if upload is None or upload.size > 5 * 1024 * 1024:
            raise BadPayload("file CSV obbligatorio (max 5 MB)")
        content = upload.read()
        options = {k: request.data.get(k) for k in request.data if k != "file"}
        options = {
            k: (v.lower() == "true") if k != "template_version" else v
            for k, v in options.items()
        }
    else:
        data = payload(
            request,
            ["content"],
            ["template_version", "dry_run", "verify_links", "create_invites"],
        )
        content = text(data, "content", 5 * 1024 * 1024).encode()
        options = {k: v for k, v in data.items() if k != "content"}
    allowed = {"template_version", "dry_run", "verify_links", "create_invites"}
    if set(options) - allowed:
        raise BadPayload("opzioni ammesse: " + ", ".join(sorted(allowed)))
    batch = importer.run_import(
        request.user,
        content,
        template_version=str(options.get("template_version", "1")),
        dry_run=boolean(options, "dry_run", default=True),
        verify_links=boolean(options, "verify_links", default=False),
        create_invites=boolean(options, "create_invites", default=False),
    )
    status = 201 if batch.status in ("APPLIED", "DRY_RUN") else 422
    return Response(batch_json(batch), status=status)


@api_view(["GET"])
@handle_errors
def import_template(request, version):
    center_only(request)
    if version not in importer.TEMPLATES:
        return Response({"code": "UNKNOWN_TEMPLATE"}, status=404)
    response = HttpResponse(
        ",".join(importer.TEMPLATES[version]) + "\r\n",
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="famiglie-v{version}.csv"'
    return response


# --- Audit e job -------------------------------------------------------------------


@api_view(["GET"])
@handle_errors
def audit_events(request):
    center_only(request)
    query = AuditEvent.objects.order_by("-occurred_at")
    params = request.query_params
    for key in ("category", "object_id", "operation"):
        if params.get(key):
            query = query.filter(**{key: params[key]})
    if params.get("correlation_id"):
        query = query.filter(correlation_id=params["correlation_id"])
    return paginate(request, query, audit_json)


@api_view(["POST"])
@handle_errors
def majority_review(request):
    center_only(request)
    data = payload(request, [], ["dry_run"])
    return Response(
        majority.run_majority_review(
            dry_run=boolean(data, "dry_run", default=True), actor=request.user
        )
    )


URLS = [
    ("privacy/retention-policies", policies),
    ("privacy/retention-policies/<uuid:pk>", policy_detail),
    ("privacy/retention-policies/<uuid:pk>/approve", policy_approve),
    ("privacy/retention-runs", runs),
    ("privacy/requests", privacy_requests),
    ("privacy/requests/<uuid:pk>", privacy_request_detail),
    ("privacy/requests/<uuid:pk>/audiences", privacy_request_audiences),
    ("privacy/requests/<uuid:pk>/<str:action>", privacy_request_action),
    ("privacy/exports", export_list),
    ("privacy/exports/operational", operational_export),
    ("privacy/exports/<uuid:pk>/download", export_download),
    ("privacy/exports/<uuid:pk>/revoke", export_revoke),
    ("privacy/imports", imports),
    ("privacy/imports/template/v<str:version>", import_template),
    ("privacy/audit-events", audit_events),
    ("privacy/majority-review", majority_review),
]


def urlpatterns():
    from django.urls import path

    return [path("api/v1/" + route, view) for route, view in URLS]
