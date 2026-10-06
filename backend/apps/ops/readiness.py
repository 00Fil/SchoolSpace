"""Controlli di readiness (GAP-K02): DB, migrazioni, cache, broker, heartbeat worker.

Ogni controllo restituisce True/False; i dettagli dell'errore vanno solo nel log
(redatto), mai nella risposta HTTP.
"""

from __future__ import annotations

import logging
import time
import uuid

from django.conf import settings
from django.core.cache import cache
from django.db import connections

log = logging.getLogger("ops.readiness")
_migrations_ok_until = 0.0


def check_database() -> bool:
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone()[0] == 1


def check_migrations() -> bool:
    """Nessuna migrazione pendente. Esito positivo in cache per 60 s per processo."""
    global _migrations_ok_until
    if time.monotonic() < _migrations_ok_until:
        return True
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connections["default"])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        return False
    _migrations_ok_until = time.monotonic() + 60
    return True


def check_cache() -> bool:
    key = f"ops:ready:{uuid.uuid4().hex}"
    cache.set(key, "1", 5)
    ok = cache.get(key) == "1"
    cache.delete(key)
    return ok


def check_broker() -> bool:
    url = str(getattr(settings, "CELERY_BROKER_URL", "") or "")
    if url.startswith(("memory://", "filesystem://")):
        return True
    from config.celery import app

    with app.connection_for_write() as conn:
        conn.ensure_connection(
            max_retries=1, interval_start=0, interval_step=0, timeout=2
        )
    return True


def check_workers() -> bool:
    from .heartbeat import stale_queues

    return not stale_queues()


CHECKS = {
    "database": check_database,
    "migrations": check_migrations,
    "cache": check_cache,
    "broker": check_broker,
    "workers": check_workers,
}


def run_checks(names=None, required=None) -> tuple[bool, dict]:
    names = list(names or CHECKS)
    if required is None:
        required = getattr(
            settings,
            "OPS_READY_REQUIRED_CHECKS",
            ("database", "migrations", "cache", "broker"),
        )
    required = set(required)
    results = {}
    healthy = True
    skipped: set[str] = set()
    for name in names:
        if name in skipped:
            results[name] = "skipped"
            continue
        try:
            ok = bool(CHECKS[name]())
        except Exception as exc:
            ok = False
            log.error(
                "readiness check failed",
                extra={
                    "check": name,
                    "exc_type": type(exc).__name__,
                    "outcome": "fail",
                },
            )
        results[name] = "ok" if ok else "fail"
        if not ok and name in required:
            healthy = False
        if name == "database" and not ok:
            # Con il DB giù le verifiche dipendenti sono inutili e lente.
            skipped |= {"migrations", "workers"}
            if required & skipped:
                healthy = False
    return healthy, results
