"""Metriche Prometheus essenziali (GAP-K02).

- HTTP: istogramma della durata per route (template, mai il path grezzo), metodo e
  codice di stato; da qui p50/p95/p99, error rate, 401/429 sul login, 409 (conflitti
  di commit/stale) senza accoppiare gli altri moduli.
- Dominio: contatore generico ``ripetizioni_domain_events_total{kind}`` che gli altri
  moduli possono incrementare con ``record_event("commit_conflict")`` ecc.
- Stato (calcolato al momento dello scrape, con cache breve): run del solver per stato,
  età della coda, run oltre il limite hard, rifiuti del validatore, heartbeat dei worker,
  ultimo backup riuscito, build info, più i provider registrati da altri moduli
  (``OPS_METRIC_PROVIDERS``: outbox, delivery, ...).

Con gunicorn multi-processo impostare ``PROMETHEUS_MULTIPROC_DIR`` (vedi
infra/gunicorn.conf.py): i contatori sono aggregati da ``MultiProcessCollector``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import timedelta
from importlib import import_module

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

log = logging.getLogger(__name__)

LATENCY_BUCKETS = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.2,
    0.3,
    0.5,
    0.75,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
)

HTTP_DURATION = Histogram(
    "ripetizioni_http_request_duration_seconds",
    "Durata delle richieste HTTP per route template",
    ["method", "route", "status"],
    buckets=LATENCY_BUCKETS,
)
HTTP_REQUESTS = Counter(
    "ripetizioni_http_requests_total",
    "Richieste HTTP per route template e codice di stato",
    ["method", "route", "status"],
)
DOMAIN_EVENTS = Counter(
    "ripetizioni_domain_events_total",
    "Eventi di dominio rilevanti per l'esercizio (conflitti, stale, rifiuti, ...)",
    ["kind"],
)

# Allowlist dei "kind" per evitare cardinalità illimitata da chiamanti futuri.
DOMAIN_EVENT_KINDS = frozenset(
    {
        "commit_conflict",
        "stale_revision",
        "validator_rejected",
        "login_failed",
        "rate_limited",
        "delivery_failed",
        "delivery_sent",
        "outbox_retry",
        "permission_denied",
        "restore_reconciled",
    }
)


def record_event(kind: str, amount: int = 1) -> None:
    """API stabile per gli altri moduli. I kind sconosciuti finiscono in ``other``."""
    DOMAIN_EVENTS.labels(kind=kind if kind in DOMAIN_EVENT_KINDS else "other").inc(
        amount
    )


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    labels = {
        "method": method if method in _METHODS else "OTHER",
        "route": route,
        "status": str(status),
    }
    HTTP_DURATION.labels(**labels).observe(seconds)
    HTTP_REQUESTS.labels(**labels).inc()


_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


# ---------------------------------------------------------------------------
# Collector di stato (letture DB al momento dello scrape)
# ---------------------------------------------------------------------------


def _gauge(name, doc, labels=None):
    return GaugeMetricFamily(name, doc, labels=labels or [])


def scheduling_metrics(now):
    from django.conf import settings
    from django.db.models import Count, Min

    from apps.scheduling.models import ScheduleRun

    by_status = _gauge(
        "ripetizioni_schedule_runs", "Run del solver per stato", ["status"]
    )
    counts = dict(ScheduleRun.objects.values_list("status").annotate(n=Count("pk")))
    for status in ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"):
        by_status.add_metric([status], counts.get(status, 0))
    yield by_status

    oldest = ScheduleRun.objects.filter(status="QUEUED").aggregate(m=Min("created_at"))[
        "m"
    ]
    age = _gauge(
        "ripetizioni_schedule_run_oldest_queued_age_seconds",
        "Età del run in coda più vecchio",
    )
    age.add_metric([], (now - oldest).total_seconds() if oldest else 0)
    yield age

    hard = int(getattr(settings, "CELERY_TASK_TIME_LIMIT", 90))
    over = _gauge(
        "ripetizioni_schedule_runs_over_hard_limit",
        "Run RUNNING da più del limite hard (NFR04)",
    )
    over.add_metric(
        [],
        ScheduleRun.objects.filter(
            status="RUNNING", started_at__lt=now - timedelta(seconds=hard)
        ).count(),
    )
    yield over

    failed = _gauge(
        "ripetizioni_schedule_runs_failed",
        "Run falliti per codice (monotono: i run non si cancellano); VALIDATION_FAILED = validatore",
        ["error_code"],
    )
    rows = (
        ScheduleRun.objects.filter(status="FAILED")
        .values_list("error_code")
        .annotate(n=Count("pk"))
    )
    seen = False
    for code, n in rows:
        failed.add_metric([code or "UNKNOWN"], n)
        seen = True
    if not seen:
        failed.add_metric(["VALIDATION_FAILED"], 0)
    yield failed


def heartbeat_metrics(now):
    from django.conf import settings

    from .models import WorkerHeartbeat

    gauge = _gauge(
        "ripetizioni_worker_heartbeat_age_seconds",
        "Secondi dall'ultimo heartbeat per coda (assente = valore molto alto)",
        ["queue"],
    )
    seen = {hb.queue: hb.seen_at for hb in WorkerHeartbeat.objects.all()}
    for queue in sorted(set(getattr(settings, "OPS_WORKER_QUEUES", ())) | set(seen)):
        at = seen.get(queue)
        gauge.add_metric([queue], (now - at).total_seconds() if at else 1e9)
    yield gauge


def backup_metrics(now):
    from django.conf import settings

    path = getattr(settings, "OPS_BACKUP_STATUS_FILE", "")
    if not path:
        return
    last = _gauge(
        "ripetizioni_backup_last_success_timestamp_seconds",
        "Unix time dell'ultimo dump logico riuscito e verificato (scripts/backup.sh)",
    )
    size = _gauge("ripetizioni_backup_last_size_bytes", "Dimensione dell'ultimo dump")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        last.add_metric([], float(data.get("last_success_epoch", 0)))
        size.add_metric([], float(data.get("size_bytes", 0)))
    except (OSError, ValueError):
        last.add_metric([], 0)
        size.add_metric([], 0)
    yield last
    yield size


def build_metrics(now):
    from django.conf import settings

    info = _gauge(
        "ripetizioni_build_info",
        "Versione della build in esecuzione",
        ["version", "env"],
    )
    info.add_metric(
        [
            getattr(settings, "BUILD_VERSION", "unknown"),
            getattr(settings, "DEPLOY_ENVIRONMENT", "unknown"),
        ],
        1,
    )
    yield info


def capacity_metrics(now):
    """Limiti di capacità del DB gestito (da contratto): denominatori degli alert all'80%."""
    from django.conf import settings

    for name, setting, doc in (
        (
            "ripetizioni_db_storage_limit_bytes",
            "OPS_DB_STORAGE_LIMIT_BYTES",
            "Storage massimo del DB gestito",
        ),
        (
            "ripetizioni_db_wal_limit_bytes",
            "OPS_DB_WAL_LIMIT_BYTES",
            "Spazio massimo per i WAL",
        ),
    ):
        value = int(getattr(settings, setting, 0) or 0)
        if value:
            gauge = _gauge(name, doc)
            gauge.add_metric([], value)
            yield gauge


