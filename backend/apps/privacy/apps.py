from django.apps import AppConfig


class PrivacyConfig(AppConfig):
    name = "apps.privacy"
    label = "privacy"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Protezione dei dati"

    def ready(self):
        from . import signals  # noqa: F401  (condizioni delega all'accettazione invito)
