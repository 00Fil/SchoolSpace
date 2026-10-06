"""Segnali Celery: propagazione del correlation_id e heartbeat all'avvio del worker."""

from __future__ import annotations

import logging

from celery import signals

from .context import (
    actor_id_var,
    correlation_id_var,
    new_correlation_id,
    sanitize_correlation_id,
)

log = logging.getLogger("ops.celery")
HEADER = "correlation_id"


@signals.before_task_publish.connect(dispatch_uid="ops.correlation.publish")
def add_correlation_header(headers=None, **kwargs):
    if headers is not None and not headers.get(HEADER):
        headers[HEADER] = correlation_id_var.get() or new_correlation_id()


@signals.task_prerun.connect(dispatch_uid="ops.correlation.prerun")
def bind_correlation(task=None, **kwargs):
    request = getattr(task, "request", None)
    value = getattr(request, HEADER, None) if request is not None else None
    if not value and request is not None:
        value = (getattr(request, "headers", None) or {}).get(HEADER)
    # I task di un processo prefork sono sequenziali: set/clear è sufficiente
    # (reset() con token non è sicuro se il pool cambia contesto).
    correlation_id_var.set(sanitize_correlation_id(value))
    actor_id_var.set(None)


@signals.task_postrun.connect(dispatch_uid="ops.correlation.postrun")
def unbind_correlation(task=None, **kwargs):
    correlation_id_var.set(None)
    actor_id_var.set(None)


@signals.worker_ready.connect(dispatch_uid="ops.heartbeat.ready")
def heartbeat_on_ready(sender=None, **kwargs):
    try:
        from .heartbeat import beat

        consumer = getattr(sender, "consumer", None) if sender is not None else None
        queues = (
            [q.name for q in consumer.task_consumer.queues]
            if consumer and consumer.task_consumer
            else []
        )
        for queue in queues:
            beat(queue, getattr(sender, "hostname", None))
    except (
        Exception
    ) as exc:  # il worker deve partire anche se il DB è momentaneamente giù
        log.warning("initial heartbeat failed", extra={"exc_type": type(exc).__name__})
