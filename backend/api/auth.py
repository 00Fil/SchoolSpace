"""API di autenticazione e identità (s1-sicurezza).

Viste Django semplici con CSRF esplicito: DRF ``api_view`` esenterebbe dal CSRF le
richieste anonime (login, reset, accettazione invito). Risposte JSON con ``code`` stabile.
"""

import json
import time
from functools import wraps

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.views.decorators.csrf import csrf_protect

from apps.identity import audit, conf, mfa, services, sessions, throttle
from apps.identity.models import (
    Account,
    IdentityAuditEvent,
    Invitation,
    StudentAccessPolicy,
    UserSession,
    normalize_email,
)
from apps.identity.policies import (
    available_contexts,
    granted_roles,
    is_center,
    mfa_required,
    selected_context,
)
from apps.reasons import reason_or_default


class BadPayload(Exception):
    pass


def error(code, status, message=None, **extra):
    body = {"code": code}
    if message:
        body["message"] = message
    body.update(extra)
    return JsonResponse(body, status=status)


def rate_limited(decision):
    response = error("RATE_LIMITED", 429, "Troppi tentativi, riprova più tardi")
    response["Retry-After"] = str(max(1, decision.retry_after))
    return response


def parse(request, required=(), optional=()):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise BadPayload()
    if not isinstance(data, dict):
        raise BadPayload()
    keys = set(data)
    if not set(required) <= keys or not keys <= set(required) | set(optional):
        raise BadPayload()
    return data


def _text(value, max_length=256):
    if not isinstance(value, str) or len(value) > max_length:
        raise BadPayload()
    return value


