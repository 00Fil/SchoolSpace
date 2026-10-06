from django.contrib import admin
from .models import AvailabilityRule

admin.site.register(AvailabilityRule)

from apps.scheduling.admin import ReadOnlyAdmin
from .models import AvailabilityDeclaration, AvailabilityException, AvailabilityConflict

for model in (AvailabilityDeclaration, AvailabilityException, AvailabilityConflict):
    admin.site.register(model, ReadOnlyAdmin)
