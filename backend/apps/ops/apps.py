from django.apps import AppConfig


class OpsConfig(AppConfig):
    """Osservabilità ed esercizio: log JSON, health/readiness, metriche, heartbeat."""

    name = "apps.ops"
    label = "ops"
    verbose_name = "Esercizio e osservabilità"

    def ready(self):
        from . import signals  # noqa: F401  (Celery: correlation_id e heartbeat)
