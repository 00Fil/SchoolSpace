from django.apps import AppConfig


class CalendarConfig(AppConfig):
    name = "apps.calendar"
    label = "lesson_calendar"

    def ready(self):
        from .signals import connect

        connect()
