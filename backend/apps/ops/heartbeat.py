from __future__ import annotations

import socket

from django.conf import settings
from django.utils import timezone

from .models import WorkerHeartbeat


def beat(queue: str, hostname: str | None = None) -> None:
    WorkerHeartbeat.objects.update_or_create(
        queue=queue[:40],
        defaults={
            "hostname": (hostname or socket.gethostname())[:200],
            "build": str(getattr(settings, "BUILD_VERSION", ""))[:80],
            "seen_at": timezone.now(),
        },
    )


def stale_queues(max_age_seconds: int | None = None, queues=None) -> list[str]:
    """Code richieste senza heartbeat recente."""
    max_age = max_age_seconds or int(getattr(settings, "OPS_HEARTBEAT_MAX_AGE", 120))
    wanted = list(
        queues if queues is not None else getattr(settings, "OPS_WORKER_QUEUES", ())
    )
    cutoff = timezone.now() - timezone.timedelta(seconds=max_age)
    fresh = set(
        WorkerHeartbeat.objects.filter(
            queue__in=wanted, seen_at__gte=cutoff
        ).values_list("queue", flat=True)
    )
    return [q for q in wanted if q not in fresh]