def endpoint(methods=("POST",), auth="any", center=False):
    """auth: 'any' | 'user' (sessione completa); center: centro con MFA verificata."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return error("METHOD_NOT_ALLOWED", 405)
            if (auth == "user" or center) and not request.user.is_authenticated:
                return error("NOT_AUTHENTICATED", 403, "Accesso richiesto")
            if center:
                if not is_center(request.user):
                    return error("FORBIDDEN", 403, "Operazione riservata al centro")
                record = getattr(request, "identity_session", None)
                if mfa_required(request.user) and (
                    record is None or record.mfa_verified_at is None
                ):
                    return error(
                        "MFA_REQUIRED", 403, "Verifica in due passaggi richiesta"
                    )
            try:
                return view(request, *args, **kwargs)
            except BadPayload:
                return error("INVALID_PAYLOAD", 400, "Richiesta non valida")
            except services.ServiceError as exc:
                return error(exc.code, exc.status, exc.message, **exc.extra)
            except mfa.MFAError as exc:
                return error(exc.code, 400)

        return csrf_protect(wrapped)

    return decorator


def _me_payload(user):
    return {
        "id": str(user.id),
        "contexts": sorted(available_contexts(user)),
        "context": selected_context(user),
    }


def _complete_login(request, user, mfa_method=None):
    login(request, user, backend="apps.identity.backends.EmailBackend")
    if mfa_method:
        sessions.mark_mfa(request)
    contexts = available_contexts(user)
    if len(contexts) == 1:
        request.session[sessions.CONTEXT_KEY] = next(iter(contexts))
    audit.record(
        "login.succeeded", actor=user, subject=user, request=request, mfa=mfa_method
    )
    body = {"detail": "Accesso eseguito", "mfa_required": False}
    body.update(_me_payload(user))
    body["context_required"] = (
        len(contexts) > 1 and conf.get("REQUIRE_CONTEXT_SELECTION")
    ) and sessions.CONTEXT_KEY not in request.session
    return JsonResponse(body)


# --- Login / logout -------------------------------------------------------------------


@endpoint()
def login_view(request):
    data = parse(request, required=("password",), optional=("email", "username"))
    identifiers = [k for k in ("email", "username") if k in data]
    if len(identifiers) != 1:
        raise BadPayload()
    identifier = normalize_email(_text(data[identifiers[0]], 254))
    password = _text(data["password"], 4096)
    ip = request_ip(request)
    decision = throttle.check("login", ip=ip, identity=identifier)
    if not decision.allowed:
        audit.record("login.rate_limited", request=request)
        return rate_limited(decision)
    user = authenticate(request, username=identifier, password=password)
    if user is None:
        throttle.fail("login", ip=ip, identity=identifier)
        audit.record("login.failed", request=request)
        return error("INVALID_CREDENTIALS", 401, "Credenziali non valide")
    throttle.succeed("login", identity=identifier)
    if request.user.is_authenticated:
        logout(request)
    if mfa_required(user):
        request.session.cycle_key()
        request.session[sessions.PENDING_KEY] = {"uid": str(user.pk), "at": time.time()}
        audit.record("login.mfa_pending", subject=user, request=request)
        return JsonResponse(
            {
                "detail": "Verifica in due passaggi richiesta",
                "mfa_required": True,
                "mfa_enrolled": mfa.is_enrolled(user),
            }
        )
    return _complete_login(request, user)


def request_ip(request):
    from apps.identity.net import client_ip

    return client_ip(request)


@endpoint()
def logout_view(request):
    request.session.pop(sessions.PENDING_KEY, None)
    if request.user.is_authenticated:
        audit.record(
            "logout", actor=request.user, subject=request.user, request=request
        )
    logout(request)
    return JsonResponse({"detail": "Sessione terminata"})


# --- MFA ------------------------------------------------------------------------------


def _mfa_subject(request):
    """Utente in attesa di MFA (login a metà) o sessione completa senza MFA (step-up)."""
    pending = request.session.get(sessions.PENDING_KEY)
    if pending:
        if time.time() - pending.get("at", 0) > conf.get("MFA_PENDING_TTL_SECONDS"):
            request.session.pop(sessions.PENDING_KEY, None)
            return None, False
        user = Account.objects.filter(pk=pending.get("uid"), is_active=True).first()
        return user, True
    if request.user.is_authenticated:
        return request.user, False
    return None, False


def _no_mfa_subject():
    return error("MFA_SESSION_EXPIRED", 401, "Ripeti l'accesso")


def _finish_mfa(request, user, pending, method):
    if pending:
        request.session.pop(sessions.PENDING_KEY, None)
        return _complete_login(request, user, mfa_method=method)
    request.session.cycle_key()
    sessions.mark_mfa(request)
    audit.record("mfa.step_up", actor=user, subject=user, request=request, mfa=method)
    return JsonResponse({"detail": "Verifica completata", "mfa_required": False})


@endpoint(methods=("GET",))
def mfa_status(request):
    user, pending = _mfa_subject(request)
    if user is None:
        return _no_mfa_subject()
    record = getattr(request, "identity_session", None)
    return JsonResponse(
        {
            "required": mfa_required(user),
            "enrolled": mfa.is_enrolled(user),
            "verified": bool(record and record.mfa_verified_at) and not pending,
            "recovery_codes_remaining": mfa.remaining_recovery_codes(user),
        }
    )


@endpoint()
def mfa_setup(request):
    parse(request)
    user, pending = _mfa_subject(request)
    if user is None:
        return _no_mfa_subject()
    data = mfa.begin_setup(user)
    audit.record("mfa.setup_started", actor=user, subject=user, request=request)
    return JsonResponse(data)


@endpoint()
def mfa_confirm(request):
    data = parse(request, required=("code",))
    code = _text(data["code"], 16)
    user, pending = _mfa_subject(request)
    if user is None:
        return _no_mfa_subject()
    ip = request_ip(request)
    decision = throttle.check("mfa", ip=ip, identity=str(user.pk))
    if not decision.allowed:
        return rate_limited(decision)
    try:
        codes = mfa.confirm_setup(user, code)
    except mfa.MFAError:
        throttle.fail("mfa", ip=ip, identity=str(user.pk))
        raise
    throttle.succeed("mfa", identity=str(user.pk))
    audit.record("mfa.enrolled", actor=user, subject=user, request=request)
    response = _finish_mfa(request, user, pending, "totp")
    body = json.loads(response.content)
    body["recovery_codes"] = codes
    return JsonResponse(body, status=response.status_code)


@endpoint()
def mfa_verify(request):
    data = parse(request, optional=("code", "recovery_code"))
    if len(data) != 1:
        raise BadPayload()
    user, pending = _mfa_subject(request)
    if user is None:
        return _no_mfa_subject()
    ip = request_ip(request)
    decision = throttle.check("mfa", ip=ip, identity=str(user.pk))
    if not decision.allowed:
        return rate_limited(decision)
    method = mfa.verify(
        user,
        code=_text(data["code"], 16) if "code" in data else None,
        recovery_code=_text(data["recovery_code"], 32)
        if "recovery_code" in data
        else None,
    )
    if method is None:
        throttle.fail("mfa", ip=ip, identity=str(user.pk))
        audit.record("mfa.failed", subject=user, request=request)
        return error("INVALID_CODE", 400, "Codice non valido")
    throttle.succeed("mfa", identity=str(user.pk))
    return _finish_mfa(request, user, pending, method)


@endpoint(auth="user")
def mfa_recovery_codes(request):
    data = parse(request, required=("code",))
    record = getattr(request, "identity_session", None)
    if record is None or record.mfa_verified_at is None:
        return error("MFA_REQUIRED", 403)
    if mfa.verify(request.user, code=_text(data["code"], 16)) != "totp":
        return error("INVALID_CODE", 400, "Codice non valido")
    codes = mfa.regenerate_recovery_codes(request.user)
    audit.record(
        "mfa.recovery_regenerated",
        actor=request.user,
        subject=request.user,
        request=request,
    )
    return JsonResponse({"recovery_codes": codes})


# --- Password -------------------------------------------------------------------------

RESET_ACCEPTED = {
    "detail": "Se l'indirizzo è registrato riceverai un'email con le istruzioni"
}


@endpoint()
def password_reset(request):
    data = parse(request, required=("email",))
    email = normalize_email(_text(data["email"], 254))
    decision = throttle.consume(
        "password_reset", ip=request_ip(request), identity=email
    )
    if not decision.allowed:
        return rate_limited(decision)
    services.request_password_reset(email, request=request)
    return JsonResponse(RESET_ACCEPTED, status=202)


@endpoint()
def password_reset_confirm(request):
    data = parse(request, required=("token", "password"))
    decision = throttle.check("password_reset_confirm", ip=request_ip(request))
    if not decision.allowed:
        return rate_limited(decision)
    try:
        services.confirm_password_reset(
            _text(data["token"], 128), _text(data["password"], 4096), request=request
        )
    except services.ServiceError as exc:
        if exc.code == services.INVALID_TOKEN:
            throttle.fail("password_reset_confirm", ip=request_ip(request))
        raise
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"detail": "Password aggiornata, accedi di nuovo"})


@endpoint(auth="user")
def password_change(request):
    data = parse(request, required=("current_password", "new_password"))
    record = getattr(request, "identity_session", None)
    services.change_password(
        request.user,
        _text(data["current_password"], 4096),
        _text(data["new_password"], 4096),
        keep_session_id=record.pk if record else None,
        request=request,
    )
    update_session_auth_hash(request, request.user)
    return JsonResponse(
        {"detail": "Password aggiornata; le altre sessioni sono chiuse"}
    )


# --- Sessioni -------------------------------------------------------------------------


def _session_row(record, current_id):
    return {
        "id": str(record.id),
        "created_at": record.created_at.isoformat(),
        "last_seen_at": record.last_seen_at.isoformat(),
        "user_agent": record.user_agent,
        "mfa_verified": record.mfa_verified_at is not None,
        "current": record.id == current_id,
    }


@endpoint(methods=("GET",), auth="user")
def session_list(request):
    current = getattr(request, "identity_session", None)
    rows = UserSession.objects.filter(
        account=request.user, revoked_at__isnull=True
    ).order_by("-last_seen_at")
    return JsonResponse(
        {"results": [_session_row(r, current.id if current else None) for r in rows]}
    )


@endpoint(auth="user")
def session_revoke(request, pk):
    record = get_object_or_404(
        UserSession, pk=pk, account=request.user, revoked_at__isnull=True
    )
    sessions.revoke(record, "user_revoked")
    audit.record(
        "session.revoked",
        actor=request.user,
        subject=request.user,
        object_id=pk,
        request=request,
    )
    current = getattr(request, "identity_session", None)
    if current and current.pk == record.pk:
        logout(request)
    return JsonResponse({"detail": "Sessione revocata"})


@endpoint(auth="user")
def session_revoke_all(request):
    data = parse(request, optional=("include_current",))
    include_current = data.get("include_current", False)
    if not isinstance(include_current, bool):
        raise BadPayload()
    current = getattr(request, "identity_session", None)
    count = sessions.revoke_all(
        request.user,
        "user_revoked_all",
        except_id=None if include_current or current is None else current.pk,
    )
    audit.record(
        "session.revoked_all",
        actor=request.user,
        subject=request.user,
        request=request,
        count=count,
    )
    if include_current:
        logout(request)
    return JsonResponse({"detail": "Sessioni revocate", "revoked": count})


# --- Contesto multi-ruolo -------------------------------------------------------------


@endpoint(methods=("GET", "POST"), auth="user")
def context_view(request):
    if request.method == "GET":
        return JsonResponse(_me_payload(request.user))
    data = parse(request, required=("context",))
    context = _text(data["context"], 12)
    if context not in available_contexts(request.user):
        audit.record(
            "context.denied",
            actor=request.user,
            subject=request.user,
            request=request,
            context=context,
        )
        return error("CONTEXT_NOT_GRANTED", 403, "Ruolo non concesso")
    request.session.cycle_key()  # rotazione dell'ID al cambio di privilegi
    request.session[sessions.CONTEXT_KEY] = context
    setattr(request.user, "_identity_context", context)
    audit.record(
        "context.selected",
        actor=request.user,
        subject=request.user,
        request=request,
        context=context,
    )
    return JsonResponse(_me_payload(request.user))


@endpoint(auth="user")
def student_guardian_consent(request):
    data = parse(request, required=("granted",))
    if not isinstance(data["granted"], bool) or "STUDENT" not in granted_roles(
        request.user
    ):
        raise BadPayload()
    policy = services.set_student_guardian_consent(
        request.user, data["granted"], request=request
    )
    return JsonResponse({"consent": policy.student_consent_at is not None})


# --- Inviti ---------------------------------------------------------------------------


def _invitation_row(inv):
    return {
        "id": str(inv.id),
        "email": inv.email,
        "role": inv.role,
        "student": str(inv.student_id) if inv.student_id else None,
        "can_manage_availability": inv.can_manage_availability,
        "status": inv.status,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "relation_verified_at": inv.relation_verified_at.isoformat()
        if inv.relation_verified_at
        else None,
        "send_count": inv.send_count,
        "created_at": inv.created_at.isoformat(),
        "version": inv.version,
    }


@endpoint(methods=("GET", "POST"), center=True)
def invitations(request):
    from apps.education.models import Student

    if request.method == "GET":
        rows = Invitation.objects.order_by("-created_at")[:200]
        return JsonResponse({"results": [_invitation_row(r) for r in rows]})
    data = parse(
        request,
        required=("email", "role"),
        optional=("student", "can_manage_availability", "age_confirmed"),
    )
    email = normalize_email(_text(data["email"], 254))
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    try:
        validate_email(email)
    except ValidationError:
        return error("INVALID_EMAIL", 400)
    student = None
    if data.get("student") is not None:
        student = Student.objects.filter(pk=_text(data["student"], 40)).first()
        if student is None:
            return error("STUDENT_NOT_FOUND", 400)
    manage = data.get("can_manage_availability", False)
    age_confirmed = data.get("age_confirmed", False)
    if not isinstance(manage, bool) or not isinstance(age_confirmed, bool):
        raise BadPayload()
    invitation = services.create_invitation(
        request.user,
        email,
        _text(data["role"], 12),
        student=student,
        can_manage_availability=manage,
        request=request,
        age_confirmed=age_confirmed,
    )
    return JsonResponse(_invitation_row(invitation), status=201)


@endpoint(methods=("GET",), center=True)
def invitation_detail(request, pk):
    return JsonResponse(_invitation_row(get_object_or_404(Invitation, pk=pk)))


@endpoint(center=True)
def invitation_verify_relation(request, pk):
    data = parse(request, required=("evidence",))
    inv = services.verify_guardian_relation(
        request.user, pk, _text(data["evidence"], 200), request=request
    )
    return JsonResponse(_invitation_row(inv))


@endpoint(center=True)
def invitation_resend(request, pk):
    parse(request)
    return JsonResponse(
        _invitation_row(services.resend_invitation(request.user, pk, request=request))
    )


@endpoint(center=True)
def invitation_revoke(request, pk):
    parse(request)
    return JsonResponse(
        _invitation_row(services.revoke_invitation(request.user, pk, request=request))
    )


@endpoint()
def invitation_accept(request):
    data = parse(request, required=("token",), optional=("password",))
    decision = throttle.check("invitation_accept", ip=request_ip(request))
    if not decision.allowed:
        return rate_limited(decision)
    password = data.get("password")
    if password is not None:
        _text(password, 4096)
    was_signed_in = request.user.is_authenticated
    try:
        account = services.accept_invitation(
            _text(data["token"], 128),
            password=password,
            current_user=request.user,
            request=request,
        )
    except services.ServiceError as exc:
        if exc.code == services.INVALID_TOKEN:
            throttle.fail("invitation_accept", ip=request_ip(request))
        raise
    if not was_signed_in and password and not mfa_required(account):
        # v0.9.5: chi ha appena scelto la password (link email o QR del centro) entra
        # subito nella sua pagina. Gli account del centro passano comunque dalla MFA.
        response = _complete_login(request, account)
        body = json.loads(response.content)
        body.update({"detail": "Invito accettato", "signed_in": True})
        return JsonResponse(body, status=201)
    return JsonResponse({"detail": "Invito accettato", "signed_in": False}, status=201)


# --- Amministrazione account (centro + MFA) -------------------------------------------


@endpoint(center=True)
def account_revoke_sessions(request, pk):
    parse(request)
    target = get_object_or_404(Account, pk=pk)
    count = sessions.revoke_all(target, "admin_revoked")
    audit.record(
        "session.admin_revoked_all",
        actor=request.user,
        subject=target,
        request=request,
        count=count,
    )
    return JsonResponse({"detail": "Sessioni revocate", "revoked": count})


@endpoint(center=True)
def account_mfa_reset(request, pk):
    data = parse(request, optional=("reason",))
    reason = reason_or_default(data.get("reason"))
    target = get_object_or_404(Account, pk=pk)
    if target.pk == request.user.pk:
        # Il reset della MFA richiede un secondo amministratore.
        return error("SECOND_ADMIN_REQUIRED", 403, "Serve un altro amministratore")
    mfa.reset(target)
    count = sessions.revoke_all(target, "mfa_reset")
    audit.record(
        "mfa.reset",
        actor=request.user,
        subject=target,
        request=request,
        reason=reason,
        sessions_revoked=count,
    )
    return JsonResponse({"detail": "MFA azzerata", "sessions_revoked": count})


@endpoint(methods=("GET", "PUT"), center=True)
def student_access_policy(request, pk):
    from apps.education.models import Student

    student = get_object_or_404(Student, pk=pk)
    if request.method == "PUT":
        data = parse(
            request,
            required=("adult_confirmed", "guardian_access"),
            optional=("expected_version",),
        )
        version = data.get("expected_version")
        if not isinstance(data["adult_confirmed"], bool) or (
            version is not None and type(version) is not int
        ):
            raise BadPayload()
        services.set_student_access_policy(
            request.user,
            student,
            data["adult_confirmed"],
            _text(data["guardian_access"], 20),
            expected_version=version,
            request=request,
        )
    policy = StudentAccessPolicy.objects.filter(student=student).first()
    return JsonResponse(
        {
            "student": str(student.id),
            "adult_confirmed": bool(policy and policy.adult_confirmed),
            "guardian_access": policy.guardian_access if policy else "DEFAULT",
            "default_guardian_access": conf.get("ADULT_GUARDIAN_ACCESS"),
            "student_consent": bool(policy and policy.student_consent_at),
            "version": policy.version if policy else 0,
        }
    )


@endpoint(methods=("GET",), center=True)
def audit_events(request):
    query = IdentityAuditEvent.objects.select_related(None).order_by("-occurred_at")
    subject = request.GET.get("subject")
    if subject:
        query = query.filter(subject_id=subject)
    rows = query[:200]
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(e.id),
                    "occurred_at": e.occurred_at.isoformat(),
                    "operation": e.operation,
                    "actor": str(e.actor_id) if e.actor_id else None,
                    "subject": str(e.subject_id) if e.subject_id else None,
                    "object_id": str(e.object_id) if e.object_id else None,
                    "details": e.details,
                }
                for e in rows
            ]
        }
    )


urlpatterns = [
    path("auth/login", login_view),
    path("auth/logout", logout_view),
    path("auth/mfa", mfa_status),
    path("auth/mfa/setup", mfa_setup),
    path("auth/mfa/confirm", mfa_confirm),
    path("auth/mfa/verify", mfa_verify),
    path("auth/mfa/recovery-codes", mfa_recovery_codes),
    path("auth/password-reset", password_reset),
    path("auth/password-reset/confirm", password_reset_confirm),
    path("auth/password-change", password_change),
    path("auth/sessions", session_list),
    path("auth/sessions/revoke-all", session_revoke_all),
    path("auth/sessions/<uuid:pk>/revoke", session_revoke),
    path("auth/context", context_view),
    path("auth/student-consent", student_guardian_consent),
    path("invitations", invitations),
    path("invitations/accept", invitation_accept),
    path("invitations/<uuid:pk>", invitation_detail),
    path("invitations/<uuid:pk>/verify-relation", invitation_verify_relation),
    path("invitations/<uuid:pk>/resend", invitation_resend),
    path("invitations/<uuid:pk>/revoke", invitation_revoke),
    path("identity/accounts/<uuid:pk>/sessions/revoke-all", account_revoke_sessions),
    path("identity/accounts/<uuid:pk>/mfa/reset", account_mfa_reset),
    path("identity/students/<uuid:pk>/access-policy", student_access_policy),
    path("identity/audit", audit_events),
]
