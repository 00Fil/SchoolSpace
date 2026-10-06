from django.contrib import admin

from .models import (
    CalendarFeedToken,
    ChannelPreference,
    Delivery,
    DeliveryAttempt,
    MeetingLink,
    OutboxEvent,
)


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboxEvent)
class OutboxAdmin(ReadOnly):
    list_display = ["event_type", "category", "subject_ref", "created_at"]
    list_filter = ["event_type", "category"]


@admin.register(Delivery)
class DeliveryAdmin(ReadOnly):
    list_display = [
        "id",
        "channel",
        "status",
        "attempts",
        "last_error_code",
        "updated_at",
    ]
    list_filter = ["status", "channel"]
    exclude = ["context"]


@admin.register(DeliveryAttempt)
class AttemptAdmin(ReadOnly):
    list_display = ["delivery", "number", "outcome", "error_code", "created_at"]
    list_filter = ["outcome"]


@admin.register(ChannelPreference)
class PreferenceAdmin(ReadOnly):
    list_display = ["account", "category", "channel", "enabled"]


@admin.register(CalendarFeedToken)
class FeedTokenAdmin(ReadOnly):
    list_display = ["account", "label", "created_at", "expires_at", "revoked_at"]
    exclude = ["token_hash"]


@admin.register(MeetingLink)
class MeetingLinkAdmin(admin.ModelAdmin):
    list_display = ["lesson", "resource", "updated_at"]
    raw_id_fields = ["lesson"]
