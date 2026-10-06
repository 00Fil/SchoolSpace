from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"

    def ready(self):
        from . import signals