def communications_metrics(now):
    """Outbox e consegne (s3, apps.communications): backlog, età e tentativi per esito.

    I tentativi sono append-only, quindi il conteggio per esito è un contatore monotono
    anche se letto dal DB (sopravvive ai riavvii e vale per tutti i processi).
    """
    from django.apps import apps as django_apps

    if not django_apps.is_installed("apps.communications"):
        return
    from django.db.models import Count, Min

    from apps.communications.models import Delivery, DeliveryAttempt

    active = ("PENDING", "SENDING", "AMBIGUOUS")
    by_status = _gauge(
        "ripetizioni_delivery_backlog",
        "Consegne non concluse per canale e stato",
        ["channel", "status"],
    )
    pending = 0
    for row in (
        Delivery.objects.filter(status__in=active)
        .values("channel", "status")
        .annotate(n=Count("pk"))
    ):
        by_status.add_metric([row["channel"], row["status"]], row["n"])
        pending += row["n"]
    yield by_status
    total = _gauge(
        "ripetizioni_outbox_pending", "Consegne in attesa o in invio (tutti i canali)"
    )
    total.add_metric([], pending)
    yield total
    oldest = Delivery.objects.filter(status__in=("PENDING", "SENDING")).aggregate(
        m=Min("created_at")
    )["m"]
    age = _gauge(
        "ripetizioni_outbox_oldest_pending_age_seconds",
        "Età della consegna in attesa più vecchia",
    )
    age.add_metric([], max(0.0, (now - oldest).total_seconds()) if oldest else 0.0)
    yield age
    dead = _gauge("ripetizioni_delivery_dead", "Consegne in dead-letter da verificare")
    dead.add_metric([], Delivery.objects.filter(status="DEAD").count())
    yield dead
    attempts = CounterMetricFamily(
        "ripetizioni_delivery_attempts",
        "Tentativi di consegna per esito (DeliveryAttempt, append-only)",
        labels=["outcome"],
    )
    for row in DeliveryAttempt.objects.values("outcome").annotate(n=Count("pk")):
        attempts.add_metric([row["outcome"]], row["n"])
    yield attempts


