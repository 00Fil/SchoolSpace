from django.contrib import admin
from .models import Decision

admin.site.register(Decision)

from .models import CommandReceipt, PathAuditEvent


class ReadOnlyServiceAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(CommandReceipt, ReadOnlyServiceAdmin)
admin.site.register(PathAuditEvent, ReadOnlyServiceAdmin)

from .models import AuditEvent  # noqa: E402

admin.site.register(AuditEvent, ReadOnlyServiceAdmin)
