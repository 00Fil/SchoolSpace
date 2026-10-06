from django.contrib import admin
from . import models


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    models.TutorSkill,
    models.TutorOperatingPolicy,
    models.ResourceTiming,
    models.ServiceWindow,
    models.Closure,
    models.PlanningPolicy,
    models.PlanningSnapshot,
    models.DemandUnit,
    models.ScheduleRun,
    models.RunDispatch,
    models.SchedulePlan,
    models.PlanningAudit,
    models.PlanningRevision,
):
    admin.site.register(model, ReadOnlyAdmin)