BUILTIN_PROVIDERS = (
    build_metrics,
    scheduling_metrics,
    heartbeat_metrics,
    backup_metrics,
    capacity_metrics,
    communications_metrics,
)


def _load(path):
    module, _, attr = path.rpartition(".")
    return getattr(import_module(module), attr)


class StateCollector:
    """Collector "custom" con cache: più scraper non moltiplicano le query sul DB."""

    def __init__(self, ttl: float = 15.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._cache: tuple[float, list] | None = None

    def providers(self):
        from django.conf import settings

        result = list(BUILTIN_PROVIDERS)
        for path in getattr(settings, "OPS_METRIC_PROVIDERS", ()):
            try:
                result.append(_load(path))
            except (ImportError, AttributeError):
                log.warning("metric provider unavailable", extra={"provider": path})
        return result

    def collect_now(self):
        from django.utils import timezone

        now = timezone.now()
        families = []
        errors = 0
        for provider in self.providers():
            try:
                families.extend(provider(now))
            except Exception as exc:  # una sorgente rotta non deve azzerare lo scrape
                errors += 1
                log.warning(
                    "metric provider failed",
                    extra={
                        "provider": getattr(provider, "__name__", "?"),
                        "exc_type": type(exc).__name__,
                    },
                )
        err = _gauge(
            "ripetizioni_metrics_provider_errors",
            "Provider di metriche falliti nell'ultimo scrape",
        )
        err.add_metric([], errors)
        families.append(err)
        return families

    def collect(self):
        with self._lock:
            stamp = time.monotonic()
            if self._cache is None or stamp - self._cache[0] > self.ttl:
                self._cache = (stamp, self.collect_now())
            return list(self._cache[1])

    def invalidate(self):
        with self._lock:
            self._cache = None


STATE = StateCollector()


def render_latest() -> bytes:
    """Testo di esposizione Prometheus (process/HTTP + stato)."""
    registry = CollectorRegistry()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY

        registry = REGISTRY
        output = generate_latest(registry)
        state = CollectorRegistry()
        state.register(_Wrapper())
        return output + generate_latest(state)
    registry.register(_Wrapper())
    return generate_latest(registry)


class _Wrapper:
    def collect(self):
        return STATE.collect()
