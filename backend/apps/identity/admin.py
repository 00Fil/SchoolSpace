from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import conf
from .models import Account, IdentityAuditEvent, Invitation, RoleGrant, UserSession
from .policies import mfa_required


@admin.register(Account)
class AccountAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Verifica", {"fields": ("email_verified", "mfa_required")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {"fields": ("email",)}),)


admin.site.register(RoleGrant)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IdentityAuditEvent)
class IdentityAuditAdmin(ReadOnlyAdmin):
    list_display = ("occurred_at", "operation", "actor", "subject")
    list_filter = ("operation",)


@admin.register(Invitation)
class InvitationAdmin(ReadOnlyAdmin):
    list_display = ("email", "role", "status", "expires_at")
    exclude = ("token_hash",)


@admin.register(UserSession)
class UserSessionAdmin(ReadOnlyAdmin):
    list_display = ("account", "created_at", "last_seen_at", "revoked_at")


_base_has_permission = admin.site.has_permission


def _has_permission(request):
    """Admin solo con sessione registrata e MFA verificata (GAP-I06)."""
    if not _base_has_permission(request):
        return False
    if not conf.get("ADMIN_REQUIRE_MFA") or not mfa_required(request.user):
        return True
    record = getattr(request, "identity_session", None)
    return record is not None and record.mfa_verified_at is not None


admin.site.has_permission = _has_permission
