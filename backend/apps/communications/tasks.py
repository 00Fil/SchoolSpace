from celery import shared_task

from .dispatch import process_delivery, reconcile as run_reconcile


@shared_task(
    name="apps.communications.tasks.deliver", acks_late=True, reject_on_worker_lost=True
)
def deliver(delivery_id):
    return process_delivery(delivery_id)


@shared_task(name="apps.communications.tasks.reconcile")
def reconcile():
    return run_reconcile()
