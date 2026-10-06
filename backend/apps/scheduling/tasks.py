from celery import shared_task
from .runs import process_run, reconcile_runs


@shared_task(
    name="apps.scheduling.tasks.execute", acks_late=True, reject_on_worker_lost=True
)
def execute(run_id):
    return process_run(run_id)


@shared_task(name="apps.scheduling.tasks.reconcile")
def reconcile():
    return reconcile_runs()


@shared_task(name="apps.scheduling.tasks.probe_time_limit")
def probe_time_limit(seconds):
    """Diagnostic probe for real-broker time-limit tests; no data access."""
    from time import sleep
    from celery.exceptions import SoftTimeLimitExceeded

    try:
        sleep(seconds)
    except SoftTimeLimitExceeded:
        return "SOFT_TIME_LIMIT"
    return "COMPLETED"
