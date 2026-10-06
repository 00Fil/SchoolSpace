"""Middleware di sicurezza (s1-sicurezza).

- ``SecurityHeadersMiddleware``: CSP, Permissions-Policy, CORP e ``Cache-Control: no-store``
  sulle API (GAP-I02, V14). HSTS, Referrer-Policy e COOP restano a SecurityMiddleware.
- ``AdminGuardMiddleware``: admin Django disattivabile e limitato a reti in allowlist (GAP-I06).
- ``SessionSecurityMiddleware``: registro sessioni, revoca, timeout per ruolo, gate MFA e
  contesto multi-ruolo (GAP-B04, GAP-B07).
"""

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.models import AnonymousUser
from django.http import Http404, JsonResponse

from . import conf, sessions
from .net import client_ip, ip_in_networks
from .policies import CONTEXT_ATTR, available_contexts, mfa_required

DEFAULT_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
DEFAULT_PERMISSIONS_POLICY = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        csp = getattr(settings, "SECURITY_CSP", DEFAULT_CSP)
        if csp:
            header = (
                "Content-Security-Policy-Report-Only"
                if getattr(settings, "SECURITY_CSP_REPORT_ONLY", False)
                else "Content-Security-Policy"
            )
            response.headers.setdefault(header, csp)
        policy = getattr(
            settings, "SECURITY_PERMISSIONS_POLICY", DEFAULT_PERMISSIONS_POLICY
        )
        if policy:
            response.headers.setdefault("Permissions-Policy", policy)
        corp = getattr(settings, "SECURITY_CROSS_ORIGIN_RESOURCE_POLICY", "same-origin")
        if corp:
            response.headers.setdefault("Cross-Origin-Resource-Policy", corp)
        api_cache = getattr(settings, "SECURITY_API_CACHE_CONTROL", "no-store")
        if api_cache and request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", api_cache)
        return response


class AdminGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        prefix = getattr(settings, "ADMIN_URL_PREFIX", "/admin/")
        if request.path.startswith(prefix):
            if not conf.get("ADMIN_ENABLED"):
                raise Http404()
            networks = conf.get("ADMIN_ALLOWED_NETWORKS")
            if networks and not ip_in_networks(client_ip(request), networks):
                raise Http404()
        return self.get_response(request)


def _exempt(path, key):
    return any(path.startswith(p) for p in conf.get(key))


class SessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        blocked = self._enforce(request)
        if blocked is not None:
            return blocked
        return self.get_response(request)

    def _drop(self, request, reason):
        record = sessions.current(request)
        if record is not None:
            sessions.revoke(record, reason)
        logout(request)
        request.user = AnonymousUser()

    def _enforce(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not hasattr(request, "session"):
            return None
        record = sessions.current(request)
        if record is None or record.account_id != user.pk:
            # Sessione non registrata o revocata lato server.
            self._drop(request, "revoked")
            return None
        if sessions.expired(record, user):
            self._drop(request, "timeout")
            return None
        sessions.touch(record)
        request.identity_session = record

        contexts = available_contexts(user)
        context = request.session.get(sessions.CONTEXT_KEY)
        if context and context not in contexts:
            # Concessione revocata dopo la selezione: il contesto non vale più.
            request.session.pop(sessions.CONTEXT_KEY, None)
            context = None
        if context is None and len(contexts) == 1:
            context = next(iter(contexts))
        setattr(user, CONTEXT_ATTR, context)

        path = request.path
        if not path.startswith("/api/") or _exempt(path, "GATE_EXEMPT_PREFIXES"):
            return None
        if mfa_required(user) and record.mfa_verified_at is None:
            return JsonResponse(
                {
                    "code": "MFA_REQUIRED",
                    "message": "Verifica in due passaggi richiesta",
                },
                status=403,
            )
        if (
            context is None
            and len(contexts) > 1
            and conf.get("REQUIRE_CONTEXT_SELECTION")
            and not _exempt(path, "CONTEXT_EXEMPT_PREFIXES")
        ):
            return JsonResponse(
                {
                    "code": "CONTEXT_REQUIRED",
                    "message": "Seleziona il ruolo con cui operare",
                    "contexts": sorted(contexts),
                },
                status=409,
            )
        return None
