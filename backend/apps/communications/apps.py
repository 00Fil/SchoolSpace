from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    name = "apps.communications"
    label = "communications"
    verbose_name = "Comunicazioni"

    def ready(self):
        from . import checks  # noqa: F401  (registra i system check)
