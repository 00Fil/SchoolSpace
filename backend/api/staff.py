"""API tutor (T2) e utenti del centro (T3) — guida v3.1, fase P1.

Stesse convenzioni di ``api.families``: solo centro, payload stretto, motivo e
``expected_version`` sulle modifiche, errori con codice stabile.
"""

from django.core.validators import validate_email
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.education import tutors as service
from apps.education.models import Tutor
from apps.identity.models import Account, Invitation, RoleGrant

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


def _email(data, key="email", required=True):
    value = text(data, key, 254, required=required)
    if value:
        validate_email(value)
        value = value.lower()
    return value


def _invitation_status(email, role):
    if not email:
        return None
    inv = (
        Invitation.objects.filter(email__iexact=email, role=role)
        .order_by("-created_at")
        .first()
    )
    if inv is None:
        return None
    return {
        "id": str(inv.pk),
        "status": inv.status,
        "expires_at": iso(inv.expires_at),
        "send_count": inv.send_count,
        "version": inv.version,
    }


def tutor_json(tutor):
    return {
        "id": str(tutor.pk),
        "display_name": tutor.display_name,
        "email": tutor.email,
        "active": tutor.active,
        "has_account": bool(tutor.account_id),
        "account": str(tutor.account_id) if tutor.account_id else None,
        "invitation": None if tutor.account_id else _invitation_status(tutor.email, "TUTOR"),
        "version": tutor.version,
    }


# --- Tutor ------------------------------------------------------------------------


@api_view(["GET", "POST"])
@handle_errors
def tutors(request):
    center_only(request)
    if request.method == "GET":
        query = Tutor.objects.order_by("display_name", "id")
        params = request.query_params
        if params.get("q"):
            query = query.filter(
                Q(display_name__icontains=params["q"]) | Q(email__icontains=params["q"])
            )
        if params.get("active") in ("true", "false"):
            query = query.filter(active=params["active"] == "true")
        return paginate(request, query, tutor_json)
    data = payload(request, ["display_name", "reason"], ["email", "invite"])
    tutor = service.create_tutor(
        request.user,
        display_name=text(data, "display_name", 120),
        email=_email(data, required=False) if "email" in data else "",
        reason=text(data, "reason", 200),
        invite=boolean(data, "invite"),
        request=request,
    )
    return Response(tutor_json(tutor), status=201)


@api_view(["GET", "PATCH"])
@handle_errors
def tutor_detail(request, pk):
    center_only(request)
    tutor = get_object_or_404(Tutor, pk=pk)
    if request.method == "GET":
        return Response(tutor_json(tutor))
    data = payload(request, ["expected_version", "reason"], ["display_name", "email"])
    changes = {}
    if "display_name" in data:
        changes["display_name"] = text(data, "display_name", 120)
    if "email" in data:
        changes["email"] = _email(data, required=False)
    tutor = service.update_tutor(
        request.user,
        tutor,
        expected_version=integer(data, "expected_version"),
        changes=changes,
        reason=data["reason"],
    )
    return Response(tutor_json(tutor))


@api_view(["POST"])
@handle_errors
def tutor_action(request, pk, action):
    center_only(request)
    tutor = get_object_or_404(Tutor, pk=pk)
    if action in ("deactivate", "reactivate"):
        data = payload(request, ["expected_version", "reason"])
        tutor = service.set_tutor_active(
            request.user,
            tutor,
            active=action == "reactivate",
            expected_version=integer(data, "expected_version"),
            reason=data["reason"],
            request=request,
        )
    elif action == "invite":
        data = payload(request, ["reason"])
        service.invite_tutor(request.user, tutor, reason=data["reason"], request=request)
        tutor.refresh_from_db()
    else:
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response(tutor_json(tutor))


# --- Utenti del centro (T3) -------------------------------------------------------------


def _staff_json(account, now):
    grants = [
        g
        for g in account.role_grants.all()
        if g.role in service.STAFF_ROLES
        and g.revoked_at is None
        and g.valid_from <= now
        and (g.valid_until is None or g.valid_until > now)
    ]
    return {
        "id": str(account.pk),
        "name": account.get_full_name(),
        "email": account.email,
        "is_active": account.is_active,
        "roles": sorted({g.role for g in grants}),
        "mfa_enabled": bool(getattr(account, "mfa_enabled", False)),
        "mfa_required": bool(getattr(account, "mfa_required", False)),
        "last_login": iso(account.last_login),
    }


@api_view(["GET"])
@handle_errors
def center_users(request):
    """Elenco degli account con ruolo CENTER o TUTOR attivo (mai famiglie o studenti)."""
    center_only(request)
    now = timezone.now()
    active = Q(role_grants__role__in=service.STAFF_ROLES, role_grants__revoked_at__isnull=True)
    query = (
        Account.objects.filter(active)
        .distinct()
        .order_by("email")
        .prefetch_related(Prefetch("role_grants", queryset=RoleGrant.objects.all()))
    )
    if request.query_params.get("q"):
        q = request.query_params["q"]
        query = query.filter(
            Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    return paginate(request, query, lambda a: _staff_json(a, now))


@api_view(["GET", "POST"])
@handle_errors
def center_invitations(request):
    center_only(request)
    if request.method == "GET":
        query = Invitation.objects.filter(role__in=service.STAFF_ROLES).order_by(
            "-created_at"
        )
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        return paginate(
            request,
            query,
            lambda inv: {
                "id": str(inv.pk),
                "email": inv.email,
                "role": inv.role,
                "status": inv.status,
                "expires_at": iso(inv.expires_at),
                "send_count": inv.send_count,
                "version": inv.version,
            },
        )
    data = payload(request, ["email", "role", "reason"])
    role = data["role"]
    if role != "CENTER":
        # Gli inviti TUTOR partono dalla scheda tutor, così l'account viene collegato.
        raise BadPayload("role: solo CENTER (i tutor si invitano dalla loro scheda)")
    invitation = service.invite_center_user(
        request.user, email=_email(data), reason=data["reason"], request=request
    )
    return Response({"id": str(invitation.pk), "status": invitation.status}, status=201)


@api_view(["POST"])
@handle_errors
def center_user_revoke_role(request, pk):
    center_only(request)
    account = get_object_or_404(Account, pk=pk)
    data = payload(request, ["role", "reason"])
    service.revoke_staff_role(
        request.user, account, role=data["role"], reason=data["reason"]
    )
    return Response(_staff_json(Account.objects.get(pk=pk), timezone.now()))


URLS = [
    ("registry/tutors", tutors),
    ("registry/tutors/<uuid:pk>", tutor_detail),
    ("registry/tutors/<uuid:pk>/<str:action>", tutor_action),
    ("identity/center-users", center_users),
    ("identity/center-invitations", center_invitations),
    ("identity/center-users/<uuid:pk>/revoke-role", center_user_revoke_role),
]


def urlpatterns():
    from django.urls import path

    return [path("api/v1/" + route, view) for route, view in URLS]
