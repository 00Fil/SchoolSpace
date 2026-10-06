"""API auditate per famiglie, studenti, deleghe GuardianLink e inviti (GAP-B06).

L'admin Django resta solo per emergenze (e le sue azioni finiscono nell'audit unificato).
Scritture solo per il centro, con motivo e versione attesa; l'accettazione dell'invito è
l'unico endpoint anonimo (token monouso, risposta uniforme).
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.education.models import Family, GuardianLink, Student
from apps.privacy import majority, registry
from apps.identity.models import Invitation
from apps.privacy.models import (
    FamilyGuardian,
    FamilyProfile,
    GuardianLinkDetail,
    InvitationTerms,
    StudentProfile,
)

from ._privacy_common import (
    BadPayload,
    boolean,
    center_only,
    handle_errors,
    integer,
    iso,
    iso_date,
    iso_datetime,
    paginate,
    payload,
    text,
)


def family_json(family):
    profile = FamilyProfile.objects.filter(family=family).first()
    return {
        "id": str(family.pk),
        "reference": family.reference,
        "contact_name": profile.contact_name if profile else "",
        "contact_email": profile.contact_email if profile else "",
        "contact_phone": profile.contact_phone if profile else "",
        "students": [str(pk) for pk in family.student_set.values_list("pk", flat=True)],
        "version": family.version,
    }


def family_full_json(family):
    """Famiglia con figli e genitori/tutori in un colpo solo (vista a schede e pagina)."""
    data = family_json(family)
    children = list(family.student_set.order_by("display_name", "id"))
    data["children"] = [student_json(s) for s in children]
    data["guardians"] = family_guardians_json(family, children)
    return data


def _guardian_status(invitation, has_account, now):
    if has_account:
        return "ACTIVE"
    if invitation is None or invitation.status == Invitation.Status.REVOKED:
        return "NO_INVITE"
    if invitation.status == Invitation.Status.PENDING_VERIFICATION:
        return "TO_VERIFY"
    if invitation.status == Invitation.Status.SENT:
        return "INVITED" if invitation.expires_at and invitation.expires_at > now else "EXPIRED"
    return "ACTIVE"


def family_guardians_json(family, children=None):
    """Genitori di famiglia (v0.9.5) e, per le famiglie precedenti, deleghe per figlio."""
    now = timezone.now()
    children = children if children is not None else list(family.student_set.all())
    ids = [c.pk for c in children]
    links = list(
        GuardianLink.objects.filter(student_id__in=ids, revoked_at__isnull=True)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .select_related("account")
    )
    out, seen = [], set()
    for g in FamilyGuardian.objects.filter(
        family=family, revoked_at__isnull=True
    ).select_related("invitation", "account"):
        mine = [l for l in links if g.account_id and l.account_id == g.account_id]
        seen.add(g.email.lower())
        if g.account_id:
            seen.add(g.account.email.lower())
        out.append(
            {
                "id": str(g.pk),
                "legacy": False,
                "family": str(family.pk),
                "name": g.display_name,
                "email": g.email,
                "phone": g.phone,
                "relationship": g.relationship,
                "permissions": {k: getattr(g, k) for k in registry.GUARDIAN_PERMS},
                "status": _guardian_status(g.invitation, bool(g.account_id), now),
                "invitation": invitation_json(g.invitation) if g.invitation else None,
                "account": str(g.account_id) if g.account_id else None,
                "students": [str(l.student_id) for l in mine if l.verified],
                "links": [link_json(l) for l in mine],
                "version": g.version,
            }
        )
    # Famiglie create prima della v0.9.5: genitori collegati figlio per figlio.
    legacy = {}
    for l in links:
        email = l.account.email.lower()
        if email in seen:
            continue
        row = legacy.setdefault(email, {"name": l.account.get_full_name(), "links": [], "invites": []})
        row["links"].append(l)
    for inv in Invitation.objects.filter(
        role="GUARDIAN",
        student_id__in=ids,
        status__in=[Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT],
    ):
        if inv.email.lower() in seen:
            continue
        legacy.setdefault(inv.email.lower(), {"name": "", "links": [], "invites": []})["invites"].append(inv)
    for email, row in legacy.items():
        first_inv = row["invites"][0] if row["invites"] else None
        detail = (
            GuardianLinkDetail.objects.filter(link=row["links"][0]).first()
            if row["links"]
            else None
        )
        out.append(
            {
                "id": None,
                "legacy": True,
                "family": str(family.pk),
                "name": row["name"],
                "email": email,
                "phone": "",
                "relationship": detail.relationship if detail else None,
                "permissions": None,
                "status": "ACTIVE"
                if any(l.verified for l in row["links"])
                else _guardian_status(first_inv, False, now)
                if first_inv
                else "TO_VERIFY",
                "invitation": invitation_json(first_inv) if first_inv else None,
                "invitations": [invitation_json(i) for i in row["invites"]],
                "account": str(row["links"][0].account_id) if row["links"] else None,
                "students": [str(l.student_id) for l in row["links"] if l.verified],
                "links": [link_json(l) for l in row["links"]],
                "version": None,
            }
        )
    return out


def student_json(student):
    profile = StudentProfile.objects.filter(student=student).first()
    return {
        "id": str(student.pk),
        "family": str(student.family_id),
        "display_name": student.display_name,
        "level": student.level,
        "active": student.active,
        "has_account": bool(student.account_id),
        "birth_date": iso(profile.birth_date) if profile else None,
        "version": student.version,
    }


def link_json(link):
    detail = GuardianLinkDetail.objects.filter(link=link).first()
    now = timezone.now()
    return {
        "id": str(link.pk),
        "student": str(link.student_id),
        "account": str(link.account_id),
        "guardian_name": link.account.get_full_name(),
        "guardian_email": link.account.email,
        "relationship": detail.relationship if detail else None,
        "can_view": link.can_view,
        "can_manage_availability": link.can_manage_availability,
        "can_receive_notifications": detail.can_receive_notifications
        if detail
        else None,
        "can_request_changes": detail.can_request_changes if detail else None,
        "verified": link.verified,
        "verified_at": iso(detail.verified_at) if detail else None,
        "verification_method": detail.verification_method if detail else "",
        "valid_from": iso(link.valid_from),
        "valid_until": iso(link.valid_until),
        "revoked_at": iso(link.revoked_at),
        "revocation_reason": detail.revocation_reason if detail else "",
        "reconfirmation": detail.reconfirmation if detail else "NOT_REQUIRED",
        "reconfirmation_due_at": iso(detail.reconfirmation_due_at) if detail else None,
        "active": bool(
            link.verified
            and not link.revoked_at
            and link.valid_from <= now
            and (link.valid_until is None or link.valid_until > now)
        ),
        "version": link.version,
    }


def invitation_json(invitation):
    """Vista di registro di un invito di identity: mai token o hash."""
    terms = InvitationTerms.objects.filter(invitation=invitation).first()
    return {
        "id": str(invitation.pk),
        "email": invitation.email,
        "student": str(invitation.student_id) if invitation.student_id else None,
        "family": str(invitation.family_id) if invitation.family_id else None,
        "status": invitation.status,
        "relationship": terms.relationship if terms else None,
        "can_manage_availability": invitation.can_manage_availability,
        "can_receive_notifications": terms.can_receive_notifications if terms else None,
        "can_request_changes": terms.can_request_changes if terms else None,
        "relation_verified_at": iso(invitation.relation_verified_at),
        "expires_at": iso(invitation.expires_at),
        "accepted_at": iso(invitation.accepted_at),
        "send_count": invitation.send_count,
        "version": invitation.version,
    }


# --- Famiglie ------------------------------------------------------------------

CONTACT = ("contact_name", "contact_email", "contact_phone")


def _contact(data):
    out = {}
    for key, limit in zip(CONTACT, (120, 254, 30)):
        if key in data:
            out[key] = text(data, key, limit, required=False)
    if out.get("contact_email"):
        from django.core.validators import validate_email

        validate_email(out["contact_email"])
        out["contact_email"] = out["contact_email"].lower()
    return out


@api_view(["GET", "POST"])
@handle_errors
def families(request):
    center_only(request)
    if request.method == "GET":
        query = Family.objects.order_by("reference")
        q = request.query_params.get("q")
        if q:
            query = query.filter(
                Q(reference__icontains=q)
                | Q(student__display_name__icontains=q)
                | Q(guardians__display_name__icontains=q, guardians__revoked_at__isnull=True)
                | Q(guardians__email__icontains=q, guardians__revoked_at__isnull=True)
                | Q(privacy_profile__contact_name__icontains=q)
            ).distinct()
        render = family_full_json if request.query_params.get("expand") else family_json
        return paginate(request, query, render)
    data = payload(request, ["reference", "reason"], CONTACT)
    family, _ = registry.create_family(
        request.user,
        reference=text(data, "reference", 80),
        contact=_contact(data),
        reason=text(data, "reason", 200),
    )
    return Response(family_json(family), status=201)


@api_view(["GET", "PATCH"])
@handle_errors
def family_detail(request, pk):
    center_only(request)
    family = get_object_or_404(Family, pk=pk)
    if request.method == "GET":
        return Response(family_full_json(family))
    data = payload(request, ["expected_version", "reason"], ("reference",) + CONTACT)
    changes = _contact(data)
    if "reference" in data:
        changes["reference"] = text(data, "reference", 80)
    family = registry.update_family(
        request.user,
        family,
        expected_version=integer(data, "expected_version"),
        changes=changes,
        reason=data["reason"],
    )
    return Response(family_json(family))


# --- Studenti ------------------------------------------------------------------


@api_view(["GET", "POST"])
@handle_errors
def students(request):
    center_only(request)
    if request.method == "GET":
        query = Student.objects.order_by("display_name", "id")
        if request.query_params.get("family"):
            query = query.filter(family_id=request.query_params["family"])
        return paginate(request, query, student_json)
    data = payload(
        request, ["family", "display_name", "reason"], ("level", "birth_date")
    )
    family = get_object_or_404(Family, pk=data["family"])
    student = registry.create_student(
        request.user,
        family=family,
        display_name=text(data, "display_name", 120),
        level=text(data, "level", 60, required=False),
        birth_date=iso_date(data, "birth_date"),
        reason=text(data, "reason", 200),
    )
    return Response(student_json(student), status=201)


@api_view(["GET", "PATCH"])
@handle_errors
def student_detail(request, pk):
    center_only(request)
    student = get_object_or_404(Student, pk=pk)
    if request.method == "GET":
        data = student_json(student)
        data["guardian_links"] = [
            link_json(link)
            for link in GuardianLink.objects.filter(student=student).select_related(
                "account"
            )
        ]
        return Response(data)
    data = payload(
        request,
        ["expected_version", "reason"],
        ("display_name", "level", "family", "active", "birth_date"),
    )
    changes = {}
    if "display_name" in data:
        changes["display_name"] = text(data, "display_name", 120)
    if "level" in data:
        changes["level"] = text(data, "level", 60, required=False)
    if "family" in data:
        changes["family"] = get_object_or_404(Family, pk=data["family"])
    if "active" in data:
        changes["active"] = boolean(data, "active")
    if "birth_date" in data:
        changes["birth_date"] = iso_date(data, "birth_date")
    student = registry.update_student(
        request.user,
        student,
        expected_version=integer(data, "expected_version"),
        changes=changes,
        reason=data["reason"],
    )
    return Response(student_json(student))


# --- Deleghe ---------------------------------------------------------------------

PERMS = registry.PERMISSION_FIELDS


def _permissions(data):
    perms = data.get("permissions", {})
    if not isinstance(perms, dict) or set(perms) - set(PERMS):
        raise BadPayload("permissions: chiavi ammesse " + ", ".join(PERMS))
    if any(not isinstance(v, bool) for v in perms.values()):
        raise BadPayload("permissions: valori booleani")
    return perms


@api_view(["GET", "POST"])
@handle_errors
def guardian_links(request):
    center_only(request)
    if request.method == "GET":
        query = GuardianLink.objects.select_related("account").order_by("-created_at")
        params = request.query_params
        if params.get("student"):
            query = query.filter(student_id=params["student"])
        if params.get("account"):
            query = query.filter(account_id=params["account"])
        if params.get("reconfirmation"):
            query = query.filter(detail__reconfirmation=params["reconfirmation"])
        if params.get("state") == "active":
            now = timezone.now()
            query = query.filter(
                verified=True, revoked_at__isnull=True, valid_from__lte=now
            ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        return paginate(request, query, link_json)
    data = payload(
        request,
        ["student", "reason"],
        (
            "account",
            "guardian_email",
            "relationship",
            "permissions",
            "valid_from",
            "valid_until",
        ),
    )
    student = get_object_or_404(Student, pk=data["student"])
    if bool(data.get("account")) == bool(data.get("guardian_email")):
        raise BadPayload("Indicare account oppure guardian_email")
    relationship = data.get("relationship", "PARENT")
    if relationship not in GuardianLinkDetail.Relationship.values:
        raise BadPayload("relationship non valida")
    if data.get("account"):
        account = get_object_or_404(get_user_model(), pk=data["account"])
    else:
        from django.core.validators import validate_email

        email = text(data, "guardian_email", 254)
        validate_email(email)
        account = registry.existing_account(email)
        if account is None:
            # Nuovo tutore: la delega nasce accettando l'invito (identity, B02).
            invitation = registry.invite_guardian(
                request.user,
                student=student,
                email=email,
                relationship=relationship,
                permissions=_permissions(data),
                reason=text(data, "reason", 200),
                request=request,
            )
            return Response(
                {"invitation": invitation_json(invitation), "link": None}, status=202
            )
    link = registry.create_guardian_link(
        request.user,
        student=student,
        account=account,
        relationship=relationship,
        permissions=_permissions(data),
        valid_from=iso_datetime(data, "valid_from"),
        valid_until=iso_datetime(data, "valid_until"),
        reason=text(data, "reason", 200),
    )
    return Response(link_json(link), status=201)


@api_view(["GET"])
@handle_errors
def guardian_link_detail(request, pk):
    center_only(request)
    return Response(link_json(get_object_or_404(GuardianLink, pk=pk)))


@api_view(["POST"])
@handle_errors
def guardian_link_action(request, pk, action):
    link = get_object_or_404(GuardianLink, pk=pk)
    if action in ("reconfirm", "decline"):
        # Il centro oppure lo studente maggiorenne titolare dell'account.
        if action == "reconfirm":
            data = payload(request, ["confirmation", "reason"])
            link = majority.reconfirm(
                request.user,
                link,
                confirmation=data["confirmation"],
                reason=data["reason"],
            )
        else:
            data = payload(request, ["reason"])
            link = majority.decline(request.user, link, reason=data["reason"])
        return Response(link_json(GuardianLink.objects.get(pk=link.pk)))
    center_only(request)
    if action == "verify":
        data = payload(request, ["expected_version", "method", "reason"])
        link = registry.verify_guardian_link(
            request.user,
            link,
            expected_version=integer(data, "expected_version"),
            method=data["method"],
            reason=data["reason"],
        )
    elif action == "permissions":
        data = payload(request, ["expected_version", "permissions", "reason"])
        link = registry.update_link_permissions(
            request.user,
            link,
            expected_version=integer(data, "expected_version"),
            permissions=_permissions(data),
            reason=data["reason"],
        )
    elif action == "revoke":
        data = payload(request, ["reason"], ["expected_version"])
        link = registry.revoke_guardian_link(
            request.user,
            link,
            expected_version=integer(data, "expected_version", required=False),
            reason=data["reason"],
        )
    else:
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response(link_json(GuardianLink.objects.get(pk=link.pk)))


# --- Inviti ----------------------------------------------------------------------


@api_view(["GET", "POST"])
@handle_errors
def invitations(request):
    """Inviti tutore con le condizioni della delega; il token lo consegna identity."""
    center_only(request)
    if request.method == "GET":
        query = Invitation.objects.filter(role="GUARDIAN").order_by("-created_at")
        params = request.query_params
        if params.get("status"):
            query = query.filter(status=params["status"])
        if params.get("student"):
            query = query.filter(student_id=params["student"])
        return paginate(request, query, invitation_json)
    data = payload(
        request, ["student", "email", "reason"], ["relationship", "permissions"]
    )
    from django.core.validators import validate_email

    email = text(data, "email", 254)
    validate_email(email)
    relationship = data.get("relationship", "PARENT")
    if relationship not in GuardianLinkDetail.Relationship.values:
        raise BadPayload("relationship non valida")
    invitation = registry.invite_guardian(
        request.user,
        student=get_object_or_404(Student, pk=data["student"]),
        email=email,
        relationship=relationship,
        permissions=_permissions(data),
        reason=text(data, "reason", 200),
        request=request,
    )
    return Response(invitation_json(invitation), status=201)


@api_view(["POST"])
@handle_errors
def invitation_action(request, pk, action):
    center_only(request)
    invitation = get_object_or_404(Invitation, pk=pk, role="GUARDIAN")
    if action == "verify-relation":
        data = payload(request, ["evidence"])
        invitation = registry.verify_invitation_relation(
            request.user,
            invitation,
            evidence=text(data, "evidence", 200),
            request=request,
        )
    elif action == "resend":
        payload(request)
        invitation = registry.resend_invitation(
            request.user, invitation, request=request
        )
    elif action == "revoke":
        data = payload(request, ["reason"])
        invitation = registry.revoke_invitation(
            request.user, invitation, reason=data["reason"], request=request
        )
    elif action == "qr":
        # Link breve per il QR: il centro lo mostra a schermo, il genitore lo scansiona.
        payload(request)
        url, expires = registry.invitation_qr_link(
            request.user, invitation, request=request
        )
        response = Response({"url": url, "expires_at": iso(expires)})
        response["Cache-Control"] = "no-store"
        return response
    else:
        return Response({"code": "NOT_FOUND"}, status=404)
    return Response(invitation_json(invitation))


# --- Iscrizione guidata e genitori di famiglia (v0.9.5) -------------------------------

GUARDIAN_FIELDS = ("name", "email", "phone", "relationship", "permissions", "evidence")


def _guardian_input(data):
    if not isinstance(data, dict) or set(data) - set(GUARDIAN_FIELDS):
        raise BadPayload("guardian: campi ammessi " + ", ".join(GUARDIAN_FIELDS))
    from django.core.validators import validate_email

    email = text(data, "email", 254)
    validate_email(email)
    perms = data.get("permissions") or {}
    if not isinstance(perms, dict) or any(not isinstance(v, bool) for v in perms.values()):
        raise BadPayload("permissions: oggetto di booleani")
    return {
        "display_name": text(data, "name", 120),
        "email": email,
        "phone": text(data, "phone", 30, required=False),
        "relationship": data.get("relationship") or "PARENT",
        "permissions": perms,
        "evidence": text(data, "evidence", 200, required=False),
    }


def _child_input(data):
    if not isinstance(data, dict) or set(data) - {"display_name", "level", "birth_date"}:
        raise BadPayload("children: campi ammessi display_name, level, birth_date")
    return {
        "display_name": text(data, "display_name", 120),
        "level": text(data, "level", 60, required=False),
        "birth_date": iso_date(data, "birth_date"),
    }


def guardian_row(guardian):
    family = guardian.family
    row = next(
        (g for g in family_guardians_json(family) if g["id"] == str(guardian.pk)), None
    )
    return row


@api_view(["POST"])
@handle_errors
def family_onboard(request):
    """Nuova famiglia partendo dal genitore: famiglia, invito e figli in una transazione."""
    center_only(request)
    data = payload(request, ["reference", "guardian", "reason"], ["children"])
    children = data.get("children") or []
    if not isinstance(children, list) or len(children) > 12:
        raise BadPayload("children: elenco (max 12)")
    family, guardian = registry.onboard_family(
        request.user,
        reference=text(data, "reference", 80),
        guardian=_guardian_input(data["guardian"]),
        children=[_child_input(c) for c in children],
        reason=text(data, "reason", 200),
        request=request,
    )
    return Response(
        {"family": family_full_json(family), "guardian": guardian_row(guardian)},
        status=201,
    )


@api_view(["POST"])
@handle_errors
def family_guardians(request, pk):
    center_only(request)
    family = get_object_or_404(Family, pk=pk)
    data = payload(request, ["guardian", "reason"])
    guardian = registry.add_family_guardian(
        request.user,
        family,
        reason=text(data, "reason", 200),
        request=request,
        **_guardian_input(data["guardian"]),
    )
    return Response(guardian_row(guardian), status=201)


@api_view(["PATCH"])
@handle_errors
def family_guardian_detail(request, pk):
    center_only(request)
    guardian = get_object_or_404(FamilyGuardian, pk=pk)
    data = payload(
        request,
        ["expected_version", "reason"],
        ("name", "phone", "relationship", "permissions"),
    )
    changes = {}
    if "name" in data:
        changes["display_name"] = text(data, "name", 120)
    if "phone" in data:
        changes["phone"] = text(data, "phone", 30, required=False)
    if "relationship" in data:
        changes["relationship"] = data["relationship"]
    if "permissions" in data:
        changes["permissions"] = data["permissions"]
    guardian = registry.update_family_guardian(
        request.user,
        guardian,
        expected_version=integer(data, "expected_version"),
        changes=changes,
        reason=text(data, "reason", 200),
    )
    return Response(guardian_row(guardian))


@api_view(["POST"])
@handle_errors
def family_guardian_action(request, pk, action):
    center_only(request)
    guardian = get_object_or_404(FamilyGuardian, pk=pk)
    if action == "remove":
        data = payload(request, ["reason"])
        registry.remove_family_guardian(
            request.user, guardian, reason=text(data, "reason", 200), request=request
        )
        return Response({"id": str(guardian.pk), "removed": True})
    if action == "reinvite":
        data = payload(request, ["reason"], ["evidence"])
        guardian = registry.reinvite_family_guardian(
            request.user,
            guardian,
            evidence=text(data, "evidence", 200, required=False),
            reason=text(data, "reason", 200),
            request=request,
        )
        return Response(guardian_row(guardian))
    return Response({"code": "NOT_FOUND"}, status=404)


URLS = [
    ("registry/families", families),
    ("registry/families/onboard", family_onboard),
    ("registry/families/<uuid:pk>", family_detail),
    ("registry/families/<uuid:pk>/guardians", family_guardians),
    ("registry/family-guardians/<uuid:pk>", family_guardian_detail),
    ("registry/family-guardians/<uuid:pk>/<str:action>", family_guardian_action),
    ("registry/students", students),
    ("registry/students/<uuid:pk>", student_detail),
    ("registry/guardian-links", guardian_links),
    ("registry/guardian-links/<uuid:pk>", guardian_link_detail),
    (
        "registry/guardian-links/<uuid:pk>/<str:action>",
        guardian_link_action,
    ),
    ("registry/invitations", invitations),
    ("registry/invitations/<uuid:pk>/<str:action>", invitation_action),
]


def urlpatterns():
    from django.urls import path

    return [path("api/v1/" + route, view) for route, view in URLS]
