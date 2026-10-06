from django.apps import AppConfig


class GovernanceConfig(AppConfig):
    name = "apps.governance"
    label = "governance"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401  (registra l'audit delle azioni admin)
