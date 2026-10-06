from celery import shared_task

from .heartbeat import beat


@shared_task(name="apps.ops.tasks.heartbeat", ignore_result=True, acks_late=False)
def heartbeat(queue):
    """Eseguito dal worker che consuma ``queue``: prova che coda, worker e beat vivono."""
    beat(queue)
    return queue
