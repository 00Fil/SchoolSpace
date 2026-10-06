"""Endpoint di esercizio: /healthz (liveness), /readyz e /api/v1/ready (readiness), /metrics."""

from __future__ import annotations

import hmac

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from . import metrics
from .readiness import run_checks


def _json(payload, status=200):
    response = JsonResponse(payload, status=status)
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@require_GET
def healthz(request):
    """Liveness: il processo risponde. Nessuna dipendenza esterna."""
    return _json(
        {"status": "ok", "build": getattr(settings, "BUILD_VERSION", "unknown")}
    )


@never_cache
@require_GET
def readyz(request):
    """Readiness con dettaglio per controllo (solo ok/fail, nessun messaggio d'errore)."""
    healthy, results = run_checks()
    return _json(
        {"status": "ok" if healthy else "fail", "checks": results},
        status=200 if healthy else 503,
    )


@never_cache
@require_GET
def ready_public(request):
    """Readiness pubblica per il probe esterno: non espone neppure i nomi dei controlli."""
    healthy, _ = run_checks()
    return _json(
        {"status": "ok" if healthy else "fail"}, status=200 if healthy else 503
    )


@never_cache
@require_GET
def metrics_view(request):
    """Esposizione Prometheus. Richiede ``Authorization: Bearer <OPS_METRICS_TOKEN>``;
    senza token configurato è disponibile solo con DEBUG (sviluppo)."""
    token = getattr(settings, "OPS_METRICS_TOKEN", "")
    if token:
        supplied = request.META.get("HTTP_AUTHORIZATION", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            response = HttpResponse(status=401)
            response["WWW-Authenticate"] = 'Bearer realm="metrics"'
            return response
    elif not settings.DEBUG:
        raise Http404()
    return HttpResponse(
        metrics.render_latest(), content_type="text/plain; version=0.0.4; charset=utf-8"
    )
