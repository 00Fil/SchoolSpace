from django.contrib import admin
from apps.scheduling.admin import ReadOnlyAdmin
from .models import (
    CalendarResource,
    Publication,
    LessonOccurrence,
    LessonParticipant,
    ResourceBooking,
    CalendarAudit,
    CalendarEvent,
)

for model in [
    CalendarResource,
    Publication,
    LessonOccurrence,
    LessonParticipant,
    ResourceBooking,
    CalendarAudit,
    CalendarEvent,
]:
    admin.site.register(model, ReadOnlyAdmin)
