"""Middleware di contesto richiesta: correlation_id, durata, access log JSON, metriche.

Va messo in testa a MIDDLEWARE così misura tutta la catena. Non registra mai il
path grezzo, la query string, header o corpo: solo il template della route.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.utils.functional import empty

from . import metrics
from .context import (
    actor_id_var,
    correlation_id_var,
    pseudonymous_actor,
    sanitize_correlation_id,
)

access_log = logging.getLogger("ops.access")

REQUEST_HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"
QUIET_ROUTES = frozenset(
    {"healthz", "readyz", "metrics", "api/v1/health", "api/v1/ready"}
)


def route_of(request) -> str:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return "<unmatched>"
    route = match.route or match.view_name or "<unknown>"
    return route[:120]


def _actor(request):
    user = getattr(request, "user", None)
    if user is None:
        return None
    wrapped = getattr(user, "_wrapped", user)
    if wrapped is empty:  # utente non ancora valutato: non forzare una query in più
        return None
    if getattr(wrapped, "is_authenticated", False):
        return pseudonymous_actor(wrapped.pk)
    return None


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cid = sanitize_correlation_id(request.META.get(REQUEST_HEADER))
        request.correlation_id = cid
        cid_token = correlation_id_var.set(cid)
        actor_token = actor_id_var.set(None)
        started = time.perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            response[RESPONSE_HEADER] = cid
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = route_of(request)
            actor = _actor(request)
            try:
                metrics.observe_request(request.method, route, status, elapsed)
            except Exception:  # le metriche non devono mai rompere una risposta
                pass
            level = (
                logging.DEBUG
                if route in QUIET_ROUTES and status < 500
                else logging.INFO
            )
            if status >= 500:
                level = logging.ERROR
            elif elapsed * 1000 > getattr(settings, "OPS_SLOW_REQUEST_MS", 500):
                level = max(level, logging.WARNING)
            access_log.log(
                level,
                "http.request",
                extra={
                    "action": "http.request",
                    "outcome": "error"
                    if status >= 500
                    else ("denied" if status in (401, 403, 429) else "ok"),
                    "method": request.method,
                    "route": route,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 1),
                    "actor_id": actor,
                },
            )
            correlation_id_var.reset(cid_token)
            actor_id_var.reset(actor_token)
