def heartbeat_schedule(queues, every: float = 30.0) -> dict:
    """Voci di CELERY_BEAT_SCHEDULE: un heartbeat per coda, con scadenza < periodo così,
    se il worker è giù, i messaggi non si accumulano."""
    return {
        f"ops-heartbeat-{queue}": {
            "task": "apps.ops.tasks.heartbeat",
            "schedule": every,
            "args": (queue,),
            "options": {"queue": queue, "expires": every * 0.8},
        }
        for queue in queues
    }
